# ============================================================
# CREATOR PLATFORM
# CREATOR AUTHENTICATION
# ============================================================

import re

from functools import wraps

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
)

from extensions import db

from models import (
    CreatorAccount,
    CreatorProfile,
    utc_now,
)

from services.plan_service import (
    PLAN_STANDARD,
    PLAN_PREMIUM,
    VALID_PLANS,
    PLAN_PRICES,
    normalize_plan,
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
# HELPERS
# ============================================================

def normalize_username(
    value,
):

    value = (
        value
        .strip()
        .lower()
    )

    value = re.sub(
        r"[^a-z0-9_]+",
        "",
        value,
    )

    return value


def get_logged_in_creator():

    creator_id = session.get(
        "creator_account_id"
    )

    if not creator_id:
        return None

    return db.session.get(
        CreatorAccount,
        creator_id,
    )


def creator_login_required(
    view,
):

    @wraps(view)
    def wrapped_view(
        *args,
        **kwargs,
    ):

        creator = (
            get_logged_in_creator()
        )

        if not creator:

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
# REGISTER
# ============================================================

@creator_auth_bp.route(
    "/register",
    methods=[
        "GET",
        "POST",
    ],
)
def register():

    # --------------------------------------------------------
    # ALREADY LOGGED IN
    # --------------------------------------------------------

    existing_creator = (
        get_logged_in_creator()
    )

    if existing_creator:

        if (
            existing_creator.account_status
            == "active"
            and existing_creator.subscription_status
            == "active"
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

    # --------------------------------------------------------
    # DEFAULT PLAN
    # --------------------------------------------------------

    selected_plan = (
        request.args
        .get(
            "plan",
            PLAN_STANDARD,
        )
        .strip()
        .lower()
    )

    if selected_plan not in VALID_PLANS:
        selected_plan = PLAN_STANDARD

    # --------------------------------------------------------
    # FORM
    # --------------------------------------------------------

    if request.method == "POST":

        display_name = (
            request.form
            .get(
                "display_name",
                "",
            )
            .strip()
        )

        username = normalize_username(
            request.form.get(
                "username",
                "",
            )
        )

        email = (
            request.form
            .get(
                "email",
                "",
            )
            .strip()
            .lower()
        )

        password = (
            request.form
            .get(
                "password",
                "",
            )
        )

        confirm_password = (
            request.form
            .get(
                "confirm_password",
                "",
            )
        )

        selected_plan = (
            request.form
            .get(
                "plan",
                PLAN_STANDARD,
            )
            .strip()
            .lower()
        )

        # ====================================================
        # PLAN VALIDATION
        # ====================================================

        if selected_plan not in VALID_PLANS:

            flash(
                "Choose a valid creator plan.",
                "error",
            )

            return render_template(
                "creator/register.html",
                selected_plan=PLAN_STANDARD,
                plan_prices=PLAN_PRICES,
            )

        selected_plan = normalize_plan(
            selected_plan
        )

        # ====================================================
        # VALIDATION
        # ====================================================

        if not display_name:

            flash(
                "Enter your display name.",
                "error",
            )

            return render_template(
                "creator/register.html",
                selected_plan=selected_plan,
                plan_prices=PLAN_PRICES,
            )

        if len(display_name) > 120:

            flash(
                "Display name is too long.",
                "error",
            )

            return render_template(
                "creator/register.html",
                selected_plan=selected_plan,
                plan_prices=PLAN_PRICES,
            )

        if not username:

            flash(
                "Choose a username.",
                "error",
            )

            return render_template(
                "creator/register.html",
                selected_plan=selected_plan,
                plan_prices=PLAN_PRICES,
            )

        if len(username) < 3:

            flash(
                "Username must contain at least "
                "3 characters.",
                "error",
            )

            return render_template(
                "creator/register.html",
                selected_plan=selected_plan,
                plan_prices=PLAN_PRICES,
            )

        if len(username) > 80:

            flash(
                "Username is too long.",
                "error",
            )

            return render_template(
                "creator/register.html",
                selected_plan=selected_plan,
                plan_prices=PLAN_PRICES,
            )

        if (
            not email
            or "@" not in email
            or "." not in email.split("@")[-1]
        ):

            flash(
                "Enter a valid email address.",
                "error",
            )

            return render_template(
                "creator/register.html",
                selected_plan=selected_plan,
                plan_prices=PLAN_PRICES,
            )

        if len(email) > 255:

            flash(
                "Email address is too long.",
                "error",
            )

            return render_template(
                "creator/register.html",
                selected_plan=selected_plan,
                plan_prices=PLAN_PRICES,
            )

        if len(password) < 8:

            flash(
                "Password must contain at least "
                "8 characters.",
                "error",
            )

            return render_template(
                "creator/register.html",
                selected_plan=selected_plan,
                plan_prices=PLAN_PRICES,
            )

        if (
            password
            != confirm_password
        ):

            flash(
                "Passwords do not match.",
                "error",
            )

            return render_template(
                "creator/register.html",
                selected_plan=selected_plan,
                plan_prices=PLAN_PRICES,
            )

        # ====================================================
        # DUPLICATE ACCOUNT
        # ====================================================

        duplicate_username = (
            CreatorAccount.query
            .filter(
                db.func.lower(
                    CreatorAccount.username
                )
                == username
            )
            .first()
        )

        if duplicate_username:

            flash(
                "That username is already taken.",
                "error",
            )

            return render_template(
                "creator/register.html",
                selected_plan=selected_plan,
                plan_prices=PLAN_PRICES,
            )

        duplicate_profile = (
            CreatorProfile.query
            .filter(
                db.func.lower(
                    CreatorProfile.username
                )
                == username
            )
            .first()
        )

        if duplicate_profile:

            flash(
                "That username is already taken.",
                "error",
            )

            return render_template(
                "creator/register.html",
                selected_plan=selected_plan,
                plan_prices=PLAN_PRICES,
            )

        duplicate_email = (
            CreatorAccount.query
            .filter(
                db.func.lower(
                    CreatorAccount.email
                )
                == email
            )
            .first()
        )

        if duplicate_email:

            flash(
                "An account already exists "
                "for that email address.",
                "error",
            )

            return render_template(
                "creator/register.html",
                selected_plan=selected_plan,
                plan_prices=PLAN_PRICES,
            )

        # ====================================================
        # CREATE ACCOUNT
        # ====================================================

        creator = CreatorAccount(
            username=username,
            email=email,

            plan=selected_plan,

            account_status=(
                "pending_payment"
            ),

            payment_status="unpaid",

            subscription_status=(
                "inactive"
            ),
        )

        creator.set_password(
            password
        )

        db.session.add(
            creator
        )

        # Need ID for profile ownership.
        db.session.flush()

        # ====================================================
        # CREATE PROFILE
        # ====================================================

        profile = CreatorProfile(
            creator_account_id=creator.id,
            display_name=display_name,
            username=username,
            tagline=None,
            bio=None,
            profile_image_url=None,
            intro_reel_url=None,
            instagram_url=None,
            tiktok_url=None,
            youtube_url=None,
        )

        db.session.add(
            profile
        )

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()
            raise

        # ====================================================
        # LOGIN NEW CREATOR
        # ====================================================

        session.clear()

        session[
            "creator_account_id"
        ] = creator.id

        flash(
            "Your creator account has been created.",
            "success",
        )

        return redirect(
            url_for(
                "creator_auth.pending"
            )
        )

    return render_template(
        "creator/register.html",
        selected_plan=selected_plan,
        plan_prices=PLAN_PRICES,
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

    creator = (
        get_logged_in_creator()
    )

    if creator:

        if (
            creator.account_status
            == "active"
            and creator.subscription_status
            == "active"
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

    if request.method == "POST":

        identity = (
            request.form
            .get(
                "identity",
                "",
            )
            .strip()
            .lower()
        )

        password = (
            request.form
            .get(
                "password",
                "",
            )
        )

        if (
            not identity
            or not password
        ):

            flash(
                "Enter your username/email "
                "and password.",
                "error",
            )

            return render_template(
                "creator/login.html"
            )

        creator = (
            CreatorAccount.query
            .filter(
                db.or_(
                    db.func.lower(
                        CreatorAccount.username
                    )
                    == identity,

                    db.func.lower(
                        CreatorAccount.email
                    )
                    == identity,
                )
            )
            .first()
        )

        if (
            not creator
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

        # ----------------------------------------------------
        # REJECTED
        # ----------------------------------------------------

        if (
            creator.account_status
            == "rejected"
        ):

            flash(
                "This creator account was not approved.",
                "error",
            )

            return render_template(
                "creator/login.html"
            )

        # ----------------------------------------------------
        # SUSPENDED
        # ----------------------------------------------------

        if (
            creator.account_status
            == "suspended"
        ):

            flash(
                "This creator account is currently suspended.",
                "error",
            )

            return render_template(
                "creator/login.html"
            )

        # ----------------------------------------------------
        # LOGIN
        # ----------------------------------------------------

        session.clear()

        session[
            "creator_account_id"
        ] = creator.id

        creator.last_login_at = (
            utc_now()
        )

        db.session.commit()

        # ----------------------------------------------------
        # ACTIVE
        # ----------------------------------------------------

        if (
            creator.account_status
            == "active"
            and creator.subscription_status
            == "active"
        ):

            flash(
                "Welcome back.",
                "success",
            )

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

    return render_template(
        "creator/login.html"
    )


# ============================================================
# PENDING / ACCOUNT STATUS
# ============================================================

@creator_auth_bp.route(
    "/pending"
)
@creator_login_required
def pending():

    creator = (
        get_logged_in_creator()
    )

    if (
        creator.account_status
        == "active"
        and creator.subscription_status
        == "active"
    ):

        return redirect(
            url_for(
                "studio.dashboard"
            )
        )

    return render_template(
        "creator/pending.html",
        creator_account=creator,
        selected_plan=normalize_plan(
            creator.plan,
            default=PLAN_PREMIUM,
        ),
        plan_prices=PLAN_PRICES,
    )


# ============================================================
# LOGOUT
# ============================================================

@creator_auth_bp.route(
    "/logout",
    methods=["POST"],
)
@creator_login_required
def logout():

    session.pop(
        "creator_account_id",
        None,
    )

    flash(
        "You have been signed out.",
        "success",
    )

    return redirect(
        url_for(
            "creator_auth.login"
        )
    )
