# ============================================================
# CREATOR PLATFORM
# PLATFORM ADMIN ROUTES
# ============================================================

from datetime import (
    datetime,
    timezone,
    timedelta,
)
from functools import wraps

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    abort,
)

from extensions import db

from models import (
    AdminUser,
    CreatorAccount,
    CreatorProfile,
    ContentCategory,
    ContentPost,
    Comment,
    EmailSubscriber,
    EmailDelivery,
)


# ============================================================
# BLUEPRINT
# ============================================================

admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
)


# ============================================================
# CONSTANTS
# ============================================================

ACCOUNT_STATUSES = {
    "pending_payment",
    "pending_approval",
    "active",
    "suspended",
    "rejected",
}

PAYMENT_STATUSES = {
    "unpaid",
    "paid",
}

SUBSCRIPTION_STATUSES = {
    "inactive",
    "active",
    "past_due",
    "expired",
    "cancelled",
}


# ============================================================
# HELPERS
# ============================================================

def utc_now():
    """
    Return current timezone-aware UTC datetime.
    """

    return datetime.now(
        timezone.utc
    )


def normalize_identity(value):
    """
    Normalize username/email login input.
    """

    return (
        value
        .strip()
        .lower()
    )


def current_admin():
    """
    Return the currently logged-in platform admin.
    """

    admin_id = session.get(
        "admin_user_id"
    )

    if not admin_id:
        return None

    return db.session.get(
        AdminUser,
        admin_id,
    )


def creator_or_404(
    creator_id,
):
    """
    Load a CreatorAccount or return 404.
    """

    creator = db.session.get(
        CreatorAccount,
        creator_id,
    )

    if not creator:
        abort(404)

    return creator


def creator_profile(
    creator,
):
    """
    Return profile belonging to creator account.
    """

    return (
        CreatorProfile.query
        .filter_by(
            creator_account_id=creator.id
        )
        .first()
    )


def normalize_datetime_utc(
    value,
):
    """
    PostgreSQL usually returns timezone-aware values for
    timezone=True columns.

    This helper also safely handles any older naive values.
    """

    if value is None:
        return None

    if value.tzinfo is None:

        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def creator_subscription_is_current(
    creator,
):
    """
    Check whether the creator currently has an active
    platform subscription.

    subscription_expires_at=None means no expiry has been
    assigned yet.
    """

    if (
        creator.subscription_status
        != "active"
    ):
        return False

    expires_at = normalize_datetime_utc(
        creator.subscription_expires_at
    )

    if expires_at is None:
        return True

    return expires_at > utc_now()


# ============================================================
# ADMIN AUTHENTICATION
# ============================================================

def admin_required(view):
    """
    Protect platform administration routes.
    """

    @wraps(view)
    def wrapped_view(
        *args,
        **kwargs,
    ):

        admin = current_admin()

        if not admin:

            session.pop(
                "admin_user_id",
                None,
            )

            flash(
                "Please sign in to continue.",
                "warning",
            )

            return redirect(
                url_for(
                    "admin.login"
                )
            )

        if not admin.is_active:

            session.clear()

            flash(
                "Your admin account is disabled.",
                "warning",
            )

            return redirect(
                url_for(
                    "admin.login"
                )
            )

        return view(
            *args,
            **kwargs,
        )

    return wrapped_view


# ============================================================
# LOGIN
# ============================================================

