# ============================================================
# CREATOR PLATFORM
# CREATOR STUDIO
# ============================================================

import re

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps


from services.paystack_service import (
    PaystackError,
    list_south_african_banks,
    validate_south_african_account,
    create_creator_subaccount,
)

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    abort,
    current_app,
    g,
)

from extensions import db

from models import (
    CreatorAccount,
    CreatorProfile,
    CreatorPayoutAccount,
    FundraisingCampaign,
    FanPayment,
    ContentCategory,
    ContentPost,
    ContentMedia,
    Comment,
    EmailSubscriber,
    EmailDelivery,
)

from services.subscription_service import (
    creator_subscription_is_current,
    enforce_subscription_lifecycle,
    creator_grace_days_remaining,
)

from services.cloudinary_service import (
    upload_image,
    upload_video,
    delete_media,
    validate_image,
    validate_video,
)

from services.email_service import (
    notify_subscribers_about_post,
)

from services.plan_service import (
    FEATURE_EXCLUSIVE_CONTENT,
    FEATURE_FAN_SUPPORT,
    FEATURE_PAYOUT_CONNECTION,
    FEATURE_FUNDRAISING,
    FEATURE_PAID_MEMBERSHIPS,
    creator_has_feature,
    creator_missing_feature_message,
    creator_plan_summary,
)


# ============================================================
# BLUEPRINT
# ============================================================

studio_bp = Blueprint(
    "studio",
    __name__,
    url_prefix="/studio",
)


# ============================================================
# HELPERS
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    )


def current_creator_account():

    creator_id = session.get(
        "creator_account_id"
    )

    if not creator_id:

        return None

    return db.session.get(
        CreatorAccount,
        creator_id,
    )


# ============================================================
# STUDIO ACCESS
# ============================================================

def studio_required(view):

    @wraps(view)
    def wrapped_view(
        *args,
        **kwargs,
    ):

        creator = (
            current_creator_account()
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

        if (
            creator.account_status
            != "active"
        ):

            return redirect(
                url_for(
                    "creator_auth.pending"
                )
            )

        try:

            subscription = (
                enforce_subscription_lifecycle(
                    creator
                )
            )

            db.session.commit()

        except Exception:

            db.session.rollback()

            current_app.logger.exception(
                (
                    "Unable to enforce creator "
                    "subscription lifecycle. "
                    "creator_account_id=%s"
                ),
                creator.id,
            )

            flash(
                (
                    "We could not verify your "
                    "subscription right now. "
                    "Please try again."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "creator_auth.pending"
                )
            )

        g.creator_subscription = (
            subscription
        )

        g.creator_subscription_status = (
            subscription.status
            if subscription
            else (
                creator.subscription_status
                or "inactive"
            )
        )

        g.creator_grace_days_remaining = (
            creator_grace_days_remaining(
                creator
            )
        )

        if not creator_subscription_is_current(
            creator
        ):

            subscription_status = (
                g.creator_subscription_status
            )

            if subscription_status == "expired":

                flash(
                    (
                        "Your subscription has expired. "
                        "Your public creator page and "
                        "content are still online. "
                        "Renew your subscription to "
                        "continue using Creator Studio."
                    ),
                    "warning",
                )

            elif subscription_status == "cancelled":

                flash(
                    (
                        "Your subscription is no longer "
                        "active. Renew your subscription "
                        "to continue using Creator Studio."
                    ),
                    "warning",
                )

            else:

                flash(
                    (
                        "An active subscription is "
                        "required to use Creator Studio."
                    ),
                    "warning",
                )

            return redirect(
                url_for(
                    "creator_auth.pending"
                )
            )

        if (
            g.creator_subscription_status
            == "past_due"
        ):

            current_app.logger.info(
                (
                    "Creator using Studio during "
                    "subscription grace period. "
                    "creator_account_id=%s "
                    "days_remaining=%s"
                ),
                creator.id,
                g.creator_grace_days_remaining,
            )

        return view(
            *args,
            **kwargs,
        )

    return wrapped_view


# ============================================================
# FEATURE ACCESS
# ============================================================

def require_creator_feature(
    creator,
    feature,
):

    if creator_has_feature(
        creator,
        feature,
    ):

        return True

    flash(
        creator_missing_feature_message(
            feature
        ),
        "warning",
    )

    return False


# ============================================================
# CREATOR PROFILE
# ============================================================

def creator_profile(
    creator,
):

    return (
        CreatorProfile.query
        .filter_by(
            creator_account_id=creator.id
        )
        .first()
    )


# ============================================================
# CREATOR PAYOUT ACCOUNT
# ============================================================

def creator_payout_account(
    creator,
):

    return (
        CreatorPayoutAccount.query
        .filter_by(
            creator_account_id=creator.id
        )
        .first()
    )


# ============================================================
# TENANT-SCOPED FUNDRAISING CAMPAIGN
# ============================================================

def creator_campaign_or_404(
    creator,
    campaign_id,
):

    return (
        FundraisingCampaign.query
        .filter_by(
            id=campaign_id,
            creator_account_id=creator.id,
        )
        .first_or_404()
    )


# ============================================================
# TENANT-SCOPED POST
# ============================================================

def creator_post_or_404(
    creator,
    post_id,
):

    return (
        ContentPost.query
        .filter_by(
            id=post_id,
            creator_account_id=creator.id,
        )
        .first_or_404()
    )


# ============================================================
# TENANT-SCOPED CATEGORY
# ============================================================

def creator_category_or_404(
    creator,
    category_id,
):

    return (
        ContentCategory.query
        .filter_by(
            id=category_id,
            creator_account_id=creator.id,
        )
        .first_or_404()
    )


# ============================================================
# TENANT-SCOPED COMMENT
# ============================================================

def creator_comment_or_404(
    creator,
    comment_id,
):

    return (
        Comment.query
        .join(
            ContentPost,
            Comment.post_id
            == ContentPost.id,
        )
        .filter(
            Comment.id == comment_id,
            ContentPost.creator_account_id
            == creator.id,
        )
        .first_or_404()
    )


# ============================================================
# SLUGIFY
# ============================================================

def slugify(
    value,
):

    value = (
        value
        .strip()
        .lower()
    )

    value = re.sub(
        r"[^a-z0-9]+",
        "-",
        value,
    )

    return value.strip("-")


# ============================================================
# UNIQUE POST SLUG
# ============================================================

def unique_post_slug(
    creator,
    title,
    post_id=None,
):

    base_slug = slugify(title) or "post"

    candidate = base_slug
    counter = 2

    while True:

        query = (
            ContentPost.query
            .filter_by(
                creator_account_id=creator.id,
                slug=candidate,
            )
        )

        if post_id is not None:

            query = query.filter(
                ContentPost.id != post_id
            )

        if not query.first():

            return candidate

        candidate = (
            f"{base_slug}-{counter}"
        )

        counter += 1


# ============================================================
# UNIQUE CATEGORY SLUG
# ============================================================

def unique_category_slug(
    creator,
    name,
):

    base_slug = slugify(name) or "folder"

    candidate = base_slug
    counter = 2

    while True:

        existing = (
            ContentCategory.query
            .filter_by(
                creator_account_id=creator.id,
                slug=candidate,
            )
            .first()
        )

        if not existing:

            return candidate

        candidate = (
            f"{base_slug}-{counter}"
        )

        counter += 1


# ============================================================
# UNIQUE CAMPAIGN SLUG
# ============================================================

def unique_campaign_slug(
    creator,
    title,
    campaign_id=None,
):

    base_slug = (
        slugify(title)
        or "campaign"
    )

    candidate = base_slug
    counter = 2

    while True:

        query = (
            FundraisingCampaign.query
            .filter_by(
                creator_account_id=creator.id,
                slug=candidate,
            )
        )

        if campaign_id is not None:

            query = query.filter(
                FundraisingCampaign.id
                != campaign_id
            )

        if not query.first():

            return candidate

        candidate = (
            f"{base_slug}-{counter}"
        )

        counter += 1


# ============================================================
# MONEY
# ============================================================

def parse_money_to_cents(
    value,
):

    value = (
        str(value or "")
        .strip()
        .replace(",", "")
    )

    if not value:

        return None

    try:

        amount = Decimal(value)

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):

        return None

    if amount <= 0:

        return None

    amount = amount.quantize(
        Decimal("0.01")
    )

    return int(
        amount * 100
    )


# ============================================================
# DATETIME INPUT
# ============================================================

def parse_datetime_local(
    value,
):

    value = (
        str(value or "")
        .strip()
    )

    if not value:

        return None

    try:

        parsed = datetime.fromisoformat(
            value
        )

    except ValueError:

        return None

    if parsed.tzinfo is None:

        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed


# ============================================================
# CLOUDINARY FOLDERS
# ============================================================

def post_cloudinary_folder(
    creator,
    post,
    media_group,
):

    root = current_app.config.get(
        "CLOUDINARY_FOLDER",
        "creator-blog",
    )

    return (
        f"{root}/creators/"
        f"{creator.id}/posts/"
        f"{post.id}/"
        f"{media_group}"
    )


def campaign_cloudinary_folder(
    creator,
    campaign,
):

    root = current_app.config.get(
        "CLOUDINARY_FOLDER",
        "creator-blog",
    )

    return (
        f"{root}/creators/"
        f"{creator.id}/fundraising/"
        f"{campaign.id}/covers"
    )


# ============================================================
# CAMPAIGN COVER IMAGE
# ============================================================

def process_campaign_cover_image(
    creator,
    campaign,
    file,
):

    if (
        not file
        or not file.filename
    ):

        return True, None

    valid, error = (
        validate_image(
            file
        )
    )

    if not valid:

        return False, error

    try:

        result = upload_image(
            file,
            folder=(
                campaign_cloudinary_folder(
                    creator,
                    campaign,
                )
            ),
        )

    except Exception:

        current_app.logger.exception(
            (
                "Fundraising campaign "
                "cover upload failed. "
                "creator_account_id=%s "
                "campaign_id=%s"
            ),
            creator.id,
            campaign.id,
        )

        return (
            False,
            "Campaign cover image upload failed.",
        )

    old_public_id = (
        campaign.cover_image_public_id
    )

    campaign.cover_image_url = (
        result["url"]
    )

    campaign.cover_image_public_id = (
        result["public_id"]
    )

    if old_public_id:

        try:

            delete_media(
                old_public_id,
                resource_type="image",
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Old campaign cover "
                    "deletion failed."
                )
            )

    return True, None


# ============================================================
# POST COVER IMAGE
# ============================================================

