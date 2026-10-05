# ============================================================
# CREATOR PLATFORM
# PUBLIC ROUTES
# ============================================================

import secrets
import time

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
    CreatorAccount,
    CreatorProfile,
    ContentCategory,
    ContentPost,
    ContentMedia,
    Comment,
    EmailSubscriber,
    utc_now,
)

from services.email_service import (
    send_verification_email,
    send_welcome_email,
)


# ============================================================
# BLUEPRINT
# ============================================================

public_bp = Blueprint(
    "public",
    __name__,
)


# ============================================================
# COMMENT SETTINGS
# ============================================================

COMMENT_MAX_LENGTH = 1500
AUTHOR_MAX_LENGTH = 80
COMMENT_COOLDOWN_SECONDS = 8


# ============================================================
# LEGACY / DEFAULT CREATOR
# ============================================================

def get_current_creator():
    """
    Return the original creator that powers the root website.

    "/" remains the legacy/default creator website while
    multi-creator pages use:

        /@username
    """

    return (
        CreatorProfile.query
        .order_by(
            CreatorProfile.id.asc()
        )
        .first()
    )


def get_current_creator_account_id():
    """
    Return the CreatorAccount ID belonging to the
    legacy/default creator.
    """

    creator = get_current_creator()

    if not creator:
        return None

    return creator.creator_account_id


# ============================================================
# PUBLIC CREATOR RESOLUTION
# ============================================================

def get_public_creator_account(
    username,
):
    """
    Resolve an active public creator account.

    Suspended, rejected, pending-payment and pending-approval
    accounts are intentionally not exposed as public creator
    websites.

    Subscription status is intentionally not checked here.

    An expired creator subscription locks Creator Studio but
    does not automatically remove already-published content.
    """

    normalized_username = (
        username
        .strip()
        .lower()
    )

    account = (
        CreatorAccount.query
        .filter(
            db.func.lower(
                CreatorAccount.username
            )
            == normalized_username,

            CreatorAccount.account_status
            == "active",
        )
        .first()
    )

    if not account:
        abort(404)

    return account


def get_public_creator_profile(
    account,
):
    """
    Return the public profile belonging to a CreatorAccount.
    """

    creator = (
        CreatorProfile.query
        .filter_by(
            creator_account_id=account.id
        )
        .first()
    )

    if not creator:
        abort(404)

    return creator


# ============================================================
# PUBLIC CREATOR URL HELPERS
# ============================================================

def creator_home_url(
    account,
):
    """
    Build the public URL for a creator.
    """

    return url_for(
        "public.creator_home",
        username=account.username,
    )


def creator_content_url(
    account,
    post,
):
    """
    Build the public URL for creator content.
    """

    return url_for(
        "public.creator_content_detail",
        username=account.username,
        slug=post.slug,
    )


# ============================================================
# ANONYMOUS SESSION
# ============================================================

def get_anonymous_session_id():
    """
    Create or return an anonymous browser/session identifier.
    """

    anonymous_id = session.get(
        "anonymous_session_id"
    )

    if not anonymous_id:

        anonymous_id = (
            secrets.token_urlsafe(
                24
            )
        )

        session[
            "anonymous_session_id"
        ] = anonymous_id

    return anonymous_id


# ============================================================
# COMMENT COOLDOWN
# ============================================================

def comment_rate_limited():
    """
    Basic session-level cooldown for anonymous comments.

    This is intentionally lightweight for the MVP.
    """

    current_time = time.time()

    previous_time = session.get(
        "last_comment_time"
    )

    if previous_time:

        difference = (
            current_time
            - previous_time
        )

        if (
            difference
            < COMMENT_COOLDOWN_SECONDS
        ):
            return True

    session[
        "last_comment_time"
    ] = current_time

    return False


# ============================================================
# SHARED CREATOR HOME RENDERER
# ============================================================