@admin_bp.route(
    "/login",
    methods=[
        "GET",
        "POST",
    ],
)
def login():

    existing_admin = (
        current_admin()
    )

    if (
        existing_admin
        and existing_admin.is_active
    ):

        return redirect(
            url_for(
                "admin.dashboard"
            )
        )

    if request.method == "POST":

        identity = normalize_identity(
            request.form.get(
                "identity",
                "",
            )
        )

        password = (
            request.form.get(
                "password",
                "",
            )
        )

        if (
            not identity
            or not password
        ):

            flash(
                "Enter your username/email and password.",
                "error",
            )

            return render_template(
                "admin/login.html"
            )

        admin = (
            AdminUser.query
            .filter(
                db.or_(
                    db.func.lower(
                        AdminUser.username
                    )
                    == identity,

                    db.func.lower(
                        AdminUser.email
                    )
                    == identity,
                )
            )
            .first()
        )

        if (
            not admin
            or not admin.is_active
            or not admin.check_password(
                password
            )
        ):

            flash(
                "Invalid login details.",
                "error",
            )

            return render_template(
                "admin/login.html"
            )

        # ----------------------------------------------------
        # START CLEAN ADMIN SESSION
        # ----------------------------------------------------

        session.clear()

        session[
            "admin_user_id"
        ] = admin.id

        admin.last_login_at = (
            utc_now()
        )

        db.session.commit()

        flash(
            "Welcome to the platform control centre.",
            "success",
        )

        return redirect(
            url_for(
                "admin.dashboard"
            )
        )

    return render_template(
        "admin/login.html"
    )


# ============================================================
# LOGOUT
# ============================================================

@admin_bp.route(
    "/logout",
    methods=["POST"],
)
@admin_required
def logout():

    session.clear()

    flash(
        "You have been signed out.",
        "success",
    )

    return redirect(
        url_for(
            "admin.login"
        )
    )


# ============================================================
# PLATFORM DASHBOARD
# ============================================================

@admin_bp.route("/")
@admin_required
def dashboard():

    # ========================================================
    # CREATOR COUNTS
    # ========================================================

    total_creators = (
        CreatorAccount.query
        .count()
    )

    active_creators = (
        CreatorAccount.query
        .filter_by(
            account_status="active"
        )
        .count()
    )

    pending_payment_creators = (
        CreatorAccount.query
        .filter_by(
            account_status="pending_payment"
        )
        .count()
    )

    pending_approval_creators = (
        CreatorAccount.query
        .filter_by(
            account_status="pending_approval"
        )
        .count()
    )

    suspended_creators = (
        CreatorAccount.query
        .filter_by(
            account_status="suspended"
        )
        .count()
    )

    rejected_creators = (
        CreatorAccount.query
        .filter_by(
            account_status="rejected"
        )
        .count()
    )

    # ========================================================
    # PAYMENT COUNTS
    # ========================================================

    paid_creators = (
        CreatorAccount.query
        .filter_by(
            payment_status="paid"
        )
        .count()
    )

    unpaid_creators = (
        CreatorAccount.query
        .filter_by(
            payment_status="unpaid"
        )
        .count()
    )

    # ========================================================
    # SUBSCRIPTION COUNTS
    # ========================================================

    active_subscriptions = (
        CreatorAccount.query
        .filter_by(
            subscription_status="active"
        )
        .count()
    )

    inactive_subscriptions = (
        CreatorAccount.query
        .filter(
            CreatorAccount
            .subscription_status
            != "active"
        )
        .count()
    )

    expiring_soon_at = (
        utc_now()
        + timedelta(
            days=7
        )
    )

    expiring_soon = (
        CreatorAccount.query
        .filter(
            CreatorAccount.subscription_status
            == "active",

            CreatorAccount.subscription_expires_at
            .isnot(None),

            CreatorAccount.subscription_expires_at
            > utc_now(),

            CreatorAccount.subscription_expires_at
            <= expiring_soon_at,
        )
        .count()
    )

    # ========================================================
    # PLATFORM ACTIVITY
    # ========================================================

    total_posts = (
        ContentPost.query
        .count()
    )

    published_posts = (
        ContentPost.query
        .filter_by(
            status="published"
        )
        .count()
    )

    total_subscribers = (
        EmailSubscriber.query
        .count()
    )

    active_email_subscribers = (
        EmailSubscriber.query
        .filter_by(
            status="active"
        )
        .count()
    )

    total_comments = (
        Comment.query
        .count()
    )

    # ========================================================
    # RECENT CREATORS
    # ========================================================

    recent_creators = (
        CreatorAccount.query
        .order_by(
            CreatorAccount.created_at.desc()
        )
        .limit(10)
        .all()
    )

    return render_template(
        "admin/dashboard.html",

        admin=current_admin(),

        # Creator accounts
        total_creators=total_creators,
        active_creators=active_creators,
        pending_payment_creators=(
            pending_payment_creators
        ),
        pending_approval_creators=(
            pending_approval_creators
        ),
        suspended_creators=(
            suspended_creators
        ),
        rejected_creators=(
            rejected_creators
        ),

        # Payments
        paid_creators=paid_creators,
        unpaid_creators=unpaid_creators,

        # SaaS subscriptions
        active_subscriptions=(
            active_subscriptions
        ),
        inactive_subscriptions=(
            inactive_subscriptions
        ),
        expiring_soon=expiring_soon,

        # Platform activity
        total_posts=total_posts,
        published_posts=published_posts,
        total_subscribers=(
            total_subscribers
        ),
        active_email_subscribers=(
            active_email_subscribers
        ),
        total_comments=total_comments,

        recent_creators=recent_creators,
    )