def process_cover_image(
    creator,
    post,
    file,
):

    if (
        not file
        or not file.filename
    ):

        return True, None

    valid, error = validate_image(
        file
    )

    if not valid:

        return False, error

    try:

        result = upload_image(
            file,
            folder=(
                post_cloudinary_folder(
                    creator,
                    post,
                    "covers",
                )
            ),
        )

    except Exception:

        current_app.logger.exception(
            "Creator cover upload failed."
        )

        return (
            False,
            "Cover image upload failed.",
        )

    existing = (
        ContentMedia.query
        .filter_by(
            post_id=post.id,
            media_type="cover",
        )
        .first()
    )

    old_public_id = None

    if existing:

        old_public_id = (
            existing.public_id
        )

        existing.media_url = (
            result["url"]
        )

        existing.public_id = (
            result["public_id"]
        )

        existing.resource_type = (
            "image"
        )

        existing.width = (
            result.get("width")
        )

        existing.height = (
            result.get("height")
        )

    else:

        existing = ContentMedia(
            post_id=post.id,
            media_type="cover",
            media_url=result["url"],
            public_id=result["public_id"],
            resource_type="image",
            width=result.get("width"),
            height=result.get("height"),
            media_order=0,
        )

        db.session.add(
            existing
        )

    post.cover_image_url = (
        result["url"]
    )

    if old_public_id:

        try:

            delete_media(
                old_public_id,
                resource_type="image",
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Old creator cover "
                    "deletion failed."
                )
            )

    return True, None


# ============================================================
# VIDEO
# ============================================================

def process_post_video(
    creator,
    post,
    file,
):

    if (
        not file
        or not file.filename
    ):

        return True, None

    valid, error = validate_video(
        file
    )

    if not valid:

        return False, error

    try:

        result = upload_video(
            file,
            folder=(
                post_cloudinary_folder(
                    creator,
                    post,
                    "video",
                )
            ),
        )

    except Exception:

        current_app.logger.exception(
            "Creator video upload failed."
        )

        return (
            False,
            "Video upload failed.",
        )

    existing = (
        ContentMedia.query
        .filter_by(
            post_id=post.id,
            media_type="video",
        )
        .first()
    )

    old_public_id = None

    if existing:

        old_public_id = (
            existing.public_id
        )

        existing.media_url = (
            result["url"]
        )

        existing.public_id = (
            result["public_id"]
        )

        existing.resource_type = (
            "video"
        )

        existing.thumbnail_url = (
            result.get(
                "thumbnail_url"
            )
        )

        existing.duration_seconds = (
            result.get(
                "duration"
            )
        )

        existing.width = (
            result.get("width")
        )

        existing.height = (
            result.get("height")
        )

    else:

        existing = ContentMedia(
            post_id=post.id,
            media_type="video",
            media_url=result["url"],
            public_id=result["public_id"],
            resource_type="video",
            thumbnail_url=result.get(
                "thumbnail_url"
            ),
            duration_seconds=result.get(
                "duration"
            ),
            width=result.get("width"),
            height=result.get("height"),
            media_order=0,
        )

        db.session.add(
            existing
        )

    if old_public_id:

        try:

            delete_media(
                old_public_id,
                resource_type="video",
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Old creator video "
                    "deletion failed."
                )
            )

    return True, None


# ============================================================
# STORY GALLERY
# ============================================================

def process_story_gallery(
    creator,
    post,
    files,
):

    files = [
        file
        for file in files
        if file
        and file.filename
    ]

    if not files:

        return True, None

    if len(files) > 10:

        return (
            False,
            (
                "You can upload up to 10 "
                "gallery images at a time."
            ),
        )

    for file in files:

        valid, error = (
            validate_image(
                file
            )
        )

        if not valid:

            return False, error

    latest = (
        ContentMedia.query
        .filter_by(
            post_id=post.id,
            media_type="gallery_image",
        )
        .order_by(
            ContentMedia.media_order.desc()
        )
        .first()
    )

    next_order = (
        latest.media_order + 1
        if latest
        else 1
    )

    uploaded = []

    try:

        for file in files:

            result = upload_image(
                file,
                folder=(
                    post_cloudinary_folder(
                        creator,
                        post,
                        "gallery",
                    )
                ),
            )

            uploaded.append(
                result
            )

            db.session.add(
                ContentMedia(
                    post_id=post.id,
                    media_type="gallery_image",
                    media_url=result["url"],
                    public_id=result["public_id"],
                    resource_type="image",
                    width=result.get("width"),
                    height=result.get("height"),
                    media_order=next_order,
                )
            )

            next_order += 1

    except Exception:

        for result in uploaded:

            try:

                delete_media(
                    result.get(
                        "public_id"
                    ),
                    resource_type="image",
                )

            except Exception:

                pass

        db.session.rollback()

        return (
            False,
            "Gallery upload failed.",
        )

    return True, None


# ============================================================
# CAMPAIGN PAYMENT STATISTICS
# ============================================================

def campaign_paid_total_cents(
    creator,
    campaign,
):

    return int(
        db.session.query(
            db.func.coalesce(
                db.func.sum(
                    FanPayment.amount_cents
                ),
                0,
            )
        )
        .filter(
            FanPayment.creator_account_id
            == creator.id,
            FanPayment.campaign_id
            == campaign.id,
            FanPayment.payment_type
            == "campaign",
            FanPayment.status
            == "paid",
        )
        .scalar()
        or 0
    )


def campaign_supporter_count(
    creator,
    campaign,
):

    return (
        FanPayment.query
        .filter(
            FanPayment.creator_account_id
            == creator.id,
            FanPayment.campaign_id
            == campaign.id,
            FanPayment.payment_type
            == "campaign",
            FanPayment.status
            == "paid",
        )
        .count()
    )


def campaign_stats(
    creator,
    campaign,
):

    raised_cents = (
        campaign_paid_total_cents(
            creator,
            campaign,
        )
    )

    supporter_count = (
        campaign_supporter_count(
            creator,
            campaign,
        )
    )

    goal_cents = (
        campaign.goal_amount_cents
        or 0
    )

    progress_percent = 0

    if goal_cents > 0:

        progress_percent = min(
            100,
            round(
                (
                    raised_cents
                    / goal_cents
                )
                * 100,
                1,
            ),
        )

    return {
        "raised_cents": raised_cents,
        "supporter_count": supporter_count,
        "progress_percent": (
            progress_percent
        ),
    }


def attach_campaign_stats(
    creator,
    campaigns,
):

    for campaign in campaigns:

        stats = campaign_stats(
            creator,
            campaign,
        )

        campaign.raised_cents = (
            stats["raised_cents"]
        )

        campaign.supporter_count = (
            stats["supporter_count"]
        )

        campaign.progress_percent = (
            stats["progress_percent"]
        )

    return campaigns


# ============================================================
# DASHBOARD
# ============================================================

@studio_bp.route("/")
@studio_required
def dashboard():

    account = (
        current_creator_account()
    )

    creator = creator_profile(
        account
    )

    base_posts = (
        ContentPost.query
        .filter_by(
            creator_account_id=account.id
        )
    )

    total_posts = base_posts.count()

    published_posts = (
        base_posts
        .filter_by(
            status="published"
        )
        .count()
    )

    draft_posts = (
        base_posts
        .filter_by(
            status="draft"
        )
        .count()
    )

    exclusive_posts = (
        base_posts
        .filter_by(
            access_level="subscriber"
        )
        .count()
    )

    email_subscribers = (
        EmailSubscriber.query
        .filter_by(
            creator_account_id=account.id,
            status="active",
        )
        .count()
    )

    categories_count = (
        ContentCategory.query
        .filter_by(
            creator_account_id=account.id
        )
        .count()
    )

    recent_posts = (
        base_posts
        .order_by(
            ContentPost.created_at.desc()
        )
        .limit(6)
        .all()
    )

    return render_template(
        "studio/dashboard.html",
        creator=creator,
        creator_account=account,
        total_posts=total_posts,
        published_posts=published_posts,
        draft_posts=draft_posts,
        exclusive_posts=exclusive_posts,
        email_subscribers=email_subscribers,
        categories_count=categories_count,
        plan_summary=(
            creator_plan_summary(
                account
            )
        ),
        recent_posts=recent_posts,
        subscription=(
            g.creator_subscription
        ),
        subscription_status=(
            g.creator_subscription_status
        ),
        grace_days_remaining=(
            g.creator_grace_days_remaining
        ),
    )


# ============================================================
# MONETISATION
# ============================================================

@studio_bp.route(
    "/monetisation"
)
@studio_required
def monetisation():

    account = (
        current_creator_account()
    )

    creator = creator_profile(
        account
    )

    payout_account = (
        creator_payout_account(
            account
        )
    )

    support_payment_count = (
        FanPayment.query
        .filter_by(
            creator_account_id=account.id,
            payment_type="support",
            status="paid",
        )
        .count()
    )

    support_total_cents = int(
        db.session.query(
            db.func.coalesce(
                db.func.sum(
                    FanPayment.amount_cents
                ),
                0,
            )
        )
        .filter(
            FanPayment.creator_account_id
            == account.id,
            FanPayment.payment_type
            == "support",
            FanPayment.status
            == "paid",
        )
        .scalar()
        or 0
    )

    total_paid_fan_payments = (
        FanPayment.query
        .filter_by(
            creator_account_id=account.id,
            status="paid",
        )
        .count()
    )

    total_fan_earnings_cents = int(
        db.session.query(
            db.func.coalesce(
                db.func.sum(
                    FanPayment.amount_cents
                ),
                0,
            )
        )
        .filter(
            FanPayment.creator_account_id
            == account.id,
            FanPayment.status
            == "paid",
        )
        .scalar()
        or 0
    )

    recent_payments = (
        FanPayment.query
        .filter_by(
            creator_account_id=account.id
        )
        .order_by(
            FanPayment.created_at.desc()
        )
        .limit(8)
        .all()
    )

    campaigns = (
        FundraisingCampaign.query
        .filter_by(
            creator_account_id=account.id
        )
        .order_by(
            FundraisingCampaign.created_at.desc()
        )
        .all()
    )

    attach_campaign_stats(
        account,
        campaigns,
    )

    active_campaign_count = (
        FundraisingCampaign.query
        .filter_by(
            creator_account_id=account.id,
            status="active",
        )
        .count()
    )

    return render_template(
        "studio/monetisation.html",
        creator=creator,
        creator_account=account,
        plan_summary=(
            creator_plan_summary(
                account
            )
        ),
        payout_account=payout_account,
        can_connect_payout=(
            creator_has_feature(
                account,
                FEATURE_PAYOUT_CONNECTION,
            )
        ),
        can_receive_support=(
            creator_has_feature(
                account,
                FEATURE_FAN_SUPPORT,
            )
        ),
        can_fundraise=(
            creator_has_feature(
                account,
                FEATURE_FUNDRAISING,
            )
        ),
        can_offer_memberships=(
            creator_has_feature(
                account,
                FEATURE_PAID_MEMBERSHIPS,
            )
        ),
        can_publish_exclusive=(
            creator_has_feature(
                account,
                FEATURE_EXCLUSIVE_CONTENT,
            )
        ),
        support_payment_count=(
            support_payment_count
        ),
        support_total_cents=(
            support_total_cents
        ),
        total_paid_fan_payments=(
            total_paid_fan_payments
        ),
        total_fan_earnings_cents=(
            total_fan_earnings_cents
        ),
        recent_payments=recent_payments,
        campaigns=campaigns,
        active_campaign_count=(
            active_campaign_count
        ),
    )