def render_creator_home(
    creator,
    creator_account_id,
    public_username=None,
):
    """
    Render a creator homepage.

    public_username is intentionally explicit.

    Legacy "/" does not pass it.
    Multi-creator "/@username" does.

    This prevents the legacy root site from accidentally
    switching all links to /@username merely because the
    legacy profile has now been backfilled to CreatorAccount.
    """

    categories = (
        ContentCategory.query
        .filter_by(
            creator_account_id=(
                creator_account_id
            ),
            is_active=True,
        )
        .order_by(
            ContentCategory.display_order.asc(),
            ContentCategory.name.asc(),
        )
        .all()
    )

    posts = (
        ContentPost.query
        .filter_by(
            creator_account_id=(
                creator_account_id
            ),
            status="published",
        )
        .order_by(
            ContentPost.published_at.desc(),
            ContentPost.created_at.desc(),
        )
        .limit(12)
        .all()
    )

    return render_template(
        "public/home.html",
        creator=creator,
        categories=categories,
        posts=posts,
        public_username=public_username,
    )


# ============================================================
# SHARED CONTENT RENDERER
# ============================================================

def render_content_detail(
    creator,
    post,
    public_username=None,
):
    """
    Render a public content page.
    """

    gallery_images = (
        ContentMedia.query
        .filter_by(
            post_id=post.id,
            media_type="gallery_image",
        )
        .order_by(
            ContentMedia.media_order.asc()
        )
        .all()
    )

    video = (
        ContentMedia.query
        .filter_by(
            post_id=post.id,
            media_type="video",
        )
        .first()
    )

    comments = (
        Comment.query
        .filter_by(
            post_id=post.id,
            parent_id=None,
            status="approved",
        )
        .order_by(
            Comment.created_at.desc()
        )
        .all()
    )

    comment_count = (
        Comment.query
        .filter_by(
            post_id=post.id,
            status="approved",
        )
        .count()
    )

    return render_template(
        "public/content_detail.html",
        creator=creator,
        post=post,
        gallery_images=gallery_images,
        video=video,
        comments=comments,
        comment_count=comment_count,
        public_username=public_username,
    )


# ============================================================
# LEGACY ROOT HOME
# ============================================================

@public_bp.route("/")
def home():
    """
    Original/default creator homepage.
    """

    creator = get_current_creator()

    if not creator:
        abort(404)

    creator_account_id = (
        creator.creator_account_id
    )

    # --------------------------------------------------------
    # TEMPORARY LEGACY FALLBACK
    # --------------------------------------------------------
    #
    # Before ownership backfill, the original creator may
    # still have creator_account_id=None.
    # --------------------------------------------------------

    if creator_account_id is None:

        categories = (
            ContentCategory.query
            .filter_by(
                is_active=True
            )
            .order_by(
                ContentCategory.display_order.asc(),
                ContentCategory.name.asc(),
            )
            .all()
        )

        posts = (
            ContentPost.query
            .filter_by(
                status="published"
            )
            .order_by(
                ContentPost.published_at.desc(),
                ContentPost.created_at.desc(),
            )
            .limit(12)
            .all()
        )

        return render_template(
            "public/home.html",
            creator=creator,
            categories=categories,
            posts=posts,
            public_username=None,
        )

    return render_creator_home(
        creator=creator,
        creator_account_id=creator_account_id,
        public_username=None,
    )


# ============================================================
# MULTI-CREATOR HOME
# /@username
# ============================================================

@public_bp.route(
    "/@<string:username>"
)
def creator_home(
    username,
):
    """
    Public SaaS creator homepage.
    """

    account = (
        get_public_creator_account(
            username
        )
    )

    creator = (
        get_public_creator_profile(
            account
        )
    )

    return render_creator_home(
        creator=creator,
        creator_account_id=account.id,
        public_username=account.username,
    )


# ============================================================
# LEGACY CONTENT DETAIL
# ============================================================