# ============================================================
# CREATOR LIST
# ============================================================

@admin_bp.route(
    "/creators"
)
@admin_required
def creators():

    account_status = (
        request.args
        .get(
            "status",
            "",
        )
        .strip()
        .lower()
    )

    payment_status = (
        request.args
        .get(
            "payment",
            "",
        )
        .strip()
        .lower()
    )

    subscription_status = (
        request.args
        .get(
            "subscription",
            "",
        )
        .strip()
        .lower()
    )

    search = (
        request.args
        .get(
            "q",
            "",
        )
        .strip()
    )

    query = CreatorAccount.query

    # ========================================================
    # ACCOUNT STATUS
    # ========================================================

    if (
        account_status
        in ACCOUNT_STATUSES
    ):

        query = query.filter(
            CreatorAccount.account_status
            == account_status
        )

    # ========================================================
    # PAYMENT STATUS
    # ========================================================

    if (
        payment_status
        in PAYMENT_STATUSES
    ):

        query = query.filter(
            CreatorAccount.payment_status
            == payment_status
        )

    # ========================================================
    # SUBSCRIPTION STATUS
    # ========================================================

    if (
        subscription_status
        in SUBSCRIPTION_STATUSES
    ):

        query = query.filter(
            CreatorAccount.subscription_status
            == subscription_status
        )

    # ========================================================
    # SEARCH
    # ========================================================

    if search:

        search_value = (
            f"%{search.lower()}%"
        )

        query = (
            query
            .outerjoin(
                CreatorProfile,
                CreatorProfile.creator_account_id
                == CreatorAccount.id,
            )
            .filter(
                db.or_(
                    db.func.lower(
                        CreatorAccount.username
                    ).like(
                        search_value
                    ),

                    db.func.lower(
                        CreatorAccount.email
                    ).like(
                        search_value
                    ),

                    db.func.lower(
                        CreatorProfile.display_name
                    ).like(
                        search_value
                    ),
                )
            )
        )

    creator_items = (
        query
        .order_by(
            CreatorAccount.created_at.desc()
        )
        .all()
    )

    return render_template(
        "admin/creators.html",

        creators=creator_items,

        selected_status=(
            account_status
        ),

        selected_payment=(
            payment_status
        ),

        selected_subscription=(
            subscription_status
        ),

        search=search,
    )


# ============================================================
# CREATOR DETAIL
# ============================================================