# ============================================================
# PAYOUT SETUP
# ============================================================

@studio_bp.route(
    "/monetisation/payout"
)
@studio_required
def payout_setup():

    account = (
        current_creator_account()
    )

    if not require_creator_feature(
        account,
        FEATURE_PAYOUT_CONNECTION,
    ):

        return redirect(
            url_for(
                "studio.monetisation"
            )
        )

    return render_template(
        "studio/payout_setup.html",
        creator=creator_profile(
            account
        ),
        creator_account=account,
        payout_account=(
            creator_payout_account(
                account
            )
        ),
        plan_summary=(
            creator_plan_summary(
                account
            )
        ),
    )


# Backwards-compatible endpoint.
# ============================================================
# CREATOR PAYOUT ACCOUNT
# ============================================================
#
# Standard + Premium.
#
# Flow:
#
#   Creator enters bank details
#       ↓
#   Server validates SA bank account with Paystack
#       ↓
#   Server creates Paystack subaccount
#       ↓
#   Store:
#
#       provider_subaccount_code
#       safe account display information
#       last 4 account digits
#
#   DO NOT STORE:
#
#       full account number
#       ID number
#       passport number
#       company registration number
#
# ============================================================

@studio_bp.route(
    "/monetisation/payout",
    methods=[
        "GET",
        "POST",
    ],
)
@studio_required
def monetisation_payout():

    account = (
        current_creator_account()
    )

    # --------------------------------------------------------
    # PLAN FEATURE
    # --------------------------------------------------------

    if not require_creator_feature(
        account,
        FEATURE_PAYOUT_CONNECTION,
    ):

        return redirect(
            url_for(
                "studio.monetisation"
            )
        )

    creator = (
        creator_profile(
            account
        )
    )

    payout_account = (
        creator_payout_account(
            account
        )
    )

    # --------------------------------------------------------
    # EXISTING ACTIVE PAYOUT ACCOUNT
    # --------------------------------------------------------
    #
    # Do not create another Paystack subaccount.
    #
    # A separate "change payout account" workflow can be
    # implemented later using Paystack's Update Subaccount
    # endpoint.
    # --------------------------------------------------------

    payout_connected = bool(
        payout_account
        and payout_account.status
        == "active"
        and payout_account
        .provider_subaccount_code
    )

    # --------------------------------------------------------
    # LOAD SOUTH AFRICAN BANKS
    # --------------------------------------------------------

    banks = []

    bank_load_error = None

    if not payout_connected:

        try:

            banks = (
                list_south_african_banks(
                    verification_only=True
                )
            )

        except PaystackError as exc:

            bank_load_error = str(
                exc
            )

            current_app.logger.exception(
                (
                    "Unable to load Paystack "
                    "South African banks. "
                    "creator_account_id=%s"
                ),
                account.id,
            )

    # --------------------------------------------------------
    # POST
    # --------------------------------------------------------

    if request.method == "POST":

        # ----------------------------------------------------
        # PREVENT DUPLICATE SUBACCOUNTS
        # ----------------------------------------------------

        if payout_connected:

            flash(
                (
                    "Your payout account is "
                    "already connected."
                ),
                "warning",
            )

            return redirect(
                url_for(
                    "studio.monetisation_payout"
                )
            )

        # ----------------------------------------------------
        # INPUT
        # ----------------------------------------------------

        business_name = (
            request.form
            .get(
                "business_name",
                "",
            )
            .strip()
        )

        account_name = (
            request.form
            .get(
                "account_name",
                "",
            )
            .strip()
        )

        bank_code = (
            request.form
            .get(
                "bank_code",
                "",
            )
            .strip()
        )

        account_number = (
            request.form
            .get(
                "account_number",
                "",
            )
            .strip()
            .replace(
                " ",
                "",
            )
        )

        account_type = (
            request.form
            .get(
                "account_type",
                "personal",
            )
            .strip()
            .lower()
        )

        document_type = (
            request.form
            .get(
                "document_type",
                "",
            )
            .strip()
        )

        document_number = (
            request.form
            .get(
                "document_number",
                "",
            )
            .strip()
            .replace(
                " ",
                "",
            )
        )

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if (
            not business_name
            or len(
                business_name
            ) > 180
        ):

            flash(
                (
                    "Enter a valid creator "
                    "or business name."
                ),
                "error",
            )

            return render_template(
                "studio/payout_setup.html",
                creator=creator,
                creator_account=account,
                payout_account=(
                    payout_account
                ),
                payout_connected=False,
                banks=banks,
                bank_load_error=(
                    bank_load_error
                ),
                plan_summary=(
                    creator_plan_summary(
                        account
                    )
                ),
            )

        if (
            not account_name
            or len(
                account_name
            ) > 180
        ):

            flash(
                (
                    "Enter the account holder "
                    "name exactly as registered "
                    "with your bank."
                ),
                "error",
            )

            return render_template(
                "studio/payout_setup.html",
                creator=creator,
                creator_account=account,
                payout_account=(
                    payout_account
                ),
                payout_connected=False,
                banks=banks,
                bank_load_error=(
                    bank_load_error
                ),
                plan_summary=(
                    creator_plan_summary(
                        account
                    )
                ),
            )

        if not bank_code:

            flash(
                "Select your bank.",
                "error",
            )

            return render_template(
                "studio/payout_setup.html",
                creator=creator,
                creator_account=account,
                payout_account=(
                    payout_account
                ),
                payout_connected=False,
                banks=banks,
                bank_load_error=(
                    bank_load_error
                ),
                plan_summary=(
                    creator_plan_summary(
                        account
                    )
                ),
            )

        # ----------------------------------------------------
        # VERIFY BANK CODE CAME FROM PAYSTACK
        # ----------------------------------------------------

        selected_bank = next(
            (
                bank
                for bank in banks
                if str(
                    bank.get(
                        "code",
                        ""
                    )
                )
                == bank_code
            ),
            None,
        )

        if not selected_bank:

            flash(
                (
                    "Select a valid South "
                    "African bank."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "studio.monetisation_payout"
                )
            )

        if (
            not account_number
            or not account_number.isdigit()
            or len(
                account_number
            ) > 30
        ):

            flash(
                (
                    "Enter a valid numeric "
                    "bank account number."
                ),
                "error",
            )

            return render_template(
                "studio/payout_setup.html",
                creator=creator,
                creator_account=account,
                payout_account=(
                    payout_account
                ),
                payout_connected=False,
                banks=banks,
                bank_load_error=(
                    bank_load_error
                ),
                plan_summary=(
                    creator_plan_summary(
                        account
                    )
                ),
            )

        if account_type not in {
            "personal",
            "business",
        }:

            abort(400)

        # ----------------------------------------------------
        # DOCUMENT TYPE MUST MATCH ACCOUNT TYPE
        # ----------------------------------------------------

        if account_type == "business":

            if (
                document_type
                != "businessRegistrationNumber"
            ):

                flash(
                    (
                        "Business bank accounts "
                        "require the business "
                        "registration number."
                    ),
                    "error",
                )

                return redirect(
                    url_for(
                        "studio.monetisation_payout"
                    )
                )

        else:

            if document_type not in {
                "identityNumber",
                "passportNumber",
            }:

                flash(
                    (
                        "Personal bank accounts "
                        "require a South African "
                        "ID or passport number."
                    ),
                    "error",
                )

                return redirect(
                    url_for(
                        "studio.monetisation_payout"
                    )
                )

        if (
            not document_number
            or len(
                document_number
            ) > 80
        ):

            flash(
                (
                    "Enter the required "
                    "identity or registration "
                    "number."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "studio.monetisation_payout"
                )
            )

        # ----------------------------------------------------
        # VALIDATE ACCOUNT WITH PAYSTACK
        # ----------------------------------------------------
        #
        # Sensitive values exist only in memory for this
        # request and are never written to our database.
        # ----------------------------------------------------

        try:

            validation = (
                validate_south_african_account(
                    bank_code=bank_code,
                    account_number=(
                        account_number
                    ),
                    account_name=(
                        account_name
                    ),
                    account_type=(
                        account_type
                    ),
                    document_type=(
                        document_type
                    ),
                    document_number=(
                        document_number
                    ),
                )
            )

        except PaystackError as exc:

            current_app.logger.warning(
                (
                    "Creator payout account "
                    "validation failed. "
                    "creator_account_id=%s "
                    "error=%s"
                ),
                account.id,
                str(exc),
            )

            flash(
                (
                    "Paystack could not verify "
                    "those bank details. Check "
                    "the account holder name, "
                    "bank, account number and "
                    "identity details."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "studio.monetisation_payout"
                )
            )

        # ----------------------------------------------------
        # REQUIRE VERIFIED ACCOUNT
        # ----------------------------------------------------

        if not validation.get(
            "verified"
        ):

            verification_message = (
                validation.get(
                    "verificationMessage"
                )
                or (
                    "The bank account could "
                    "not be verified."
                )
            )

            current_app.logger.warning(
                (
                    "Creator bank validation "
                    "returned unverified. "
                    "creator_account_id=%s"
                ),
                account.id,
            )

            flash(
                verification_message,
                "error",
            )

            return redirect(
                url_for(
                    "studio.monetisation_payout"
                )
            )

        # ----------------------------------------------------
        # REQUIRE ACCOUNT TO ACCEPT CREDITS
        # ----------------------------------------------------

        accepts_credits = (
            validation.get(
                "accountAcceptsCredits"
            )
        )

        if accepts_credits is False:

            flash(
                (
                    "This bank account cannot "
                    "currently receive credits. "
                    "Please use another account."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "studio.monetisation_payout"
                )
            )

        # ----------------------------------------------------
        # CREATE PAYSTACK SUBACCOUNT
        # ----------------------------------------------------

        try:

            provider_account = (
                create_creator_subaccount(
                    business_name=(
                        business_name
                    ),
                    bank_code=(
                        bank_code
                    ),
                    account_number=(
                        account_number
                    ),
                    creator_email=(
                        account.email
                    ),
                    creator_name=(
                        account_name
                    ),
                )
            )

        except PaystackError as exc:

            current_app.logger.exception(
                (
                    "Paystack subaccount "
                    "creation failed. "
                    "creator_account_id=%s "
                    "error=%s"
                ),
                account.id,
                str(exc),
            )

            flash(
                (
                    "Your bank details were "
                    "verified, but the payout "
                    "account could not be "
                    "connected. Please try again."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "studio.monetisation_payout"
                )
            )

        # ----------------------------------------------------
        # PROVIDER IDENTIFIER
        # ----------------------------------------------------

        subaccount_code = (
            str(
                provider_account.get(
                    "subaccount_code"
                )
                or ""
            )
            .strip()
        )

        if not subaccount_code:

            current_app.logger.error(
                (
                    "Paystack created subaccount "
                    "without subaccount code. "
                    "creator_account_id=%s"
                ),
                account.id,
            )

            flash(
                (
                    "Paystack did not return "
                    "a payout account identifier. "
                    "Please contact support."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "studio.monetisation_payout"
                )
            )

        # ----------------------------------------------------
        # SAFE PROVIDER DISPLAY VALUES
        # ----------------------------------------------------

        provider_account_name = (
            str(
                provider_account.get(
                    "account_name"
                )
                or account_name
            )
            .strip()
        )

        provider_bank_name = (
            str(
                provider_account.get(
                    "settlement_bank"
                )
                or selected_bank.get(
                    "name"
                )
                or ""
            )
            .strip()
        )

        provider_business_name = (
            str(
                provider_account.get(
                    "business_name"
                )
                or business_name
            )
            .strip()
        )

        # ----------------------------------------------------
        # CREATE / UPDATE LOCAL PAYOUT RECORD
        # ----------------------------------------------------

        if not payout_account:

            payout_account = (
                CreatorPayoutAccount(
                    creator_account_id=(
                        account.id
                    )
                )
            )

            db.session.add(
                payout_account
            )

        payout_account.provider = (
            "paystack"
        )

        payout_account.provider_subaccount_code = (
            subaccount_code
        )

        payout_account.business_name = (
            provider_business_name[:180]
            or None
        )

        payout_account.account_name = (
            provider_account_name[:180]
            or None
        )

        payout_account.settlement_bank = (
            provider_bank_name[:180]
            or None
        )

        # ----------------------------------------------------
        # ONLY LAST FOUR DIGITS
        # ----------------------------------------------------

        payout_account.account_number_last4 = (
            account_number[-4:]
        )

        payout_account.percentage_charge = (
            0
        )

        payout_account.status = (
            "active"
        )

        payout_account.connected_at = (
            utc_now()
        )

        payout_account.disabled_at = (
            None
        )

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            current_app.logger.exception(
                (
                    "Local payout account save "
                    "failed after Paystack "
                    "subaccount creation. "
                    "creator_account_id=%s "
                    "subaccount_code=%s"
                ),
                account.id,
                subaccount_code,
            )

            # IMPORTANT:
            #
            # The Paystack subaccount now exists even though
            # our local save failed.
            #
            # Do NOT automatically create another one.
            #
            # This requires reconciliation by platform admin.

            flash(
                (
                    "Paystack connected the bank "
                    "account, but Kalxa could not "
                    "finish saving the connection. "
                    "Please contact support before "
                    "trying again."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "studio.monetisation_payout"
                )
            )

        current_app.logger.info(
            (
                "Creator payout account "
                "connected. "
                "creator_account_id=%s "
                "provider=paystack"
            ),
            account.id,
        )

        flash(
            (
                "Your payout account is "
                "connected successfully. "
                "You can now receive fan "
                "support."
            ),
            "success",
        )

        return redirect(
            url_for(
                "studio.monetisation_payout"
            )
        )

    # --------------------------------------------------------
    # GET
    # --------------------------------------------------------

    return render_template(
        "studio/payout_setup.html",
        creator=creator,
        creator_account=account,
        payout_account=(
            payout_account
        ),
        payout_connected=(
            payout_connected
        ),
        banks=banks,
        bank_load_error=(
            bank_load_error
        ),
        plan_summary=(
            creator_plan_summary(
                account
            )
        ),
    )