@public_bp.route(
    "/content/<string:slug>"
)
def content_detail(
    slug,
):
    """
    Content detail for the original/default root creator.
    """

    creator = get_current_creator()

    if not creator:
        abort(404)

    creator_account_id = (
        creator.creator_account_id
    )

    query = (
        ContentPost.query
        .filter_by(
            slug=slug,
            status="published",
        )
    )

    if creator_account_id is not None:

        query = query.filter_by(
            creator_account_id=(
                creator_account_id
            )
        )

    post = query.first_or_404()

    return render_content_detail(
        creator=creator,
        post=post,
        public_username=None,
    )


# ============================================================
# MULTI-CREATOR CONTENT DETAIL
# /@username/content/slug
# ============================================================

@public_bp.route(
    "/@<string:username>/content/<string:slug>"
)
def creator_content_detail(
    username,
    slug,
):
    """
    Content detail belonging to a specific creator.
    """

    account = (
        get_public_creator_account(
            username
        )
    )

    creator = (
        get_public_creator_profile(
            account
        )
    )

    post = (
        ContentPost.query
        .filter_by(
            creator_account_id=account.id,
            slug=slug,
            status="published",
        )
        .first_or_404()
    )

    return render_content_detail(
        creator=creator,
        post=post,
        public_username=account.username,
    )


# ============================================================
# LEGACY ADD COMMENT
# ============================================================

@public_bp.route(
    "/content/<int:post_id>/comments",
    methods=["POST"],
)
def add_comment(
    post_id,
):
    """
    Add a comment to content belonging to the
    original/default creator.
    """

    creator = get_current_creator()

    if not creator:
        abort(404)

    post = (
        ContentPost.query
        .filter_by(
            id=post_id,
            status="published",
        )
        .first_or_404()
    )

    if (
        creator.creator_account_id
        is not None
        and post.creator_account_id
        != creator.creator_account_id
    ):
        abort(404)

    return process_comment(
        post=post,
        redirect_endpoint=(
            "public.content_detail"
        ),
        redirect_values={
            "slug": post.slug,
        },
    )


# ============================================================
# MULTI-CREATOR ADD COMMENT
# ============================================================

@public_bp.route(
    "/@<string:username>/content/"
    "<int:post_id>/comments",
    methods=["POST"],
)
def creator_add_comment(
    username,
    post_id,
):
    """
    Add a comment to a specific creator's content.
    """

    account = (
        get_public_creator_account(
            username
        )
    )

    post = (
        ContentPost.query
        .filter_by(
            id=post_id,
            creator_account_id=account.id,
            status="published",
        )
        .first_or_404()
    )

    return process_comment(
        post=post,
        redirect_endpoint=(
            "public.creator_content_detail"
        ),
        redirect_values={
            "username": account.username,
            "slug": post.slug,
        },
    )


# ============================================================
# COMMENT PROCESSOR
# ============================================================

def process_comment(
    post,
    redirect_endpoint,
    redirect_values,
):
    """
    Shared anonymous comment creation logic.
    """

    def redirect_to_comments():

        return redirect(
            url_for(
                redirect_endpoint,
                **redirect_values,
            )
            + "#comments"
        )

    # ========================================================
    # HONEYPOT
    # ========================================================

    website = (
        request.form
        .get(
            "website",
            "",
        )
        .strip()
    )

    if website:
        return redirect_to_comments()

    # ========================================================
    # RATE LIMIT
    # ========================================================

    if comment_rate_limited():

        flash(
            "Please wait a few seconds before "
            "posting another comment.",
            "warning",
        )

        return redirect_to_comments()

    # ========================================================
    # FORM
    # ========================================================

    author_name = (
        request.form
        .get(
            "author_name",
            "",
        )
        .strip()
    )

    body = (
        request.form
        .get(
            "body",
            "",
        )
        .strip()
    )

    # ========================================================
    # VALIDATION
    # ========================================================

    if not author_name:

        flash(
            "Enter your name before commenting.",
            "error",
        )

        return redirect_to_comments()

    if len(author_name) > AUTHOR_MAX_LENGTH:

        flash(
            "Your name is too long.",
            "error",
        )

        return redirect_to_comments()

    if not body:

        flash(
            "Write something before posting.",
            "error",
        )

        return redirect_to_comments()

    if len(body) > COMMENT_MAX_LENGTH:

        flash(
            "Your comment is too long.",
            "error",
        )

        return redirect_to_comments()

    # ========================================================
    # SAVE
    # ========================================================

    comment = Comment(
        post_id=post.id,
        author_name=author_name,
        body=body,
        status="approved",
        is_creator=False,
        anonymous_session_id=(
            get_anonymous_session_id()
        ),
    )

    db.session.add(
        comment
    )

    db.session.commit()

    flash(
        "Your comment was posted.",
        "success",
    )

    return redirect_to_comments()