@admin_bp.route(
    "/creators/<int:creator_id>"
)
@admin_required
def creator_detail(
    creator_id,
):

    creator = creator_or_404(
        creator_id
    )

    profile = creator_profile(
        creator
    )

    # ========================================================
    # CONTENT COUNTS
    # ========================================================

    post_query = (
        ContentPost.query
        .filter_by(
            creator_account_id=creator.id
        )
    )

    total_posts = (
        post_query.count()
    )

    published_posts = (
        post_query
        .filter_by(
            status="published"
        )
        .count()
    )

    draft_posts = (
        post_query
        .filter_by(
            status="draft"
        )
        .count()
    )

    exclusive_posts = (
        post_query
        .filter_by(
            access_level="subscriber"
        )
        .count()
    )

    # ========================================================
    # CATEGORY COUNT
    # ========================================================

    category_count = (
        ContentCategory.query
        .filter_by(
            creator_account_id=creator.id
        )
        .count()
    )

    # ========================================================
    # SUBSCRIBERS
    # ========================================================

    subscriber_query = (
        EmailSubscriber.query
        .filter_by(
            creator_account_id=creator.id
        )
    )

    subscriber_count = (
        subscriber_query.count()
    )

    active_subscriber_count = (
        subscriber_query
        .filter_by(
            status="active"
        )
        .count()
    )

    # ========================================================
    # COMMENTS
    # ========================================================

    comment_count = (
        Comment.query
        .join(
            ContentPost,
            Comment.post_id
            == ContentPost.id,
        )
        .filter(
            ContentPost.creator_account_id
            == creator.id
        )
        .count()
    )

    # ========================================================
    # EMAIL DELIVERY
    # ========================================================

    email_delivery_count = (
        EmailDelivery.query
        .join(
            EmailSubscriber,
            EmailDelivery.subscriber_id
            == EmailSubscriber.id,
        )
        .filter(
            EmailSubscriber.creator_account_id
            == creator.id
        )
        .count()
    )

    # ========================================================
    # RECENT CONTENT
    # ========================================================

    recent_posts = (
        post_query
        .order_by(
            ContentPost.created_at.desc()
        )
        .limit(10)
        .all()
    )

    subscription_is_current = (
        creator_subscription_is_current(
            creator
        )
    )

    return render_template(
        "admin/creator_detail.html",

        creator=creator,
        profile=profile,

        total_posts=total_posts,
        published_posts=published_posts,
        draft_posts=draft_posts,
        exclusive_posts=exclusive_posts,

        category_count=category_count,

        subscriber_count=(
            subscriber_count
        ),
        active_subscriber_count=(
            active_subscriber_count
        ),

        comment_count=comment_count,

        email_delivery_count=(
            email_delivery_count
        ),

        recent_posts=recent_posts,

        subscription_is_current=(
            subscription_is_current
        ),
    )


# ============================================================
# MARK REGISTRATION PAYMENT AS PAID
# ============================================================

@admin_bp.route(
    "/creators/<int:creator_id>/mark-paid",
    methods=["POST"],
)
@admin_required
def creator_mark_paid(
    creator_id,
):

    creator = creator_or_404(
        creator_id
    )

    # --------------------------------------------------------
    # DO NOT ALTER REJECTED ACCOUNTS
    # --------------------------------------------------------

    if (
        creator.account_status
        == "rejected"
    ):

        flash(
            "A rejected creator cannot be marked "
            "as ready for approval.",
            "warning",
        )

        return redirect(
            url_for(
                "admin.creator_detail",
                creator_id=creator.id,
            )
        )

    creator.payment_status = "paid"

    if not creator.registration_paid_at:

        creator.registration_paid_at = (
            utc_now()
        )

    # --------------------------------------------------------
    # PAYMENT COMPLETED
    # --------------------------------------------------------
    #
    # Creator now waits for platform approval.
    # --------------------------------------------------------

    if (
        creator.account_status
        == "pending_payment"
    ):

        creator.account_status = (
            "pending_approval"
        )

    db.session.commit()

    flash(
        f"Registration payment for "
        f"@{creator.username} was marked as paid.",
        "success",
    )

    return redirect(
        url_for(
            "admin.creator_detail",
            creator_id=creator.id,
        )
    )


# ============================================================
# MARK REGISTRATION PAYMENT AS UNPAID
# ============================================================

@admin_bp.route(
    "/creators/<int:creator_id>/mark-unpaid",
    methods=["POST"],
)
@admin_required
def creator_mark_unpaid(
    creator_id,
):

    creator = creator_or_404(
        creator_id
    )

    if (
        creator.account_status
        == "active"
    ):

        flash(
            "An active creator cannot be moved back "
            "to registration payment automatically.",
            "warning",
        )

        return redirect(
            url_for(
                "admin.creator_detail",
                creator_id=creator.id,
            )
        )

    creator.payment_status = "unpaid"

    creator.registration_paid_at = None

    if (
        creator.account_status
        not in {
            "suspended",
            "rejected",
        }
    ):

        creator.account_status = (
            "pending_payment"
        )

    db.session.commit()

    flash(
        f"@{creator.username} was marked as unpaid.",
        "success",
    )

    return redirect(
        url_for(
            "admin.creator_detail",
            creator_id=creator.id,
        )
    )