# ============================================================
# SUPPORT SETUP
# ============================================================

@studio_bp.route(
    "/monetisation/support"
)
@studio_required
def support_setup():

    account = (
        current_creator_account()
    )

    if not require_creator_feature(
        account,
        FEATURE_FAN_SUPPORT,
    ):

        return redirect(
            url_for(
                "studio.monetisation"
            )
        )

    payout_account = (
        creator_payout_account(
            account
        )
    )

    support_total_cents = int(
        db.session.query(
            db.func.coalesce(
                db.func.sum(
                    FanPayment.amount_cents
                ),
                0,
            )
        )
        .filter(
            FanPayment.creator_account_id
            == account.id,
            FanPayment.payment_type
            == "support",
            FanPayment.status
            == "paid",
        )
        .scalar()
        or 0
    )

    support_count = (
        FanPayment.query
        .filter_by(
            creator_account_id=account.id,
            payment_type="support",
            status="paid",
        )
        .count()
    )

    recent_support = (
        FanPayment.query
        .filter_by(
            creator_account_id=account.id,
            payment_type="support",
        )
        .order_by(
            FanPayment.created_at.desc()
        )
        .limit(10)
        .all()
    )

    return render_template(
        "studio/support_setup.html",
        creator=creator_profile(
            account
        ),
        creator_account=account,
        payout_account=payout_account,
        plan_summary=(
            creator_plan_summary(
                account
            )
        ),
        support_total_cents=(
            support_total_cents
        ),
        support_count=support_count,
        recent_support=recent_support,
    )


# Backwards-compatible endpoint.
@studio_bp.route(
    "/monetisation/support/legacy"
)
@studio_required
def monetisation_support():

    return redirect(
        url_for(
            "studio.support_setup"
        )
    )


# ============================================================
# FUNDRAISING CAMPAIGNS
# PREMIUM ONLY
# ============================================================

@studio_bp.route(
    "/monetisation/campaigns"
)
@studio_required
def fundraising_campaigns():

    account = (
        current_creator_account()
    )

    if not require_creator_feature(
        account,
        FEATURE_FUNDRAISING,
    ):

        return redirect(
            url_for(
                "studio.monetisation"
            )
        )

    campaigns = (
        FundraisingCampaign.query
        .filter_by(
            creator_account_id=account.id
        )
        .order_by(
            FundraisingCampaign.created_at.desc()
        )
        .all()
    )

    attach_campaign_stats(
        account,
        campaigns,
    )

    total_raised_cents = sum(
        campaign.raised_cents
        for campaign in campaigns
    )

    total_supporters = sum(
        campaign.supporter_count
        for campaign in campaigns
    )

    return render_template(
        "studio/fundraising_campaigns.html",
        creator=creator_profile(
            account
        ),
        creator_account=account,
        campaigns=campaigns,
        total_raised_cents=(
            total_raised_cents
        ),
        total_supporters=(
            total_supporters
        ),
        plan_summary=(
            creator_plan_summary(
                account
            )
        ),
    )


# ============================================================
# CREATE FUNDRAISING CAMPAIGN
# ============================================================

@studio_bp.route(
    "/monetisation/campaigns/new",
    methods=[
        "GET",
        "POST",
    ],
)
@studio_required
def fundraising_new():

    account = (
        current_creator_account()
    )

    if not require_creator_feature(
        account,
        FEATURE_FUNDRAISING,
    ):

        return redirect(
            url_for(
                "studio.monetisation"
            )
        )

    if request.method == "POST":

        title = (
            request.form
            .get("title", "")
            .strip()
        )

        description = (
            request.form
            .get("description", "")
            .strip()
        )

        goal_amount_cents = (
            parse_money_to_cents(
                request.form.get(
                    "goal_amount"
                )
            )
        )

        starts_at_raw = (
            request.form
            .get("starts_at", "")
            .strip()
        )

        ends_at_raw = (
            request.form
            .get("ends_at", "")
            .strip()
        )

        starts_at = (
            parse_datetime_local(
                starts_at_raw
            )
        )

        ends_at = (
            parse_datetime_local(
                ends_at_raw
            )
        )

        requested_status = (
            request.form
            .get(
                "status",
                "draft",
            )
            .strip()
            .lower()
        )

        if requested_status not in {
            "draft",
            "active",
        }:

            requested_status = "draft"

        if not title:

            flash(
                "Campaign title is required.",
                "error",
            )

            return render_template(
                "studio/fundraising_form.html",
                creator_account=account,
                campaign=None,
            )

        if len(title) > 180:

            flash(
                (
                    "Campaign title must be "
                    "180 characters or fewer."
                ),
                "error",
            )

            return render_template(
                "studio/fundraising_form.html",
                creator_account=account,
                campaign=None,
            )

        if not description:

            flash(
                (
                    "Campaign description "
                    "is required."
                ),
                "error",
            )

            return render_template(
                "studio/fundraising_form.html",
                creator_account=account,
                campaign=None,
            )

        if goal_amount_cents is None:

            flash(
                (
                    "Enter a valid fundraising "
                    "goal greater than R0."
                ),
                "error",
            )

            return render_template(
                "studio/fundraising_form.html",
                creator_account=account,
                campaign=None,
            )

        if starts_at_raw and not starts_at:

            flash(
                "Enter a valid campaign start date.",
                "error",
            )

            return render_template(
                "studio/fundraising_form.html",
                creator_account=account,
                campaign=None,
            )

        if ends_at_raw and not ends_at:

            flash(
                "Enter a valid campaign end date.",
                "error",
            )

            return render_template(
                "studio/fundraising_form.html",
                creator_account=account,
                campaign=None,
            )

        if (
            starts_at
            and ends_at
            and ends_at <= starts_at
        ):

            flash(
                (
                    "Campaign end date must be "
                    "after the start date."
                ),
                "error",
            )

            return render_template(
                "studio/fundraising_form.html",
                creator_account=account,
                campaign=None,
            )

        campaign = FundraisingCampaign(
            creator_account_id=account.id,
            title=title,
            slug=unique_campaign_slug(
                account,
                title,
            ),
            description=description,
            goal_amount_cents=(
                goal_amount_cents
            ),
            currency="ZAR",
            status=requested_status,
            starts_at=starts_at,
            ends_at=ends_at,
        )

        if requested_status == "active":

            campaign.published_at = (
                utc_now()
            )

        try:

            db.session.add(
                campaign
            )

            # Need ID before Cloudinary folder.
            db.session.flush()

            success, error = (
                process_campaign_cover_image(
                    account,
                    campaign,
                    request.files.get(
                        "cover_image"
                    ),
                )
            )

            if not success:

                db.session.rollback()

                flash(
                    error,
                    "error",
                )

                return render_template(
                    "studio/fundraising_form.html",
                    creator_account=account,
                    campaign=None,
                )

            db.session.commit()

        except Exception:

            db.session.rollback()

            current_app.logger.exception(
                (
                    "Fundraising campaign "
                    "creation failed. "
                    "creator_account_id=%s"
                ),
                account.id,
            )

            flash(
                (
                    "Campaign could not be "
                    "created. Please try again."
                ),
                "error",
            )

            return render_template(
                "studio/fundraising_form.html",
                creator_account=account,
                campaign=None,
            )

        flash(
            (
                "Fundraising campaign "
                "created successfully."
            ),
            "success",
        )

        return redirect(
            url_for(
                "studio.fundraising_campaigns"
            )
        )

    return render_template(
        "studio/fundraising_form.html",
        creator_account=account,
        campaign=None,
    )