# ============================================================
# LEGACY ADD REPLY
# ============================================================

@public_bp.route(
    "/comments/<int:comment_id>/reply",
    methods=["POST"],
)
def add_reply(
    comment_id,
):
    """
    Add a reply on the original/default creator website.
    """

    creator = get_current_creator()

    if not creator:
        abort(404)

    parent = (
        db.session.get(
            Comment,
            comment_id,
        )
    )

    if not parent:
        abort(404)

    post = parent.post

    if not post:
        abort(404)

    if post.status != "published":
        abort(404)

    if (
        creator.creator_account_id
        is not None
        and post.creator_account_id
        != creator.creator_account_id
    ):
        abort(404)

    return process_reply(
        parent=parent,
        post=post,
        redirect_endpoint=(
            "public.content_detail"
        ),
        redirect_values={
            "slug": post.slug,
        },
    )


# ============================================================
# MULTI-CREATOR ADD REPLY
# ============================================================

@public_bp.route(
    "/@<string:username>/comments/"
    "<int:comment_id>/reply",
    methods=["POST"],
)
def creator_add_reply(
    username,
    comment_id,
):
    """
    Add a reply to a comment belonging to a specific
    creator's published content.
    """

    account = (
        get_public_creator_account(
            username
        )
    )

    parent = (
        Comment.query
        .join(
            ContentPost,
            Comment.post_id
            == ContentPost.id,
        )
        .filter(
            Comment.id == comment_id,
            ContentPost.creator_account_id
            == account.id,
            ContentPost.status
            == "published",
        )
        .first_or_404()
    )

    post = parent.post

    return process_reply(
        parent=parent,
        post=post,
        redirect_endpoint=(
            "public.creator_content_detail"
        ),
        redirect_values={
            "username": account.username,
            "slug": post.slug,
        },
    )


# ============================================================
# REPLY PROCESSOR
# ============================================================

def process_reply(
    parent,
    post,
    redirect_endpoint,
    redirect_values,
):
    """
    Shared anonymous reply creation logic.
    """

    # ========================================================
    # ONLY ONE LEVEL OF REPLIES
    # ========================================================

    if parent.parent_id is not None:
        abort(400)

    def redirect_to_parent():

        return redirect(
            url_for(
                redirect_endpoint,
                **redirect_values,
            )
            + f"#comment-{parent.id}"
        )

    # ========================================================
    # HONEYPOT
    # ========================================================

    website = (
        request.form
        .get(
            "website",
            "",
        )
        .strip()
    )

    if website:
        return redirect_to_parent()

    # ========================================================
    # RATE LIMIT
    # ========================================================

    if comment_rate_limited():

        flash(
            "Please wait a few seconds before "
            "posting another reply.",
            "warning",
        )

        return redirect_to_parent()

    # ========================================================
    # FORM
    # ========================================================

    author_name = (
        request.form
        .get(
            "author_name",
            "",
        )
        .strip()
    )

    body = (
        request.form
        .get(
            "body",
            "",
        )
        .strip()
    )

    # ========================================================
    # VALIDATION
    # ========================================================

    if not author_name:

        flash(
            "Enter your name before replying.",
            "error",
        )

        return redirect_to_parent()

    if len(author_name) > AUTHOR_MAX_LENGTH:

        flash(
            "Your name is too long.",
            "error",
        )

        return redirect_to_parent()

    if not body:

        flash(
            "Write something before replying.",
            "error",
        )

        return redirect_to_parent()

    if len(body) > COMMENT_MAX_LENGTH:

        flash(
            "Your reply is too long.",
            "error",
        )

        return redirect_to_parent()

    # ========================================================
    # SAVE
    # ========================================================

    reply = Comment(
        post_id=post.id,
        parent_id=parent.id,
        author_name=author_name,
        body=body,
        status="approved",
        is_creator=False,
        anonymous_session_id=(
            get_anonymous_session_id()
        ),
    )

    db.session.add(
        reply
    )

    db.session.commit()

    flash(
        "Your reply was posted.",
        "success",
    )

    return redirect_to_parent()


