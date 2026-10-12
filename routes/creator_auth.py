"""
============================================================
KALXA CREATOR
CREATOR AUTHENTICATION
============================================================

Handles:

- Creator registration
- Creator login
- Creator logout
- Free plan activation
- Standard/Premium activation eligibility
- Creator account status
- Creator session management
- Creator account/plan page

PRICING:

FREE
    R0 forever
    23% Kalxa commission on fan support

STANDARD
    R100 once-off activation
    3% Kalxa commission

PREMIUM
    R150 once-off activation
    3% Kalxa commission
    Advanced creator tools

SECURITY:

Selecting a paid plan does not activate paid features.

Paid access requires server-verified payment status.

Legacy pending accounts are not automatically activated.
============================================================
"""

import re

from functools import wraps

from sqlalchemy.exc import IntegrityError

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    current_app,
)

from extensions import db

from models import (
    CreatorAccount,
    CreatorProfile,
    utc_now,
)


# ============================================================
# BLUEPRINT
# ============================================================

creator_auth_bp = Blueprint(
    "creator_auth",
    __name__,
    url_prefix="/creator",
)


# ============================================================
# PLAN CONFIGURATION
# ============================================================

PLAN_PRICES = {
    "free": 0,
    "standard": 100,
    "premium": 150,
}

VALID_PLANS = frozenset(
    PLAN_PRICES.keys()
)

PAID_PLANS = frozenset({
    "standard",
    "premium",
})


# ============================================================
# USERNAME NORMALIZATION
# ============================================================

def normalize_username(value):
    """
    Normalize creator usernames.

    Allowed:
        a-z
        0-9
        underscore
    """

    return re.sub(
        r"[^a-z0-9_]+",
        "",
        str(value or "").strip().lower(),
    )


# ============================================================
# CURRENT LOGGED-IN CREATOR
# ============================================================

def get_logged_in_creator():
    """
    Resolve the creator from the current session.

    Never trust a creator ID supplied through request
    parameters for authentication.
    """

    creator_id = session.get(
        "creator_account_id"
    )

    if not creator_id:
        return None

    try:
        return db.session.get(
            CreatorAccount,
            creator_id,
        )

    except Exception:

        current_app.logger.exception(
            "Unable to load creator session."
        )

        db.session.rollback()

        return None


# ============================================================
# LEGACY SUBSCRIPTION COMPATIBILITY
# ============================================================

def refresh_creator_subscription(creator):
    """
    Compatibility helper for existing templates.

    Kalxa Creator now uses once-off activation plans.

    Do not enforce monthly subscription expiry for
    Free, Standard or Premium creator access.
    """

    if creator is None:
        return None

    return getattr(
        creator,
        "platform_subscription",
        None,
    )


# ============================================================
# CREATOR STUDIO ACCESS
# ============================================================

def creator_can_enter_studio(creator):
    """
    Authoritative creator access rules.

    FREE:
        Account must be active.

    STANDARD:
        Account must be active.
        Payment must be verified.

    PREMIUM:
        Account must be active.
        Payment must be verified.

    Other statuses/plans:
        Deny access.

    IMPORTANT:
        Payment status must only be updated by trusted
        server-side payment verification logic.
    """

    if creator is None:
        return False

    account_status = str(
        creator.account_status or ""
    ).strip().lower()

    if account_status != "active":
        return False

    plan = str(
        creator.plan or ""
    ).strip().lower()

    # --------------------------------------------------------
    # FREE
    # --------------------------------------------------------

    if plan == "free":
        return True

    # --------------------------------------------------------
    # STANDARD / PREMIUM
    # --------------------------------------------------------

    if plan in PAID_PLANS:

        payment_status = str(
            creator.payment_status or ""
        ).strip().lower()

        return bool(
            payment_status == "paid"
            and creator.registration_paid_at is not None
        )

    # --------------------------------------------------------
    # UNKNOWN PLAN
    # --------------------------------------------------------

    return False


# ============================================================
# CREATOR LOGIN REQUIRED
# ============================================================

def creator_login_required(view):

    @wraps(view)
    def wrapped_view(
        *args,
        **kwargs,
    ):

        creator = get_logged_in_creator()

        if creator is None:

            session.pop(
                "creator_account_id",
                None,
            )

            flash(
                "Please sign in to continue.",
                "warning",
            )

            return redirect(
                url_for(
                    "creator_auth.login"
                )
            )

        return view(
            *args,
            **kwargs,
        )

    return wrapped_view


# ============================================================
# REGISTRATION TEMPLATE
# ============================================================

def _register_page(selected_plan):

    return render_template(
        "creator/register.html",
        selected_plan=selected_plan,
        plan_prices=PLAN_PRICES,
    )


# ============================================================
# REGISTRATION
# ============================================================