# ============================================================
# APPROVE CREATOR
# ============================================================

@admin_bp.route(
    "/creators/<int:creator_id>/approve",
    methods=["POST"],
)
@admin_required
def creator_approve(
    creator_id,
):

    creator = creator_or_404(
        creator_id
    )

    # --------------------------------------------------------
    # REGISTRATION MUST BE PAID FIRST
    # --------------------------------------------------------

    if (
        creator.payment_status
        != "paid"
    ):

        flash(
            "Registration payment must be marked "
            "as paid before approval.",
            "error",
        )

        return redirect(
            url_for(
                "admin.creator_detail",
                creator_id=creator.id,
            )
        )

    if (
        creator.account_status
        == "rejected"
    ):

        flash(
            "This creator was rejected. Reactivate the "
            "account instead if you want to restore it.",
            "warning",
        )

        return redirect(
            url_for(
                "admin.creator_detail",
                creator_id=creator.id,
            )
        )

    creator.account_status = "active"

    if not creator.approved_at:

        creator.approved_at = (
            utc_now()
        )

    # --------------------------------------------------------
    # MVP BEHAVIOUR
    # --------------------------------------------------------
    #
    # Approval activates the creator's platform access.
    #
    # Later Yoco can replace this manual activation.
    # --------------------------------------------------------

    creator.subscription_status = (
        "active"
    )

    if not creator.subscription_started_at:

        creator.subscription_started_at = (
            utc_now()
        )

    # --------------------------------------------------------
    # INITIAL 30-DAY PERIOD
    # --------------------------------------------------------
    #
    # If the legacy/backfilled creator already has no expiry,
    # preserve that state.
    #
    # New creator accounts receive 30 days.
    # --------------------------------------------------------

    if (
        creator.subscription_expires_at
        is None
        and creator.created_at
        and creator.approved_at
    ):

        creator.subscription_expires_at = (
            utc_now()
            + timedelta(
                days=30
            )
        )

    db.session.commit()

    flash(
        f"@{creator.username} has been approved "
        f"and can access Creator Studio.",
        "success",
    )

    return redirect(
        url_for(
            "admin.creator_detail",
            creator_id=creator.id,
        )
    )


# ============================================================
# REJECT CREATOR
# ============================================================

@admin_bp.route(
    "/creators/<int:creator_id>/reject",
    methods=["POST"],
)
@admin_required
def creator_reject(
    creator_id,
):

    creator = creator_or_404(
        creator_id
    )

    if (
        creator.account_status
        == "active"
    ):

        flash(
            "An active creator should be suspended "
            "instead of rejected.",
            "warning",
        )

        return redirect(
            url_for(
                "admin.creator_detail",
                creator_id=creator.id,
            )
        )

    creator.account_status = (
        "rejected"
    )

    creator.subscription_status = (
        "inactive"
    )

    db.session.commit()

    flash(
        f"@{creator.username} was rejected.",
        "success",
    )

    return redirect(
        url_for(
            "admin.creator_detail",
            creator_id=creator.id,
        )
    )


# ============================================================
# SUSPEND CREATOR
# ============================================================

@admin_bp.route(
    "/creators/<int:creator_id>/suspend",
    methods=["POST"],
)
@admin_required
def creator_suspend(
    creator_id,
):

    creator = creator_or_404(
        creator_id
    )

    if (
        creator.account_status
        != "active"
    ):

        flash(
            "Only an active creator can be suspended.",
            "warning",
        )

        return redirect(
            url_for(
                "admin.creator_detail",
                creator_id=creator.id,
            )
        )

    creator.account_status = (
        "suspended"
    )

    db.session.commit()

    flash(
        f"@{creator.username} has been suspended.",
        "success",
    )

    return redirect(
        url_for(
            "admin.creator_detail",
            creator_id=creator.id,
        )
    )