# ============================================================
# LEGACY NEWSLETTER SUBSCRIBE
# ============================================================

@public_bp.route(
    "/newsletter/subscribe",
    methods=["POST"],
)
def newsletter_subscribe():
    """
    Newsletter subscription for the original/default creator.
    """

    creator = get_current_creator()

    if not creator:
        abort(404)

    if creator.creator_account_id is None:

        abort(
            503,
            description=(
                "Creator ownership has not "
                "been configured yet."
            ),
        )

    return process_newsletter_subscription(
        creator_account_id=(
            creator.creator_account_id
        ),
        redirect_endpoint="public.home",
        redirect_values={},
    )


# ============================================================
# MULTI-CREATOR NEWSLETTER SUBSCRIBE
# ============================================================

@public_bp.route(
    "/@<string:username>/newsletter/subscribe",
    methods=["POST"],
)
def creator_newsletter_subscribe(
    username,
):
    """
    Newsletter subscription for a specific creator.
    """

    account = (
        get_public_creator_account(
            username
        )
    )

    return process_newsletter_subscription(
        creator_account_id=account.id,
        redirect_endpoint=(
            "public.creator_home"
        ),
        redirect_values={
            "username": account.username,
        },
    )


# ============================================================
# NEWSLETTER SUBSCRIPTION PROCESSOR
# ============================================================