@creator_auth_bp.route(
    "/register",
    methods=[
        "GET",
        "POST",
    ],
)
def register():

    # ========================================================
    # ALREADY LOGGED IN
    # ========================================================

    existing = get_logged_in_creator()

    if existing:

        if creator_can_enter_studio(
            existing
        ):

            return redirect(
                url_for(
                    "studio.dashboard"
                )
            )

        return redirect(
            url_for(
                "creator_auth.pending"
            )
        )

    # ========================================================
    # SELECTED PLAN
    # ========================================================

    selected_plan = str(
        request.values.get(
            "plan"
        )
        or "free"
    ).strip().lower()

    if selected_plan not in VALID_PLANS:
        selected_plan = "free"

    if request.method == "GET":

        return _register_page(
            selected_plan
        )

    # ========================================================
    # FORM INPUT
    # ========================================================

    display_name = str(
        request.form.get(
            "display_name"
        )
        or ""
    ).strip()

    username = normalize_username(
        request.form.get(
            "username"
        )
    )

    email = str(
        request.form.get(
            "email"
        )
        or ""
    ).strip().lower()

    password = (
        request.form.get(
            "password"
        )
        or ""
    )

    confirmation = (
        request.form.get(
            "confirm_password"
        )
        or ""
    )

    # ========================================================
    # VALIDATION
    # ========================================================

    if not (
        1 <= len(display_name) <= 120
    ):

        flash(
            (
                "Enter a display name of "
                "up to 120 characters."
            ),
            "error",
        )

        return _register_page(
            selected_plan
        )

    if not (
        3 <= len(username) <= 80
    ):

        flash(
            (
                "Username must contain "
                "3–80 letters, digits "
                "or underscores."
            ),
            "error",
        )

        return _register_page(
            selected_plan
        )

    if (
        len(email) > 255
        or not re.fullmatch(
            r"[^\s@]+@[^\s@]+\.[^\s@]+",
            email,
        )
    ):

        flash(
            "Enter a valid email address.",
            "error",
        )

        return _register_page(
            selected_plan
        )

    if len(password) < 8:

        flash(
            (
                "Password must contain "
                "at least 8 characters."
            ),
            "error",
        )

        return _register_page(
            selected_plan
        )

    if password != confirmation:

        flash(
            "Passwords do not match.",
            "error",
        )

        return _register_page(
            selected_plan
        )

    # ========================================================
    # USERNAME UNIQUENESS
    # ========================================================

    existing_account_username = (
        CreatorAccount.query
        .filter(
            db.func.lower(
                CreatorAccount.username
            ) == username
        )
        .first()
    )

    existing_profile_username = (
        CreatorProfile.query
        .filter(
            db.func.lower(
                CreatorProfile.username
            ) == username
        )
        .first()
    )

    if (
        existing_account_username
        or existing_profile_username
    ):

        flash(
            "That username is already taken.",
            "error",
        )

        return _register_page(
            selected_plan
        )

    # ========================================================
    # EMAIL UNIQUENESS
    # ========================================================

    existing_email = (
        CreatorAccount.query
        .filter(
            db.func.lower(
                CreatorAccount.email
            ) == email
        )
        .first()
    )

    if existing_email:

        flash(
            (
                "An account already exists "
                "for that email address."
            ),
            "error",
        )

        return _register_page(
            selected_plan
        )

    # ========================================================
    # CREATE FREE ACCOUNT FIRST
    # ========================================================
    #
    # Even if Standard/Premium was selected:
    #
    # The account starts on Free.
    #
    # Only verified payment may upgrade the account.
    # ========================================================

    creator = CreatorAccount(
        username=username,
        email=email,
        plan="free",
        account_status="active",
        payment_status="unpaid",
        subscription_status="inactive",
    )

    creator.set_password(
        password
    )

    # ========================================================
    # SAVE CREATOR ACCOUNT AND PROFILE
    # ========================================================

    try:

        db.session.add(
            creator
        )

        db.session.flush()

        profile = CreatorProfile(
            creator_account_id=creator.id,
            display_name=display_name,
            username=username,
        )

        db.session.add(
            profile
        )

        db.session.commit()

    except IntegrityError:

        db.session.rollback()

        flash(
            (
                "That username or email "
                "is already registered."
            ),
            "error",
        )

        return _register_page(
            selected_plan
        )

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Creator registration failed."
        )

        flash(
            (
                "Registration is temporarily "
                "unavailable. Please try again."
            ),
            "error",
        )

        return _register_page(
            selected_plan
        )

    # ========================================================
    # CREATE CREATOR SESSION
    # ========================================================

    session.clear()

    session[
        "creator_account_id"
    ] = creator.id

    session.permanent = True

    # ========================================================
    # PAID PLAN INTENT
    # ========================================================

    if selected_plan in PAID_PLANS:

        session[
            "requested_creator_plan"
        ] = selected_plan

        flash(
            (
                "Your Free creator account "
                "is ready. Activate your "
                "selected paid plan when ready."
            ),
            "success",
        )

        return redirect(
            url_for(
                "creator_auth.pending"
            )
        )

    # ========================================================
    # FREE PLAN
    # ========================================================

    flash(
        (
            "Your Free creator account "
            "is ready."
        ),
        "success",
    )

    return redirect(
        url_for(
            "studio.dashboard"
        )
    )