# ============================================================
# BACKWARDS-COMPATIBLE CREATE ENDPOINT
# ============================================================

@studio_bp.route(
    "/monetisation/campaigns/create",
    methods=["GET"],
)
@studio_required
def fundraising_campaign_new():

    return redirect(
        url_for(
            "studio.fundraising_new"
        )
    )


# ============================================================
# EDIT FUNDRAISING CAMPAIGN
# ============================================================

@studio_bp.route(
    "/monetisation/campaigns/"
    "<int:campaign_id>/edit",
    methods=[
        "GET",
        "POST",
    ],
)
@studio_required
def fundraising_edit(
    campaign_id,
):

    account = (
        current_creator_account()
    )

    if not require_creator_feature(
        account,
        FEATURE_FUNDRAISING,
    ):

        return redirect(
            url_for(
                "studio.monetisation"
            )
        )

    campaign = (
        creator_campaign_or_404(
            account,
            campaign_id,
        )
    )

    if request.method == "POST":

        title = (
            request.form
            .get("title", "")
            .strip()
        )

        description = (
            request.form
            .get("description", "")
            .strip()
        )

        goal_amount_cents = (
            parse_money_to_cents(
                request.form.get(
                    "goal_amount"
                )
            )
        )

        starts_at_raw = (
            request.form
            .get("starts_at", "")
            .strip()
        )

        ends_at_raw = (
            request.form
            .get("ends_at", "")
            .strip()
        )

        starts_at = (
            parse_datetime_local(
                starts_at_raw
            )
        )

        ends_at = (
            parse_datetime_local(
                ends_at_raw
            )
        )

        requested_status = (
            request.form
            .get(
                "status",
                campaign.status,
            )
            .strip()
            .lower()
        )

        allowed_statuses = {
            "draft",
            "active",
            "completed",
            "cancelled",
            "archived",
        }

        if requested_status not in allowed_statuses:

            abort(400)

        if not title:

            flash(
                "Campaign title is required.",
                "error",
            )

            return render_template(
                "studio/fundraising_form.html",
                creator_account=account,
                campaign=campaign,
            )

        if len(title) > 180:

            flash(
                (
                    "Campaign title must be "
                    "180 characters or fewer."
                ),
                "error",
            )

            return render_template(
                "studio/fundraising_form.html",
                creator_account=account,
                campaign=campaign,
            )

        if not description:

            flash(
                (
                    "Campaign description "
                    "is required."
                ),
                "error",
            )

            return render_template(
                "studio/fundraising_form.html",
                creator_account=account,
                campaign=campaign,
            )

        if goal_amount_cents is None:

            flash(
                (
                    "Enter a valid fundraising "
                    "goal greater than R0."
                ),
                "error",
            )

            return render_template(
                "studio/fundraising_form.html",
                creator_account=account,
                campaign=campaign,
            )

        if starts_at_raw and not starts_at:

            flash(
                "Enter a valid campaign start date.",
                "error",
            )

            return render_template(
                "studio/fundraising_form.html",
                creator_account=account,
                campaign=campaign,
            )

        if ends_at_raw and not ends_at:

            flash(
                "Enter a valid campaign end date.",
                "error",
            )

            return render_template(
                "studio/fundraising_form.html",
                creator_account=account,
                campaign=campaign,
            )

        if (
            starts_at
            and ends_at
            and ends_at <= starts_at
        ):

            flash(
                (
                    "Campaign end date must be "
                    "after the start date."
                ),
                "error",
            )

            return render_template(
                "studio/fundraising_form.html",
                creator_account=account,
                campaign=campaign,
            )

        previous_status = (
            campaign.status
        )

        campaign.title = title

        campaign.slug = (
            unique_campaign_slug(
                account,
                title,
                campaign.id,
            )
        )

        campaign.description = (
            description
        )

        campaign.goal_amount_cents = (
            goal_amount_cents
        )

        campaign.starts_at = starts_at

        campaign.ends_at = ends_at

        campaign.status = (
            requested_status
        )

        if (
            requested_status == "active"
            and previous_status != "active"
        ):

            if not campaign.published_at:

                campaign.published_at = (
                    utc_now()
                )

            campaign.cancelled_at = None

        if (
            requested_status == "completed"
            and previous_status
            != "completed"
        ):

            campaign.completed_at = (
                utc_now()
            )

        if (
            requested_status == "cancelled"
            and previous_status
            != "cancelled"
        ):

            campaign.cancelled_at = (
                utc_now()
            )

        try:

            success, error = (
                process_campaign_cover_image(
                    account,
                    campaign,
                    request.files.get(
                        "cover_image"
                    ),
                )
            )

            if not success:

                db.session.rollback()

                flash(
                    error,
                    "error",
                )

                return redirect(
                    url_for(
                        "studio.fundraising_edit",
                        campaign_id=campaign.id,
                    )
                )

            db.session.commit()

        except Exception:

            db.session.rollback()

            current_app.logger.exception(
                (
                    "Fundraising campaign "
                    "update failed. "
                    "creator_account_id=%s "
                    "campaign_id=%s"
                ),
                account.id,
                campaign.id,
            )

            flash(
                (
                    "Campaign could not be "
                    "updated. Please try again."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "studio.fundraising_edit",
                    campaign_id=campaign.id,
                )
            )

        flash(
            "Campaign updated.",
            "success",
        )

        return redirect(
            url_for(
                "studio.fundraising_edit",
                campaign_id=campaign.id,
            )
        )

    stats = campaign_stats(
        account,
        campaign,
    )

    campaign.raised_cents = (
        stats["raised_cents"]
    )

    campaign.supporter_count = (
        stats["supporter_count"]
    )

    campaign.progress_percent = (
        stats["progress_percent"]
    )

    return render_template(
        "studio/fundraising_form.html",
        creator_account=account,
        campaign=campaign,
    )


# ============================================================
# PUBLISH / ACTIVATE CAMPAIGN
# ============================================================

@studio_bp.route(
    "/monetisation/campaigns/"
    "<int:campaign_id>/publish",
    methods=["POST"],
)
@studio_required
def fundraising_publish(
    campaign_id,
):

    account = (
        current_creator_account()
    )

    if not require_creator_feature(
        account,
        FEATURE_FUNDRAISING,
    ):

        return redirect(
            url_for(
                "studio.monetisation"
            )
        )

    campaign = (
        creator_campaign_or_404(
            account,
            campaign_id,
        )
    )

    if campaign.status in {
        "cancelled",
        "archived",
    }:

        flash(
            (
                "This campaign cannot be "
                "published in its current state."
            ),
            "warning",
        )

        return redirect(
            url_for(
                "studio.fundraising_edit",
                campaign_id=campaign.id,
            )
        )

    campaign.status = "active"

    if not campaign.published_at:

        campaign.published_at = (
            utc_now()
        )

    campaign.cancelled_at = None

    db.session.commit()

    flash(
        "Campaign is now active.",
        "success",
    )

    return redirect(
        url_for(
            "studio.fundraising_campaigns"
        )
    )


# ============================================================
# COMPLETE CAMPAIGN
# ============================================================

@studio_bp.route(
    "/monetisation/campaigns/"
    "<int:campaign_id>/complete",
    methods=["POST"],
)
@studio_required
def fundraising_complete(
    campaign_id,
):

    account = (
        current_creator_account()
    )

    if not require_creator_feature(
        account,
        FEATURE_FUNDRAISING,
    ):

        return redirect(
            url_for(
                "studio.monetisation"
            )
        )

    campaign = (
        creator_campaign_or_404(
            account,
            campaign_id,
        )
    )

    campaign.status = "completed"

    if not campaign.completed_at:

        campaign.completed_at = (
            utc_now()
        )

    db.session.commit()

    flash(
        "Campaign marked as completed.",
        "success",
    )

    return redirect(
        url_for(
            "studio.fundraising_campaigns"
        )
    )


# ============================================================
# CANCEL CAMPAIGN
# ============================================================

@studio_bp.route(
    "/monetisation/campaigns/"
    "<int:campaign_id>/cancel",
    methods=["POST"],
)
@studio_required
def fundraising_cancel(
    campaign_id,
):

    account = (
        current_creator_account()
    )

    if not require_creator_feature(
        account,
        FEATURE_FUNDRAISING,
    ):

        return redirect(
            url_for(
                "studio.monetisation"
            )
        )

    campaign = (
        creator_campaign_or_404(
            account,
            campaign_id,
        )
    )

    campaign.status = "cancelled"

    campaign.cancelled_at = (
        utc_now()
    )

    db.session.commit()

    flash(
        "Campaign cancelled.",
        "success",
    )

    return redirect(
        url_for(
            "studio.fundraising_campaigns"
        )
    )


# ============================================================
# ARCHIVE CAMPAIGN
# ============================================================

@studio_bp.route(
    "/monetisation/campaigns/"
    "<int:campaign_id>/archive",
    methods=["POST"],
)
@studio_required
def fundraising_archive(
    campaign_id,
):

    account = (
        current_creator_account()
    )

    if not require_creator_feature(
        account,
        FEATURE_FUNDRAISING,
    ):

        return redirect(
            url_for(
                "studio.monetisation"
            )
        )

    campaign = (
        creator_campaign_or_404(
            account,
            campaign_id,
        )
    )

    campaign.status = "archived"

    db.session.commit()

    flash(
        "Campaign archived.",
        "success",
    )

    return redirect(
        url_for(
            "studio.fundraising_campaigns"
        )
    )


# ============================================================
# REMOVE CAMPAIGN COVER
# ============================================================