def process_newsletter_subscription(
    creator_account_id,
    redirect_endpoint,
    redirect_values,
):
    """
    Shared tenant-safe newsletter subscription logic.
    """

    def redirect_to_newsletter():

        return redirect(
            url_for(
                redirect_endpoint,
                **redirect_values,
            )
            + "#newsletter"
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

    # ========================================================
    # HONEYPOT
    # ========================================================

    website = (
        request.form
        .get(
            "website",
            "",
        )
        .strip()
    )

    if website:
        return redirect_to_newsletter()

    # ========================================================
    # VALIDATION
    # ========================================================

    if (
        not email
        or "@" not in email
        or "." not in email.split("@")[-1]
        or len(email) > 255
    ):

        flash(
            "Enter a valid email address.",
            "error",
        )

        return redirect_to_newsletter()

    # ========================================================
    # STRICT TENANT LOOKUP
    # ========================================================

    subscriber = (
        EmailSubscriber.query
        .filter_by(
            creator_account_id=(
                creator_account_id
            ),
            email=email,
        )
        .first()
    )

    # ========================================================
    # ALREADY ACTIVE
    # ========================================================

    if (
        subscriber
        and subscriber.status
        == "active"
    ):

        flash(
            "You're already subscribed.",
            "success",
        )

        return redirect_to_newsletter()

    # ========================================================
    # CREATE / REACTIVATE
    # ========================================================

    verification_token = (
        secrets.token_urlsafe(
            48
        )
    )

    unsubscribe_token = (
        secrets.token_urlsafe(
            48
        )
    )

    if subscriber:

        subscriber.status = "pending"

        subscriber.verification_token = (
            verification_token
        )

        if not subscriber.unsubscribe_token:

            subscriber.unsubscribe_token = (
                unsubscribe_token
            )

        subscriber.verified_at = None
        subscriber.unsubscribed_at = None

    else:

        subscriber = EmailSubscriber(
            creator_account_id=(
                creator_account_id
            ),
            email=email,
            status="pending",
            verification_token=(
                verification_token
            ),
            unsubscribe_token=(
                unsubscribe_token
            ),
        )

        db.session.add(
            subscriber
        )

    db.session.commit()

    # ========================================================
    # SEND TENANT-AWARE VERIFICATION
    # ========================================================

    sent = send_verification_email(
        subscriber
    )

    if sent:

        flash(
            "Check your inbox and confirm "
            "your email to finish subscribing.",
            "success",
        )

    else:

        flash(
            "Your email was saved, but the "
            "verification email could not be "
            "sent. Please try again shortly.",
            "error",
        )

    return redirect_to_newsletter()


# ============================================================
# VERIFY NEWSLETTER EMAIL
# ============================================================

@public_bp.route(
    "/newsletter/verify/<string:token>"
)
def newsletter_verify(
    token,
):
    """
    Verify a newsletter subscriber.

    Verification tokens are globally unique enough for
    direct token resolution, while the subscriber itself
    remains attached to one creator account.
    """

    subscriber = (
        EmailSubscriber.query
        .filter_by(
            verification_token=token
        )
        .first()
    )

    if not subscriber:

        return render_template(
            "public/newsletter_message.html",
            title="Invalid link",
            heading="This link isn't valid.",
            message=(
                "The verification link may "
                "have expired or already been used."
            ),
        ), 404

    # --------------------------------------------------------
    # SUBSCRIBER MUST BELONG TO A CREATOR
    # --------------------------------------------------------

    if subscriber.creator_account_id is None:

        return render_template(
            "public/newsletter_message.html",
            title="Subscription unavailable",
            heading=(
                "We couldn't confirm this subscription."
            ),
            message=(
                "This subscription is not connected "
                "to a creator account."
            ),
        ), 400

    account = db.session.get(
        CreatorAccount,
        subscriber.creator_account_id,
    )

    if not account:
        abort(404)

    subscriber.status = "active"

    subscriber.verified_at = (
        utc_now()
    )

    subscriber.unsubscribed_at = None

    # --------------------------------------------------------
    # ONE-TIME VERIFICATION TOKEN
    # --------------------------------------------------------

    subscriber.verification_token = None

    db.session.commit()

    # --------------------------------------------------------
    # TENANT-AWARE WELCOME EMAIL
    # --------------------------------------------------------

    send_welcome_email(
        subscriber
    )

    return render_template(
        "public/newsletter_message.html",
        title="Subscription confirmed",
        heading="You're in.",
        message=(
            "Your email is confirmed. "
            "You'll now receive updates "
            "when new content is published."
        ),
        creator_username=account.username,
    )


# ============================================================
# UNSUBSCRIBE
# ============================================================

@public_bp.route(
    "/newsletter/unsubscribe/<string:token>"
)
def newsletter_unsubscribe(
    token,
):
    """
    Unsubscribe a newsletter subscriber.
    """

    subscriber = (
        EmailSubscriber.query
        .filter_by(
            unsubscribe_token=token
        )
        .first()
    )

    if not subscriber:

        return render_template(
            "public/newsletter_message.html",
            title="Invalid link",
            heading="This link isn't valid.",
            message=(
                "We couldn't find a subscription "
                "for this unsubscribe link."
            ),
        ), 404

    subscriber.status = (
        "unsubscribed"
    )

    subscriber.unsubscribed_at = (
        utc_now()
    )

    subscriber.verification_token = None

    db.session.commit()

    creator_username = None

    if subscriber.creator_account_id:

        account = db.session.get(
            CreatorAccount,
            subscriber.creator_account_id,
        )

        if account:

            creator_username = (
                account.username
            )

    return render_template(
        "public/newsletter_message.html",
        title="Unsubscribed",
        heading="You've been unsubscribed.",
        message=(
            "You won't receive new-post "
            "emails from this creator anymore. "
            "You can subscribe again from their "
            "website at any time."
        ),
        creator_username=creator_username,
    )