# ============================================================
# REACTIVATE CREATOR
# ============================================================

@admin_bp.route(
    "/creators/<int:creator_id>/reactivate",
    methods=["POST"],
)
@admin_required
def creator_reactivate(
    creator_id,
):

    creator = creator_or_404(
        creator_id
    )

    if (
        creator.payment_status
        != "paid"
    ):

        flash(
            "The creator's registration payment must "
            "be paid before reactivation.",
            "error",
        )

        return redirect(
            url_for(
                "admin.creator_detail",
                creator_id=creator.id,
            )
        )

    creator.account_status = (
        "active"
    )

    if not creator.approved_at:

        creator.approved_at = (
            utc_now()
        )

    db.session.commit()

    flash(
        f"@{creator.username} has been reactivated.",
        "success",
    )

    return redirect(
        url_for(
            "admin.creator_detail",
            creator_id=creator.id,
        )
    )


# ============================================================
# ACTIVATE SUBSCRIPTION
# ============================================================

@admin_bp.route(
    "/creators/<int:creator_id>/subscription/activate",
    methods=["POST"],
)
@admin_required
def creator_subscription_activate(
    creator_id,
):

    creator = creator_or_404(
        creator_id
    )

    if (
        creator.account_status
        != "active"
    ):

        flash(
            "The creator account must be active "
            "before activating its subscription.",
            "error",
        )

        return redirect(
            url_for(
                "admin.creator_detail",
                creator_id=creator.id,
            )
        )

    now = utc_now()

    creator.subscription_status = (
        "active"
    )

    if not creator.subscription_started_at:

        creator.subscription_started_at = (
            now
        )

    expires_at = normalize_datetime_utc(
        creator.subscription_expires_at
    )

    # --------------------------------------------------------
    # NEW / EXPIRED SUBSCRIPTION
    # --------------------------------------------------------

    if (
        expires_at is None
        or expires_at <= now
    ):

        creator.subscription_expires_at = (
            now
            + timedelta(
                days=30
            )
        )

    db.session.commit()

    flash(
        f"@{creator.username}'s platform "
        f"subscription is active.",
        "success",
    )

    return redirect(
        url_for(
            "admin.creator_detail",
            creator_id=creator.id,
        )
    )


# ============================================================
# EXTEND SUBSCRIPTION
# ============================================================

@admin_bp.route(
    "/creators/<int:creator_id>/subscription/extend",
    methods=["POST"],
)
@admin_required
def creator_subscription_extend(
    creator_id,
):

    creator = creator_or_404(
        creator_id
    )

    if (
        creator.account_status
        != "active"
    ):

        flash(
            "The creator account must be active "
            "before extending its subscription.",
            "error",
        )

        return redirect(
            url_for(
                "admin.creator_detail",
                creator_id=creator.id,
            )
        )

    days = request.form.get(
        "days",
        default=30,
        type=int,
    )

    if (
        days is None
        or days < 1
        or days > 365
    ):

        flash(
            "Subscription extension must be "
            "between 1 and 365 days.",
            "error",
        )

        return redirect(
            url_for(
                "admin.creator_detail",
                creator_id=creator.id,
            )
        )

    now = utc_now()

    expires_at = normalize_datetime_utc(
        creator.subscription_expires_at
    )

    if (
        expires_at
        and expires_at > now
    ):

        start_from = expires_at

    else:

        start_from = now

    creator.subscription_status = (
        "active"
    )

    if not creator.subscription_started_at:

        creator.subscription_started_at = (
            now
        )

    creator.subscription_expires_at = (
        start_from
        + timedelta(
            days=days
        )
    )

    db.session.commit()

    flash(
        f"@{creator.username}'s subscription "
        f"was extended by {days} days.",
        "success",
    )

    return redirect(
        url_for(
            "admin.creator_detail",
            creator_id=creator.id,
        )
    )


# ============================================================
# EXPIRE SUBSCRIPTION
# ============================================================