@studio_bp.route(
    "/monetisation/campaigns/"
    "<int:campaign_id>/cover/remove",
    methods=["POST"],
)
@studio_required
def fundraising_remove_cover(
    campaign_id,
):

    account = (
        current_creator_account()
    )

    if not require_creator_feature(
        account,
        FEATURE_FUNDRAISING,
    ):

        return redirect(
            url_for(
                "studio.monetisation"
            )
        )

    campaign = (
        creator_campaign_or_404(
            account,
            campaign_id,
        )
    )

    if campaign.cover_image_public_id:

        try:

            delete_media(
                campaign.cover_image_public_id,
                resource_type="image",
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Campaign cover deletion "
                    "failed. creator_account_id=%s "
                    "campaign_id=%s"
                ),
                account.id,
                campaign.id,
            )

            flash(
                (
                    "Campaign cover could "
                    "not be removed."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "studio.fundraising_edit",
                    campaign_id=campaign.id,
                )
            )

    campaign.cover_image_url = None
    campaign.cover_image_public_id = None

    db.session.commit()

    flash(
        "Campaign cover removed.",
        "success",
    )

    return redirect(
        url_for(
            "studio.fundraising_edit",
            campaign_id=campaign.id,
        )
    )


# ============================================================
# DELETE CAMPAIGN
# ============================================================
#
# Only campaigns without payment history can be deleted.
# Once money has been associated with a campaign, preserve the
# financial history and archive/cancel it instead.
# ============================================================

@studio_bp.route(
    "/monetisation/campaigns/"
    "<int:campaign_id>/delete",
    methods=["POST"],
)
@studio_required
def fundraising_delete(
    campaign_id,
):

    account = (
        current_creator_account()
    )

    if not require_creator_feature(
        account,
        FEATURE_FUNDRAISING,
    ):

        return redirect(
            url_for(
                "studio.monetisation"
            )
        )

    campaign = (
        creator_campaign_or_404(
            account,
            campaign_id,
        )
    )

    payment_exists = (
        FanPayment.query
        .filter(
            FanPayment.creator_account_id
            == account.id,
            FanPayment.campaign_id
            == campaign.id,
        )
        .first()
    )

    if payment_exists:

        flash(
            (
                "This campaign has payment "
                "history and cannot be deleted. "
                "Archive it instead."
            ),
            "warning",
        )

        return redirect(
            url_for(
                "studio.fundraising_campaigns"
            )
        )

    if campaign.cover_image_public_id:

        try:

            delete_media(
                campaign.cover_image_public_id,
                resource_type="image",
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Campaign cover cleanup "
                    "failed during deletion."
                )
            )

    title = campaign.title

    db.session.delete(
        campaign
    )

    db.session.commit()

    flash(
        f'"{title}" was deleted.',
        "success",
    )

    return redirect(
        url_for(
            "studio.fundraising_campaigns"
        )
    )


# ============================================================
# CONTENT LIST
# ============================================================

@studio_bp.route(
    "/content"
)
@studio_required
def content_list():

    account = (
        current_creator_account()
    )

    status = (
        request.args
        .get("status", "")
        .strip()
    )

    content_type = (
        request.args
        .get("type", "")
        .strip()
    )

    query = (
        ContentPost.query
        .filter_by(
            creator_account_id=account.id
        )
    )

    if status in {
        "draft",
        "published",
        "archived",
    }:

        query = query.filter_by(
            status=status
        )

    if content_type in {
        "story",
        "reel",
        "vlog",
    }:

        query = query.filter_by(
            content_type=content_type
        )

    posts = (
        query
        .order_by(
            ContentPost.created_at.desc()
        )
        .all()
    )

    return render_template(
        "studio/content_list.html",
        posts=posts,
        selected_status=status,
        selected_type=content_type,
    )


# ============================================================
# CREATE CONTENT
# ============================================================

@studio_bp.route(
    "/content/new",
    methods=[
        "GET",
        "POST",
    ],
)
@studio_required
def content_new():

    account = (
        current_creator_account()
    )

    categories = (
        ContentCategory.query
        .filter_by(
            creator_account_id=account.id,
            is_active=True,
        )
        .order_by(
            ContentCategory.display_order.asc(),
            ContentCategory.name.asc(),
        )
        .all()
    )

    if request.method == "POST":

        title = (
            request.form
            .get("title", "")
            .strip()
        )

        excerpt = (
            request.form
            .get("excerpt", "")
            .strip()
        )

        body = (
            request.form
            .get("body", "")
            .strip()
        )

        content_type = (
            request.form
            .get(
                "content_type",
                "story",
            )
            .strip()
        )

        access_level = (
            request.form
            .get(
                "access_level",
                "public",
            )
            .strip()
        )

        status = (
            request.form
            .get(
                "status",
                "draft",
            )
            .strip()
        )

        category_id = (
            request.form.get(
                "category_id",
                type=int,
            )
        )

        if not title:

            flash(
                "Title is required.",
                "error",
            )

            return render_template(
                "studio/content_form.html",
                post=None,
                categories=categories,
            )

        if content_type not in {
            "story",
            "reel",
            "vlog",
        }:

            abort(400)

        if access_level not in {
            "public",
            "subscriber",
        }:

            abort(400)

        if (
            access_level == "subscriber"
            and not require_creator_feature(
                account,
                FEATURE_EXCLUSIVE_CONTENT,
            )
        ):

            return render_template(
                "studio/content_form.html",
                post=None,
                categories=categories,
            )

        if status not in {
            "draft",
            "published",
            "archived",
        }:

            abort(400)

        category = None

        if category_id:

            category = (
                creator_category_or_404(
                    account,
                    category_id,
                )
            )

        post = ContentPost(
            creator_account_id=account.id,
            title=title,
            slug=unique_post_slug(
                account,
                title,
            ),
            excerpt=excerpt or None,
            body=body or None,
            content_type=content_type,
            access_level=access_level,
            status=status,
            category=category,
            is_featured=(
                request.form.get(
                    "is_featured"
                )
                == "on"
            ),
        )

        if status == "published":

            post.published_at = (
                utc_now()
            )

        db.session.add(
            post
        )

        db.session.flush()

        success, error = (
            process_cover_image(
                account,
                post,
                request.files.get(
                    "cover_image"
                ),
            )
        )

        if not success:

            db.session.rollback()

            flash(
                error,
                "error",
            )

            return render_template(
                "studio/content_form.html",
                post=None,
                categories=categories,
            )

        if content_type in {
            "reel",
            "vlog",
        }:

            success, error = (
                process_post_video(
                    account,
                    post,
                    request.files.get(
                        "video_file"
                    ),
                )
            )

            if not success:

                db.session.rollback()

                flash(
                    error,
                    "error",
                )

                return render_template(
                    "studio/content_form.html",
                    post=None,
                    categories=categories,
                )

        if content_type == "story":

            success, error = (
                process_story_gallery(
                    account,
                    post,
                    request.files.getlist(
                        "gallery_images"
                    ),
                )
            )

            if not success:

                db.session.rollback()

                flash(
                    error,
                    "error",
                )

                return render_template(
                    "studio/content_form.html",
                    post=None,
                    categories=categories,
                )

        db.session.commit()

        if (
            post.status == "published"
            and post.access_level
            == "public"
        ):

            try:

                notify_subscribers_about_post(
                    post
                )

            except Exception:

                current_app.logger.exception(
                    (
                        "Creator subscriber "
                        "notification failed."
                    )
                )

        flash(
            "Content created successfully.",
            "success",
        )

        return redirect(
            url_for(
                "studio.content_edit",
                post_id=post.id,
            )
        )

    return render_template(
        "studio/content_form.html",
        post=None,
        categories=categories,
    )


# ============================================================
# EDIT CONTENT
# ============================================================

@studio_bp.route(
    "/content/<int:post_id>/edit",
    methods=[
        "GET",
        "POST",
    ],
)
@studio_required
def content_edit(
    post_id,
):

    account = (
        current_creator_account()
    )

    post = creator_post_or_404(
        account,
        post_id,
    )

    categories = (
        ContentCategory.query
        .filter_by(
            creator_account_id=account.id,
            is_active=True,
        )
        .order_by(
            ContentCategory.display_order.asc(),
            ContentCategory.name.asc(),
        )
        .all()
    )

    if request.method == "POST":

        title = (
            request.form
            .get("title", "")
            .strip()
        )

        if not title:

            flash(
                "Title is required.",
                "error",
            )

            return render_template(
                "studio/content_form.html",
                post=post,
                categories=categories,
            )

        content_type = (
            request.form
            .get(
                "content_type",
                "story",
            )
            .strip()
        )

        access_level = (
            request.form
            .get(
                "access_level",
                "public",
            )
            .strip()
        )

        status = (
            request.form
            .get(
                "status",
                "draft",
            )
            .strip()
        )

        if content_type not in {
            "story",
            "reel",
            "vlog",
        }:

            abort(400)

        if access_level not in {
            "public",
            "subscriber",
        }:

            abort(400)

        making_new_exclusive = (
            access_level == "subscriber"
            and post.access_level
            != "subscriber"
        )

        if (
            making_new_exclusive
            and not require_creator_feature(
                account,
                FEATURE_EXCLUSIVE_CONTENT,
            )
        ):

            return render_template(
                "studio/content_form.html",
                post=post,
                categories=categories,
            )

        if status not in {
            "draft",
            "published",
            "archived",
        }:

            abort(400)

        category_id = (
            request.form.get(
                "category_id",
                type=int,
            )
        )

        category = None

        if category_id:

            category = (
                creator_category_or_404(
                    account,
                    category_id,
                )
            )

        previous_status = (
            post.status
        )

        publishing_exclusive = (
            access_level == "subscriber"
            and status == "published"
            and previous_status
            != "published"
        )

        if (
            publishing_exclusive
            and not require_creator_feature(
                account,
                FEATURE_EXCLUSIVE_CONTENT,
            )
        ):

            return render_template(
                "studio/content_form.html",
                post=post,
                categories=categories,
            )

        post.title = title

        post.slug = unique_post_slug(
            account,
            title,
            post.id,
        )

        post.excerpt = (
            request.form
            .get("excerpt", "")
            .strip()
            or None
        )

        post.body = (
            request.form
            .get("body", "")
            .strip()
            or None
        )

        post.content_type = (
            content_type
        )

        post.access_level = (
            access_level
        )

        post.status = status

        post.category = category

        post.is_featured = (
            request.form.get(
                "is_featured"
            )
            == "on"
        )

        if (
            status == "published"
            and previous_status
            != "published"
        ):

            post.published_at = (
                utc_now()
            )

        success, error = (
            process_cover_image(
                account,
                post,
                request.files.get(
                    "cover_image"
                ),
            )
        )

        if not success:

            db.session.rollback()

            flash(
                error,
                "error",
            )

            return redirect(
                url_for(
                    "studio.content_edit",
                    post_id=post.id,
                )
            )

        if content_type in {
            "reel",
            "vlog",
        }:

            success, error = (
                process_post_video(
                    account,
                    post,
                    request.files.get(
                        "video_file"
                    ),
                )
            )

            if not success:

                db.session.rollback()

                flash(
                    error,
                    "error",
                )

                return redirect(
                    url_for(
                        "studio.content_edit",
                        post_id=post.id,
                    )
                )

        if content_type == "story":

            success, error = (
                process_story_gallery(
                    account,
                    post,
                    request.files.getlist(
                        "gallery_images"
                    ),
                )
            )

            if not success:

                db.session.rollback()

                flash(
                    error,
                    "error",
                )

                return redirect(
                    url_for(
                        "studio.content_edit",
                        post_id=post.id,
                    )
                )

        db.session.commit()

        if (
            previous_status
            != "published"
            and post.status
            == "published"
            and post.access_level
            == "public"
        ):

            try:

                notify_subscribers_about_post(
                    post
                )

            except Exception:

                current_app.logger.exception(
                    (
                        "Creator subscriber "
                        "notification failed."
                    )
                )

        flash(
            "Content updated.",
            "success",
        )

        return redirect(
            url_for(
                "studio.content_edit",
                post_id=post.id,
            )
        )

    return render_template(
        "studio/content_form.html",
        post=post,
        categories=categories,
    )