# ============================================================
# LOGIN
# ============================================================

@creator_auth_bp.route(
    "/login",
    methods=[
        "GET",
        "POST",
    ],
)
def login():

    # ========================================================
    # EXISTING SESSION
    # ========================================================

    existing = get_logged_in_creator()

    if existing:

        if creator_can_enter_studio(
            existing
        ):

            return redirect(
                url_for(
                    "studio.dashboard"
                )
            )

        return redirect(
            url_for(
                "creator_auth.pending"
            )
        )

    # ========================================================
    # LOGIN PAGE
    # ========================================================

    if request.method == "GET":

        return render_template(
            "creator/login.html"
        )

    # ========================================================
    # FORM INPUT
    # ========================================================

    identity = str(
        request.form.get(
            "identity"
        )
        or ""
    ).strip().lower()

    password = (
        request.form.get(
            "password"
        )
        or ""
    )

    # ========================================================
    # FIND ACCOUNT
    # ========================================================

    creator = None

    if identity:

        creator = (
            CreatorAccount.query
            .filter(
                db.or_(
                    db.func.lower(
                        CreatorAccount.username
                    ) == identity,
                    db.func.lower(
                        CreatorAccount.email
                    ) == identity,
                )
            )
            .first()
        )

    # ========================================================
    # VERIFY CREDENTIALS
    # ========================================================

    if (
        creator is None
        or not password
        or not creator.check_password(
            password
        )
    ):

        flash(
            "Invalid login details.",
            "error",
        )

        return render_template(
            "creator/login.html"
        )

    # ========================================================
    # ACCOUNT RESTRICTIONS
    # ========================================================

    if creator.account_status in {
        "rejected",
        "suspended",
    }:

        flash(
            (
                "This account is not "
                "currently available."
            ),
            "error",
        )

        return render_template(
            "creator/login.html"
        )

    # ========================================================
    # CREATE NEW SESSION
    # ========================================================

    session.clear()

    session[
        "creator_account_id"
    ] = creator.id

    session.permanent = True

    # ========================================================
    # RECORD LAST LOGIN
    # ========================================================

    creator.last_login_at = utc_now()

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Could not record creator login."
        )

    # ========================================================
    # REDIRECT ACCORDING TO ACCOUNT STATUS
    # ========================================================

    if creator_can_enter_studio(
        creator
    ):

        return redirect(
            url_for(
                "studio.dashboard"
            )
        )

    return redirect(
        url_for(
            "creator_auth.pending"
        )
    )


# ============================================================
# CREATOR ACCOUNT / PLAN PAGE
# ============================================================

@creator_auth_bp.route(
    "/pending"
)
@creator_login_required
def pending():

    creator = get_logged_in_creator()

    subscription = (
        refresh_creator_subscription(
            creator
        )
    )

    plan = str(
        creator.plan or "free"
    ).strip().lower()

    if plan not in VALID_PLANS:
        plan = "free"

    requested_plan = session.get(
        "requested_creator_plan"
    )

    if requested_plan not in PAID_PLANS:
        requested_plan = None

    # ========================================================
    # PUBLIC CREATOR URL
    # ========================================================

    public_url = None

    if creator.account_status == "active":

        public_url = url_for(
            "public.creator_home",
            username=creator.username,
        )

    # ========================================================
    # ACCOUNT PAGE
    # ========================================================

    return render_template(
        "creator/pending.html",

        creator_account=creator,

        subscription=subscription,

        subscription_status=(
            creator.subscription_status
            or "inactive"
        ),

        grace_days_remaining=0,

        selected_plan=plan,

        selected_plan_price=(
            PLAN_PRICES[plan]
        ),

        plan_prices=PLAN_PRICES,

        requested_plan=requested_plan,

        public_creator_url=public_url,

        can_enter_studio=(
            creator_can_enter_studio(
                creator
            )
        ),
    )


# ============================================================
# LOGOUT
# ============================================================

@creator_auth_bp.route(
    "/logout",
    methods=[
        "POST",
    ],
)
@creator_login_required
def logout():

    session.clear()

    flash(
        (
            "You have been "
            "signed out."
        ),
        "success",
    )

    return redirect(
        url_for(
            "creator_auth.login"
        )
    )