@admin_bp.route(
    "/creators/<int:creator_id>/subscription/expire",
    methods=["POST"],
)
@admin_required
def creator_subscription_expire(
    creator_id,
):

    creator = creator_or_404(
        creator_id
    )

    creator.subscription_status = (
        "expired"
    )

    creator.subscription_expires_at = (
        utc_now()
    )

    db.session.commit()

    flash(
        f"@{creator.username}'s subscription "
        f"has been marked as expired.",
        "success",
    )

    return redirect(
        url_for(
            "admin.creator_detail",
            creator_id=creator.id,
        )
    )


# ============================================================
# CANCEL SUBSCRIPTION
# ============================================================

@admin_bp.route(
    "/creators/<int:creator_id>/subscription/cancel",
    methods=["POST"],
)
@admin_required
def creator_subscription_cancel(
    creator_id,
):

    creator = creator_or_404(
        creator_id
    )

    creator.subscription_status = (
        "cancelled"
    )

    db.session.commit()

    flash(
        f"@{creator.username}'s platform "
        f"subscription was cancelled.",
        "success",
    )

    return redirect(
        url_for(
            "admin.creator_detail",
            creator_id=creator.id,
        )
    )


# ============================================================
# PLATFORM ANALYTICS
# ============================================================

@admin_bp.route(
    "/analytics"
)
@admin_required
def analytics():

    # ========================================================
    # CREATOR ACCOUNTS
    # ========================================================

    total_creators = (
        CreatorAccount.query
        .count()
    )

    active_creators = (
        CreatorAccount.query
        .filter_by(
            account_status="active"
        )
        .count()
    )

    pending_payment_creators = (
        CreatorAccount.query
        .filter_by(
            account_status="pending_payment"
        )
        .count()
    )

    pending_approval_creators = (
        CreatorAccount.query
        .filter_by(
            account_status="pending_approval"
        )
        .count()
    )

    suspended_creators = (
        CreatorAccount.query
        .filter_by(
            account_status="suspended"
        )
        .count()
    )

    rejected_creators = (
        CreatorAccount.query
        .filter_by(
            account_status="rejected"
        )
        .count()
    )

    # ========================================================
    # PLATFORM SUBSCRIPTIONS
    # ========================================================

    active_subscriptions = (
        CreatorAccount.query
        .filter_by(
            subscription_status="active"
        )
        .count()
    )

    expired_subscriptions = (
        CreatorAccount.query
        .filter_by(
            subscription_status="expired"
        )
        .count()
    )

    cancelled_subscriptions = (
        CreatorAccount.query
        .filter_by(
            subscription_status="cancelled"
        )
        .count()
    )

    past_due_subscriptions = (
        CreatorAccount.query
        .filter_by(
            subscription_status="past_due"
        )
        .count()
    )

    # ========================================================
    # CONTENT
    # ========================================================

    total_posts = (
        ContentPost.query
        .count()
    )

    published_posts = (
        ContentPost.query
        .filter_by(
            status="published"
        )
        .count()
    )

    draft_posts = (
        ContentPost.query
        .filter_by(
            status="draft"
        )
        .count()
    )

    archived_posts = (
        ContentPost.query
        .filter_by(
            status="archived"
        )
        .count()
    )

    story_count = (
        ContentPost.query
        .filter_by(
            content_type="story"
        )
        .count()
    )

    reel_count = (
        ContentPost.query
        .filter_by(
            content_type="reel"
        )
        .count()
    )

    vlog_count = (
        ContentPost.query
        .filter_by(
            content_type="vlog"
        )
        .count()
    )

    public_posts = (
        ContentPost.query
        .filter_by(
            access_level="public"
        )
        .count()
    )

    exclusive_posts = (
        ContentPost.query
        .filter_by(
            access_level="subscriber"
        )
        .count()
    )

    # ========================================================
    # COMMENTS
    # ========================================================

    comment_count = (
        Comment.query
        .count()
    )

    approved_comment_count = (
        Comment.query
        .filter_by(
            status="approved"
        )
        .count()
    )

    pending_comment_count = (
        Comment.query
        .filter_by(
            status="pending"
        )
        .count()
    )

    hidden_comment_count = (
        Comment.query
        .filter_by(
            status="hidden"
        )
        .count()
    )

    # ========================================================
    # NEWSLETTER
    # ========================================================

    subscriber_count = (
        EmailSubscriber.query
        .count()
    )

    active_subscriber_count = (
        EmailSubscriber.query
        .filter_by(
            status="active"
        )
        .count()
    )

    pending_subscriber_count = (
        EmailSubscriber.query
        .filter_by(
            status="pending"
        )
        .count()
    )

    unsubscribed_count = (
        EmailSubscriber.query
        .filter_by(
            status="unsubscribed"
        )
        .count()
    )

    # ========================================================
    # EMAIL
    # ========================================================

    total_email_deliveries = (
        EmailDelivery.query
        .count()
    )

    sent_email_count = (
        EmailDelivery.query
        .filter_by(
            status="sent"
        )
        .count()
    )

    failed_email_count = (
        EmailDelivery.query
        .filter_by(
            status="failed"
        )
        .count()
    )

    # ========================================================
    # MOST ACTIVE CREATORS BY POST COUNT
    # ========================================================

    most_active_creators = (
        db.session.query(
            CreatorAccount,
            db.func.count(
                ContentPost.id
            ).label(
                "post_total"
            ),
        )
        .outerjoin(
            ContentPost,
            ContentPost.creator_account_id
            == CreatorAccount.id,
        )
        .group_by(
            CreatorAccount.id
        )
        .order_by(
            db.func.count(
                ContentPost.id
            ).desc(),
            CreatorAccount.created_at.desc(),
        )
        .limit(10)
        .all()
    )

    # ========================================================
    # MOST DISCUSSED POSTS
    # ========================================================

    most_commented_posts = (
        db.session.query(
            ContentPost,
            db.func.count(
                Comment.id
            ).label(
                "comment_total"
            ),
        )
        .outerjoin(
            Comment,
            Comment.post_id
            == ContentPost.id,
        )
        .group_by(
            ContentPost.id
        )
        .order_by(
            db.func.count(
                Comment.id
            ).desc(),
            ContentPost.created_at.desc(),
        )
        .limit(10)
        .all()
    )

    # ========================================================
    # RECENT CREATORS
    # ========================================================

    recent_creators = (
        CreatorAccount.query
        .order_by(
            CreatorAccount.created_at.desc()
        )
        .limit(10)
        .all()
    )

    return render_template(
        "admin/analytics.html",

        # Creators
        total_creators=total_creators,
        active_creators=active_creators,
        pending_payment_creators=(
            pending_payment_creators
        ),
        pending_approval_creators=(
            pending_approval_creators
        ),
        suspended_creators=(
            suspended_creators
        ),
        rejected_creators=(
            rejected_creators
        ),

        # SaaS subscriptions
        active_subscriptions=(
            active_subscriptions
        ),
        expired_subscriptions=(
            expired_subscriptions
        ),
        cancelled_subscriptions=(
            cancelled_subscriptions
        ),
        past_due_subscriptions=(
            past_due_subscriptions
        ),

        # Content
        total_posts=total_posts,
        published_posts=published_posts,
        draft_posts=draft_posts,
        archived_posts=archived_posts,

        story_count=story_count,
        reel_count=reel_count,
        vlog_count=vlog_count,

        public_posts=public_posts,
        exclusive_posts=exclusive_posts,

        # Comments
        comment_count=comment_count,
        approved_comment_count=(
            approved_comment_count
        ),
        pending_comment_count=(
            pending_comment_count
        ),
        hidden_comment_count=(
            hidden_comment_count
        ),

        # Newsletter
        subscriber_count=subscriber_count,
        active_subscriber_count=(
            active_subscriber_count
        ),
        pending_subscriber_count=(
            pending_subscriber_count
        ),
        unsubscribed_count=(
            unsubscribed_count
        ),

        # Email
        total_email_deliveries=(
            total_email_deliveries
        ),
        sent_email_count=(
            sent_email_count
        ),
        failed_email_count=(
            failed_email_count
        ),

        # Activity
        most_active_creators=(
            most_active_creators
        ),
        most_commented_posts=(
            most_commented_posts
        ),
        recent_creators=recent_creators,
    )