# ============================================================
# PUBLISH CONTENT
# ============================================================

@studio_bp.route(
    "/content/<int:post_id>/publish",
    methods=["POST"],
)
@studio_required
def content_publish(
    post_id,
):

    account = (
        current_creator_account()
    )

    post = creator_post_or_404(
        account,
        post_id,
    )

    if (
        post.access_level == "subscriber"
        and post.status != "published"
        and not require_creator_feature(
            account,
            FEATURE_EXCLUSIVE_CONTENT,
        )
    ):

        return redirect(
            url_for(
                "studio.content_edit",
                post_id=post.id,
            )
        )

    was_published = (
        post.status == "published"
    )

    post.status = "published"

    if not post.published_at:

        post.published_at = (
            utc_now()
        )

    db.session.commit()

    if (
        not was_published
        and post.access_level
        == "public"
    ):

        try:

            notify_subscribers_about_post(
                post
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Creator newsletter "
                    "notification failed."
                )
            )

    flash(
        "Content published.",
        "success",
    )

    return redirect(
        url_for(
            "studio.content_list"
        )
    )


# ============================================================
# ARCHIVE CONTENT
# ============================================================

@studio_bp.route(
    "/content/<int:post_id>/archive",
    methods=["POST"],
)
@studio_required
def content_archive(
    post_id,
):

    account = (
        current_creator_account()
    )

    post = creator_post_or_404(
        account,
        post_id,
    )

    post.status = "archived"

    db.session.commit()

    flash(
        f'"{post.title}" was archived.',
        "success",
    )

    return redirect(
        url_for(
            "studio.content_list"
        )
    )


# ============================================================
# DELETE CONTENT
# ============================================================

@studio_bp.route(
    "/content/<int:post_id>/delete",
    methods=["POST"],
)
@studio_required
def content_delete(
    post_id,
):

    account = (
        current_creator_account()
    )

    post = creator_post_or_404(
        account,
        post_id,
    )

    title = post.title

    for media in list(
        post.media
    ):

        if not media.public_id:

            continue

        try:

            resource_type = (
                media.resource_type
                or (
                    "video"
                    if media.media_type
                    == "video"
                    else "image"
                )
            )

            delete_media(
                media.public_id,
                resource_type=resource_type,
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Creator media "
                    "deletion failed."
                )
            )

    db.session.delete(
        post
    )

    db.session.commit()

    flash(
        f'"{title}" was deleted.',
        "success",
    )

    return redirect(
        url_for(
            "studio.content_list"
        )
    )


# ============================================================
# REMOVE COVER
# ============================================================

@studio_bp.route(
    "/content/<int:post_id>/cover/remove",
    methods=["POST"],
)
@studio_required
def content_remove_cover(
    post_id,
):

    account = (
        current_creator_account()
    )

    post = creator_post_or_404(
        account,
        post_id,
    )

    media = (
        ContentMedia.query
        .filter_by(
            post_id=post.id,
            media_type="cover",
        )
        .first()
    )

    if media:

        if media.public_id:

            try:

                delete_media(
                    media.public_id,
                    resource_type="image",
                )

            except Exception:

                current_app.logger.exception(
                    "Cover deletion failed."
                )

                flash(
                    (
                        "Cover image could "
                        "not be removed."
                    ),
                    "error",
                )

                return redirect(
                    url_for(
                        "studio.content_edit",
                        post_id=post.id,
                    )
                )

        db.session.delete(
            media
        )

    post.cover_image_url = None

    db.session.commit()

    flash(
        "Cover image removed.",
        "success",
    )

    return redirect(
        url_for(
            "studio.content_edit",
            post_id=post.id,
        )
    )


# ============================================================
# REMOVE VIDEO
# ============================================================

@studio_bp.route(
    "/content/<int:post_id>/video/remove",
    methods=["POST"],
)
@studio_required
def content_remove_video(
    post_id,
):

    account = (
        current_creator_account()
    )

    post = creator_post_or_404(
        account,
        post_id,
    )

    media = (
        ContentMedia.query
        .filter_by(
            post_id=post.id,
            media_type="video",
        )
        .first()
    )

    if not media:

        flash(
            "No video was found.",
            "warning",
        )

        return redirect(
            url_for(
                "studio.content_edit",
                post_id=post.id,
            )
        )

    if media.public_id:

        try:

            delete_media(
                media.public_id,
                resource_type="video",
            )

        except Exception:

            current_app.logger.exception(
                "Video deletion failed."
            )

            flash(
                (
                    "Video could not "
                    "be removed."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "studio.content_edit",
                    post_id=post.id,
                )
            )

    db.session.delete(
        media
    )

    db.session.commit()

    flash(
        "Video removed.",
        "success",
    )

    return redirect(
        url_for(
            "studio.content_edit",
            post_id=post.id,
        )
    )


# ============================================================
# REMOVE GALLERY IMAGE
# ============================================================

@studio_bp.route(
    "/content/<int:post_id>/gallery/"
    "<int:media_id>/remove",
    methods=["POST"],
)
@studio_required
def content_remove_gallery_image(
    post_id,
    media_id,
):

    account = (
        current_creator_account()
    )

    post = creator_post_or_404(
        account,
        post_id,
    )

    media = (
        ContentMedia.query
        .filter_by(
            id=media_id,
            post_id=post.id,
            media_type="gallery_image",
        )
        .first_or_404()
    )

    if media.public_id:

        try:

            delete_media(
                media.public_id,
                resource_type="image",
            )

        except Exception:

            current_app.logger.exception(
                "Gallery deletion failed."
            )

            flash(
                (
                    "Gallery image could "
                    "not be removed."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "studio.content_edit",
                    post_id=post.id,
                )
            )

    db.session.delete(
        media
    )

    db.session.commit()

    flash(
        "Gallery image removed.",
        "success",
    )

    return redirect(
        url_for(
            "studio.content_edit",
            post_id=post.id,
        )
    )


# ============================================================
# CATEGORIES
# ============================================================

@studio_bp.route(
    "/categories",
    methods=[
        "GET",
        "POST",
    ],
)
@studio_required
def categories():

    account = (
        current_creator_account()
    )

    if request.method == "POST":

        name = (
            request.form
            .get("name", "")
            .strip()
        )

        description = (
            request.form
            .get("description", "")
            .strip()
        )

        if not name:

            flash(
                "Folder name is required.",
                "error",
            )

            return redirect(
                url_for(
                    "studio.categories"
                )
            )

        count = (
            ContentCategory.query
            .filter_by(
                creator_account_id=account.id
            )
            .count()
        )

        category = ContentCategory(
            creator_account_id=account.id,
            name=name,
            slug=unique_category_slug(
                account,
                name,
            ),
            description=(
                description
                or None
            ),
            is_active=True,
            display_order=count + 1,
        )

        db.session.add(
            category
        )

        db.session.commit()

        flash(
            "Folder created.",
            "success",
        )

        return redirect(
            url_for(
                "studio.categories"
            )
        )

    category_items = (
        ContentCategory.query
        .filter_by(
            creator_account_id=account.id
        )
        .order_by(
            ContentCategory.display_order.asc(),
            ContentCategory.name.asc(),
        )
        .all()
    )

    return render_template(
        "studio/categories.html",
        categories=category_items,
    )


# ============================================================
# PROFILE
# ============================================================

@studio_bp.route(
    "/profile",
    methods=[
        "GET",
        "POST",
    ],
)
@studio_required
def profile():

    account = (
        current_creator_account()
    )

    creator = creator_profile(
        account
    )

    if not creator:

        abort(404)

    if request.method == "POST":

        display_name = (
            request.form
            .get("display_name", "")
            .strip()
        )

        tagline = (
            request.form
            .get("tagline", "")
            .strip()
        )

        bio = (
            request.form
            .get("bio", "")
            .strip()
        )

        if not display_name:

            flash(
                (
                    "Display name "
                    "is required."
                ),
                "error",
            )

            return render_template(
                "studio/profile.html",
                creator=creator,
            )

        creator.username = (
            account.username
        )

        creator.display_name = (
            display_name
        )

        creator.tagline = (
            tagline
            or None
        )

        creator.bio = (
            bio
            or None
        )

        creator.instagram_url = (
            request.form
            .get("instagram_url", "")
            .strip()
            or None
        )

        creator.tiktok_url = (
            request.form
            .get("tiktok_url", "")
            .strip()
            or None
        )

        creator.youtube_url = (
            request.form
            .get("youtube_url", "")
            .strip()
            or None
        )

        profile_image = (
            request.files.get(
                "profile_image"
            )
        )

        if (
            profile_image
            and profile_image.filename
        ):

            valid, error = (
                validate_image(
                    profile_image
                )
            )

            if not valid:

                flash(
                    error,
                    "error",
                )

                return render_template(
                    "studio/profile.html",
                    creator=creator,
                )

            root = current_app.config.get(
                "CLOUDINARY_FOLDER",
                "creator-blog",
            )

            result = upload_image(
                profile_image,
                folder=(
                    f"{root}/creators/"
                    f"{account.id}/profile"
                ),
            )

            old_id = (
                creator.profile_image_public_id
            )

            creator.profile_image_url = (
                result["url"]
            )

            creator.profile_image_public_id = (
                result["public_id"]
            )

            if old_id:

                try:

                    delete_media(
                        old_id,
                        resource_type="image",
                    )

                except Exception:

                    current_app.logger.exception(
                        (
                            "Old profile image "
                            "deletion failed."
                        )
                    )

        intro_reel = (
            request.files.get(
                "intro_reel"
            )
        )

        if (
            intro_reel
            and intro_reel.filename
        ):

            valid, error = (
                validate_video(
                    intro_reel
                )
            )

            if not valid:

                flash(
                    error,
                    "error",
                )

                return render_template(
                    "studio/profile.html",
                    creator=creator,
                )

            root = current_app.config.get(
                "CLOUDINARY_FOLDER",
                "creator-blog",
            )

            result = upload_video(
                intro_reel,
                folder=(
                    f"{root}/creators/"
                    f"{account.id}/"
                    "intro-reels"
                ),
            )

            old_id = (
                creator.intro_reel_public_id
            )

            creator.intro_reel_url = (
                result["url"]
            )

            creator.intro_reel_public_id = (
                result["public_id"]
            )

            creator.intro_reel_thumbnail_url = (
                result.get(
                    "thumbnail_url"
                )
            )

            if old_id:

                try:

                    delete_media(
                        old_id,
                        resource_type="video",
                    )

                except Exception:

                    current_app.logger.exception(
                        (
                            "Old intro reel "
                            "deletion failed."
                        )
                    )

        db.session.commit()

        flash(
            (
                "Profile updated "
                "successfully."
            ),
            "success",
        )

        return redirect(
            url_for(
                "studio.profile"
            )
        )

    return render_template(
        "studio/profile.html",
        creator=creator,
    )


# ============================================================
# COMMENTS
# ============================================================

@studio_bp.route(
    "/comments"
)
@studio_required
def comments():

    account = (
        current_creator_account()
    )

    status = (
        request.args
        .get("status", "")
        .strip()
    )

    query = (
        Comment.query
        .join(
            ContentPost,
            Comment.post_id
            == ContentPost.id,
        )
        .filter(
            ContentPost.creator_account_id
            == account.id
        )
    )

    if status in {
        "approved",
        "hidden",
        "pending",
    }:

        query = query.filter(
            Comment.status == status
        )

    items = (
        query
        .order_by(
            Comment.created_at.desc()
        )
        .all()
    )

    return render_template(
        "studio/comments.html",
        comments=items,
        selected_status=status,
    )


# ============================================================
# COMMENT APPROVE
# ============================================================

@studio_bp.route(
    "/comments/<int:comment_id>/approve",
    methods=["POST"],
)
@studio_required
def comment_approve(
    comment_id,
):

    account = (
        current_creator_account()
    )

    comment = (
        creator_comment_or_404(
            account,
            comment_id,
        )
    )

    comment.status = "approved"

    db.session.commit()

    flash(
        "Comment approved.",
        "success",
    )

    return redirect(
        request.referrer
        or url_for(
            "studio.comments"
        )
    )


# ============================================================
# COMMENT HIDE
# ============================================================

@studio_bp.route(
    "/comments/<int:comment_id>/hide",
    methods=["POST"],
)
@studio_required
def comment_hide(
    comment_id,
):

    account = (
        current_creator_account()
    )

    comment = (
        creator_comment_or_404(
            account,
            comment_id,
        )
    )

    comment.status = "hidden"

    if comment.parent_id is None:

        for reply in comment.replies:

            reply.status = "hidden"

    db.session.commit()

    flash(
        "Comment hidden.",
        "success",
    )

    return redirect(
        request.referrer
        or url_for(
            "studio.comments"
        )
    )


# ============================================================
# COMMENT DELETE
# ============================================================

@studio_bp.route(
    "/comments/<int:comment_id>/delete",
    methods=["POST"],
)
@studio_required
def comment_delete(
    comment_id,
):

    account = (
        current_creator_account()
    )

    comment = (
        creator_comment_or_404(
            account,
            comment_id,
        )
    )

    db.session.delete(
        comment
    )

    db.session.commit()

    flash(
        "Comment deleted.",
        "success",
    )

    return redirect(
        request.referrer
        or url_for(
            "studio.comments"
        )
    )


# ============================================================
# CREATOR REPLY
# ============================================================

@studio_bp.route(
    "/comments/<int:comment_id>/reply",
    methods=["POST"],
)
@studio_required
def comment_creator_reply(
    comment_id,
):

    account = (
        current_creator_account()
    )

    parent = (
        creator_comment_or_404(
            account,
            comment_id,
        )
    )

    if parent.parent_id is not None:

        abort(400)

    body = (
        request.form
        .get("body", "")
        .strip()
    )

    if (
        not body
        or len(body) > 1500
    ):

        flash(
            "Enter a valid reply.",
            "error",
        )

        return redirect(
            url_for(
                "studio.comments"
            )
        )

    profile_item = (
        creator_profile(
            account
        )
    )

    reply = Comment(
        post_id=parent.post_id,
        parent_id=parent.id,
        author_name=(
            profile_item.display_name
            if profile_item
            else account.username
        ),
        body=body,
        status="approved",
        is_creator=True,
        anonymous_session_id=None,
    )

    db.session.add(
        reply
    )

    db.session.commit()

    flash(
        "Your reply was posted.",
        "success",
    )

    return redirect(
        url_for(
            "studio.comments"
        )
    )


# ============================================================
# SUBSCRIBERS
# ============================================================

@studio_bp.route(
    "/subscribers"
)
@studio_required
def subscribers():

    account = (
        current_creator_account()
    )

    status = (
        request.args
        .get("status", "")
        .strip()
    )

    query = (
        EmailSubscriber.query
        .filter_by(
            creator_account_id=account.id
        )
    )

    if status in {
        "pending",
        "active",
        "unsubscribed",
    }:

        query = query.filter_by(
            status=status
        )

    subscriber_items = (
        query
        .order_by(
            EmailSubscriber.created_at.desc()
        )
        .all()
    )

    return render_template(
        "studio/subscribers.html",
        subscribers=subscriber_items,
        selected_status=status,
    )


# ============================================================
# ANALYTICS
# ============================================================

@studio_bp.route(
    "/analytics"
)
@studio_required
def analytics():

    account = (
        current_creator_account()
    )

    posts = (
        ContentPost.query
        .filter_by(
            creator_account_id=account.id
        )
    )

    subscriber_query = (
        EmailSubscriber.query
        .filter_by(
            creator_account_id=account.id
        )
    )

    comment_query = (
        Comment.query
        .join(
            ContentPost,
            Comment.post_id
            == ContentPost.id,
        )
        .filter(
            ContentPost.creator_account_id
            == account.id
        )
    )

    return render_template(
        "studio/analytics.html",

        creator=creator_profile(
            account
        ),

        total_posts=posts.count(),

        published_posts=(
            posts
            .filter_by(
                status="published"
            )
            .count()
        ),

        draft_posts=(
            posts
            .filter_by(
                status="draft"
            )
            .count()
        ),

        archived_posts=(
            posts
            .filter_by(
                status="archived"
            )
            .count()
        ),

        public_posts=(
            posts
            .filter_by(
                access_level="public"
            )
            .count()
        ),

        exclusive_posts=(
            posts
            .filter_by(
                access_level="subscriber"
            )
            .count()
        ),

        story_count=(
            posts
            .filter_by(
                content_type="story"
            )
            .count()
        ),

        reel_count=(
            posts
            .filter_by(
                content_type="reel"
            )
            .count()
        ),

        vlog_count=(
            posts
            .filter_by(
                content_type="vlog"
            )
            .count()
        ),

        comment_count=(
            comment_query.count()
        ),

        approved_comment_count=(
            comment_query
            .filter(
                Comment.status
                == "approved"
            )
            .count()
        ),

        pending_comment_count=(
            comment_query
            .filter(
                Comment.status
                == "pending"
            )
            .count()
        ),

        hidden_comment_count=(
            comment_query
            .filter(
                Comment.status
                == "hidden"
            )
            .count()
        ),

        subscriber_count=(
            subscriber_query.count()
        ),

        active_subscriber_count=(
            subscriber_query
            .filter_by(
                status="active"
            )
            .count()
        ),

        pending_subscriber_count=(
            subscriber_query
            .filter_by(
                status="pending"
            )
            .count()
        ),

        unsubscribed_count=(
            subscriber_query
            .filter_by(
                status="unsubscribed"
            )
            .count()
        ),

        recent_posts=(
            posts
            .order_by(
                ContentPost.created_at.desc()
            )
            .limit(10)
            .all()
        ),
    )


# ============================================================
# REMOVE PROFILE IMAGE
# ============================================================

@studio_bp.route(
    "/profile/remove-image",
    methods=["POST"],
)
@studio_required
def profile_remove_image():

    account = (
        current_creator_account()
    )

    creator = creator_profile(
        account
    )

    if not creator:

        abort(404)

    if creator.profile_image_public_id:

        try:

            delete_media(
                creator.profile_image_public_id,
                resource_type="image",
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Creator profile image "
                    "deletion failed."
                )
            )

            flash(
                (
                    "Profile image could "
                    "not be removed."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "studio.profile"
                )
            )

    creator.profile_image_url = None

    creator.profile_image_public_id = None

    db.session.commit()

    flash(
        "Profile image removed.",
        "success",
    )

    return redirect(
        url_for(
            "studio.profile"
        )
    )


# ============================================================
# REMOVE INTRO REEL
# ============================================================

@studio_bp.route(
    "/profile/remove-intro-reel",
    methods=["POST"],
)
@studio_required
def profile_remove_intro_reel():

    account = (
        current_creator_account()
    )

    creator = creator_profile(
        account
    )

    if not creator:

        abort(404)

    if creator.intro_reel_public_id:

        try:

            delete_media(
                creator.intro_reel_public_id,
                resource_type="video",
            )

        except Exception:

            current_app.logger.exception(
                (
                    "Creator intro reel "
                    "deletion failed."
                )
            )

            flash(
                (
                    "Intro reel could "
                    "not be removed."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "studio.profile"
                )
            )

    creator.intro_reel_url = None

    creator.intro_reel_public_id = None

    creator.intro_reel_thumbnail_url = None

    db.session.commit()

    flash(
        "Intro reel removed.",
        "success",
    )

    return redirect(
        url_for(
            "studio.profile"
        )
    )


# ============================================================
# WEBSITE SETTINGS
# ============================================================

from routes.website_settings_routes import (
    register_website_settings,
)

register_website_settings(
    studio_bp,
    studio_required,
    current_creator_account,
)
