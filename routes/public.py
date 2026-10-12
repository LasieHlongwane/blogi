"""
KALXA CREATOR — PUBLIC ROUTES

Responsibilities
----------------
1. Kalxa Creator platform homepage
2. Individual creator websites
3. Custom-domain creator websites
4. Public creator content
5. Anonymous comments and replies
6. Creator-specific newsletters
7. Tenant-safe public branding

URL STRUCTURE
-------------

Platform domain:

    /                           Kalxa Creator homepage
    /@username                  Creator website
    /@username/content/slug     Creator content

Custom creator domain:

    /                           Creator website
    /content/slug               Creator content

IMPORTANT
---------
The platform root no longer automatically displays
the first CreatorProfile in the database.
"""

import re
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
    g,
)

from extensions import db

from models import (
    CreatorAccount,
    CreatorProfile,
    CreatorBranding,
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
# CONSTANTS
# ============================================================

COMMENT_MAX_LENGTH = 1500

AUTHOR_MAX_LENGTH = 80

COMMENT_COOLDOWN_SECONDS = 8


# ============================================================
# BRANDING DEFAULTS
# ============================================================

BRANDING_DEFAULTS = {
    "primary_color": "#111318",
    "accent_color": "#F4B942",
    "background_color": "#FFFFFF",
    "text_color": "#17191D",
    "theme": "light",
    "font_family": "system",
}


# ============================================================
# HOSTED CREATOR ACCOUNT
# ============================================================

def hosted_account():
    """
    Return the creator account resolved by custom-domain
    middleware.

    Expected:

        g.creator_domain_account

    None means the request is using the Kalxa platform
    domain or another non-tenant host.
    """

    return getattr(
        g,
        "creator_domain_account",
        None,
    )


# ============================================================
# CURRENT CREATOR
# ============================================================

def get_current_creator():
    """
    Return the creator profile only when the request
    is associated with a hosted creator domain.

    IMPORTANT:

    Do not automatically return the first creator
    in the database.

    That legacy behavior caused the Kalxa Creator
    platform homepage to display Lasie's website.
    """

    account = hosted_account()

    if account is None:
        return None

    return CreatorProfile.query.filter_by(
        creator_account_id=account.id,
    ).first()


def get_current_creator_account_id():
    """
    Return the current hosted creator account ID.

    Returns None on the Kalxa platform domain.
    """

    account = hosted_account()

    return account.id if account else None


# ============================================================
# PUBLIC CREATOR ACCOUNT LOOKUP
# ============================================================

def get_public_creator_account(username):
    """
    Resolve an active creator account by username.

    Platform domain:

        /@username

    Custom domain:

        Only the creator associated with the custom
        domain can be accessed.
    """

    normalized_username = (
        username or ""
    ).strip().lower()

    if not normalized_username:
        abort(404)

    hosted = hosted_account()

    if hosted:

        hosted_username = (
            hosted.username or ""
        ).strip().lower()

        if hosted_username != normalized_username:
            abort(404)

    account = CreatorAccount.query.filter(
        db.func.lower(
            CreatorAccount.username
        ) == normalized_username,

        CreatorAccount.account_status == "active",
    ).first()

    if account is None:
        abort(404)

    return account


# ============================================================
# PUBLIC CREATOR PROFILE LOOKUP
# ============================================================

def get_public_creator_profile(account):
    """
    Return the profile belonging to the selected creator.
    """

    if account is None:
        abort(404)

    creator = CreatorProfile.query.filter_by(
        creator_account_id=account.id,
    ).first()

    if creator is None:
        abort(404)

    return creator


# ============================================================
# PUBLIC CREATOR URL HELPERS
# ============================================================

def creator_home_url(account):
    """
    Build the creator's public homepage URL.

    Custom domain:

        /

    Platform domain:

        /@username
    """

    hosted = hosted_account()

    if (
        hosted is not None
        and hosted.id == account.id
    ):

        return url_for(
            "public.home",
        )

    return url_for(
        "public.creator_home",
        username=account.username,
    )


def creator_content_url(account, post):
    """
    Build a tenant-safe content URL.
    """

    hosted = hosted_account()

    if (
        hosted is not None
        and hosted.id == account.id
    ):

        return url_for(
            "public.content_detail",
            slug=post.slug,
        )

    return url_for(
        "public.creator_content_detail",
        username=account.username,
        slug=post.slug,
    )


# ============================================================
# PUBLIC BRANDING
# ============================================================

def public_branding_context(
    creator,
    account_id,
):
    """
    Return branding for the creator being viewed.

    Branding is always scoped to creator_account_id.

    Premium-only branding is available only when
    the creator has a verified, activated Premium plan.
    """

    account = (
        db.session.get(
            CreatorAccount,
            account_id,
        )
        if account_id is not None
        else None
    )

    branding = (
        CreatorBranding.query.filter_by(
            creator_account_id=account_id,
        ).first()
        if account is not None
        else None
    )

    # --------------------------------------------------------
    # VERIFIED PREMIUM STATUS
    # --------------------------------------------------------

    premium = bool(
        account is not None
        and (account.plan or "").lower() == "premium"
        and account.account_status == "active"
        and account.payment_status == "paid"
        and account.registration_paid_at is not None
    )

    # --------------------------------------------------------
    # SAFE COLOR VALIDATION
    # --------------------------------------------------------

    def color(field):

        value = (
            getattr(
                branding,
                field,
                None,
            )
            if branding is not None
            else None
        )

        if (
            isinstance(value, str)
            and re.fullmatch(
                r"#[0-9a-fA-F]{6}",
                value,
            )
        ):
            return value

        return BRANDING_DEFAULTS[field]

    # --------------------------------------------------------
    # THEME
    # --------------------------------------------------------

    theme = (
        getattr(
            branding,
            "theme",
            "light",
        )
        if premium and branding
        else "light"
    )

    if theme not in {
        "light",
        "dark",
    }:
        theme = "light"

    # --------------------------------------------------------
    # FONT
    # --------------------------------------------------------

    font = (
        getattr(
            branding,
            "font_family",
            "system",
        )
        if premium and branding
        else "system"
    )

    if font not in {
        "system",
        "sans",
        "serif",
        "mono",
    }:
        font = "system"

    # --------------------------------------------------------
    # TITLE AND TAGLINE
    # --------------------------------------------------------

    title = (
        getattr(
            branding,
            "site_title",
            None,
        )
        if branding
        else None
    ) or creator.display_name

    tagline = (
        getattr(
            branding,
            "site_tagline",
            None,
        )
        if branding
        else None
    ) or (
        creator.tagline or ""
    )

    # --------------------------------------------------------
    # CONTEXT
    # --------------------------------------------------------

    return {

        "creator_account": account,

        "branding": branding,

        "site_brand": {

            "title": title,

            "tagline": tagline,

            "logo_url": (
                getattr(
                    branding,
                    "logo_url",
                    None,
                )
                if branding
                else None
            ),

            "favicon_url": (
                getattr(
                    branding,
                    "favicon_url",
                    None,
                )
                if branding
                else None
            ),

            "cover_image_url": (
                getattr(
                    branding,
                    "cover_image_url",
                    None,
                )
                if branding
                else None
            ),

            "primary_color": color(
                "primary_color"
            ),

            "accent_color": color(
                "accent_color"
            ),

            "background_color": (
                color(
                    "background_color"
                )
                if premium
                else BRANDING_DEFAULTS[
                    "background_color"
                ]
            ),

            "text_color": (
                color(
                    "text_color"
                )
                if premium
                else BRANDING_DEFAULTS[
                    "text_color"
                ]
            ),

            "theme": theme,

            "font_family": font,

            "footer_text": (
                getattr(
                    branding,
                    "footer_text",
                    None,
                )
                if premium and branding
                else None
            ),

            "show_platform_branding": not premium,

        },

    }


# ============================================================
# ANONYMOUS SESSION
# ============================================================

def get_anonymous_session_id():
    """
    Return an anonymous session identifier.
    """

    anonymous_id = session.get(
        "anonymous_session_id"
    )

    if not anonymous_id:

        anonymous_id = secrets.token_urlsafe(
            24
        )

        session[
            "anonymous_session_id"
        ] = anonymous_id

    return anonymous_id


# ============================================================
# COMMENT RATE LIMITING
# ============================================================

def comment_rate_limited():
    """
    Apply a basic session-based comment cooldown.

    NOTE:

    This is not a replacement for server-side
    IP/account rate limiting.
    """

    current_time = time.time()

    previous_time = session.get(
        "last_comment_time"
    )

    if (
        previous_time
        and current_time - previous_time
        < COMMENT_COOLDOWN_SECONDS
    ):
        return True

    session[
        "last_comment_time"
    ] = current_time

    return False


# ============================================================
# RENDER CREATOR HOME
# ============================================================

def render_creator_home(
    creator,
    creator_account_id,
    public_username=None,
):
    """
    Render the public website belonging to one creator.
    """

    if (
        creator is None
        or creator_account_id is None
    ):
        abort(404)

    categories = ContentCategory.query.filter_by(
        creator_account_id=creator_account_id,
        is_active=True,
    ).order_by(
        ContentCategory.display_order.asc(),
        ContentCategory.name.asc(),
    ).all()

    posts = ContentPost.query.filter_by(
        creator_account_id=creator_account_id,
        status="published",
    ).order_by(
        ContentPost.published_at.desc(),
        ContentPost.created_at.desc(),
    ).limit(12).all()

    return render_template(
        "public/home.html",

        creator=creator,

        categories=categories,

        posts=posts,

        public_username=public_username,

        **public_branding_context(
            creator,
            creator_account_id,
        ),
    )


# ============================================================
# RENDER CONTENT DETAIL
# ============================================================

def render_content_detail(
    creator,
    post,
    public_username=None,
):
    """
    Render a published post belonging to the
    selected creator.
    """

    if creator is None or post is None:
        abort(404)

    if (
        creator.creator_account_id
        != post.creator_account_id
    ):
        abort(404)

    gallery_images = ContentMedia.query.filter_by(
        post_id=post.id,
        media_type="gallery_image",
    ).order_by(
        ContentMedia.media_order.asc(),
    ).all()

    video = ContentMedia.query.filter_by(
        post_id=post.id,
        media_type="video",
    ).first()

    comments = Comment.query.filter_by(
        post_id=post.id,
        parent_id=None,
        status="approved",
    ).order_by(
        Comment.created_at.desc(),
    ).all()

    comment_count = Comment.query.filter_by(
        post_id=post.id,
        status="approved",
    ).count()

    return render_template(
        "public/content_detail.html",

        creator=creator,

        post=post,

        gallery_images=gallery_images,

        video=video,

        comments=comments,

        comment_count=comment_count,

        public_username=public_username,

        **public_branding_context(
            creator,
            post.creator_account_id,
        ),
    )


# ============================================================
# PLATFORM HOMEPAGE / CUSTOM DOMAIN HOMEPAGE
# ============================================================

@public_bp.route("/")
def home():
    """
    Main entry point.

    PLATFORM DOMAIN
    ---------------

    Display the Kalxa Creator SaaS landing page.

    CUSTOM CREATOR DOMAIN
    ---------------------

    Display the website belonging to the
    custom-domain creator.

    Never select an arbitrary first creator.
    """

    account = hosted_account()

    # --------------------------------------------------------
    # CUSTOM CREATOR DOMAIN
    # --------------------------------------------------------

    if account is not None:

        if account.account_status != "active":
            abort(404)

        creator = get_public_creator_profile(
            account
        )

        return render_creator_home(
            creator=creator,
            creator_account_id=account.id,
            public_username=None,
        )

    # --------------------------------------------------------
    # KALXA PLATFORM HOMEPAGE
    # --------------------------------------------------------

    return render_template(
        "public/platform_home.html",

        platform_name="Kalxa Creator",

        plans={

            "free": {
                "name": "Free",
                "price": 0,
                "commission": 23,
                "billing": "forever",
            },

            "standard": {
                "name": "Standard",
                "price": 100,
                "commission": 3,
                "billing": "once-off",
            },

            "premium": {
                "name": "Premium",
                "price": 150,
                "commission": 3,
                "billing": "once-off",
            },

        },

    )


# ============================================================
# CREATOR PUBLIC HOMEPAGE
# ============================================================

@public_bp.route("/@<string:username>")
def creator_home(username):
    """
    Public creator website.

    Example:

        /@lasie
    """

    account = get_public_creator_account(
        username
    )

    creator = get_public_creator_profile(
        account
    )

    public_username = (
        None
        if hosted_account()
        else account.username
    )

    return render_creator_home(
        creator=creator,
        creator_account_id=account.id,
        public_username=public_username,
    )


# ============================================================
# CUSTOM DOMAIN CONTENT DETAIL
# ============================================================

@public_bp.route("/content/<string:slug>")
def content_detail(slug):
    """
    Root-style content URLs are available only
    when a custom creator domain is resolved.

    Example:

        customdomain.co.za/content/my-story

    On the Kalxa platform domain, use:

        /@username/content/my-story
    """

    account = hosted_account()

    if account is None:
        abort(404)

    if account.account_status != "active":
        abort(404)

    creator = get_public_creator_profile(
        account
    )

    post = ContentPost.query.filter_by(
        creator_account_id=account.id,
        slug=slug,
        status="published",
    ).first_or_404()

    return render_content_detail(
        creator=creator,
        post=post,
        public_username=None,
    )


# ============================================================
# CREATOR CONTENT DETAIL
# ============================================================

@public_bp.route(
    "/@<string:username>/content/<string:slug>"
)
def creator_content_detail(
    username,
    slug,
):
    """
    Platform creator content URL.
    """

    account = get_public_creator_account(
        username
    )

    creator = get_public_creator_profile(
        account
    )

    post = ContentPost.query.filter_by(
        creator_account_id=account.id,
        slug=slug,
        status="published",
    ).first_or_404()

    public_username = (
        None
        if hosted_account()
        else account.username
    )

    return render_content_detail(
        creator=creator,
        post=post,
        public_username=public_username,
    )


# ============================================================
# ROOT-STYLE COMMENTS
# ============================================================

@public_bp.route(
    "/content/<int:post_id>/comments",
    methods=["POST"],
)
def add_comment(post_id):
    """
    Submit a comment on a custom-domain creator post.
    """

    account = hosted_account()

    if account is None:
        abort(404)

    if account.account_status != "active":
        abort(404)

    post = ContentPost.query.filter_by(
        id=post_id,
        creator_account_id=account.id,
        status="published",
    ).first_or_404()

    return process_comment(
        post,
        "public.content_detail",
        {
            "slug": post.slug,
        },
    )


# ============================================================
# PLATFORM CREATOR COMMENTS
# ============================================================

@public_bp.route(
    "/@<string:username>/content/<int:post_id>/comments",
    methods=["POST"],
)
def creator_add_comment(
    username,
    post_id,
):
    """
    Submit a comment on a creator's platform URL.
    """

    account = get_public_creator_account(
        username
    )

    post = ContentPost.query.filter_by(
        id=post_id,
        creator_account_id=account.id,
        status="published",
    ).first_or_404()

    endpoint = (
        "public.content_detail"
        if hosted_account()
        else "public.creator_content_detail"
    )

    values = {
        "slug": post.slug,
    }

    if not hosted_account():
        values[
            "username"
        ] = account.username

    return process_comment(
        post,
        endpoint,
        values,
    )


# ============================================================
# PROCESS COMMENT
# ============================================================

def process_comment(
    post,
    redirect_endpoint,
    redirect_values,
):
    """
    Validate and save an anonymous comment.
    """

    def back():

        return redirect(
            url_for(
                redirect_endpoint,
                **redirect_values,
            ) + "#comments"
        )

    # --------------------------------------------------------
    # HONEYPOT
    # --------------------------------------------------------

    if request.form.get(
        "website",
        "",
    ).strip():

        return back()

    # --------------------------------------------------------
    # RATE LIMIT
    # --------------------------------------------------------

    if comment_rate_limited():

        flash(
            "Please wait a few seconds before posting another comment.",
            "warning",
        )

        return back()

    # --------------------------------------------------------
    # VALIDATE
    # --------------------------------------------------------

    author_name = request.form.get(
        "author_name",
        "",
    ).strip()

    body = request.form.get(
        "body",
        "",
    ).strip()

    if not author_name:

        flash(
            "Enter your name before commenting.",
            "error",
        )

        return back()

    if len(author_name) > AUTHOR_MAX_LENGTH:

        flash(
            "Your name is too long.",
            "error",
        )

        return back()

    if not body:

        flash(
            "Write something before posting.",
            "error",
        )

        return back()

    if len(body) > COMMENT_MAX_LENGTH:

        flash(
            "Your comment is too long.",
            "error",
        )

        return back()

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

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

    return back()


# ============================================================
# ROOT-STYLE COMMENT REPLIES
# ============================================================

@public_bp.route(
    "/comments/<int:comment_id>/reply",
    methods=["POST"],
)
def add_reply(comment_id):
    """
    Reply to a comment on a custom creator domain.
    """

    account = hosted_account()

    if account is None:
        abort(404)

    if account.account_status != "active":
        abort(404)

    parent = Comment.query.join(
        ContentPost,
        Comment.post_id == ContentPost.id,
    ).filter(
        Comment.id == comment_id,
        ContentPost.creator_account_id == account.id,
        ContentPost.status == "published",
    ).first_or_404()

    post = parent.post

    return process_reply(
        parent,
        post,
        "public.content_detail",
        {
            "slug": post.slug,
        },
    )


# ============================================================
# PLATFORM CREATOR REPLIES
# ============================================================

@public_bp.route(
    "/@<string:username>/comments/<int:comment_id>/reply",
    methods=["POST"],
)
def creator_add_reply(
    username,
    comment_id,
):
    """
    Reply to a comment on a platform creator URL.
    """

    account = get_public_creator_account(
        username
    )

    parent = Comment.query.join(
        ContentPost,
        Comment.post_id == ContentPost.id,
    ).filter(
        Comment.id == comment_id,
        ContentPost.creator_account_id == account.id,
        ContentPost.status == "published",
    ).first_or_404()

    post = parent.post

    endpoint = (
        "public.content_detail"
        if hosted_account()
        else "public.creator_content_detail"
    )

    values = {
        "slug": post.slug,
    }

    if not hosted_account():

        values[
            "username"
        ] = account.username

    return process_reply(
        parent,
        post,
        endpoint,
        values,
    )


# ============================================================
# PROCESS REPLY
# ============================================================

def process_reply(
    parent,
    post,
    redirect_endpoint,
    redirect_values,
):
    """
    Validate and save a reply to a top-level comment.
    """

    if parent.parent_id is not None:
        abort(400)

    if parent.status != "approved":
        abort(404)

    def back():

        return redirect(
            url_for(
                redirect_endpoint,
                **redirect_values,
            ) + f"#comment-{parent.id}"
        )

    # --------------------------------------------------------
    # HONEYPOT
    # --------------------------------------------------------

    if request.form.get(
        "website",
        "",
    ).strip():

        return back()

    # --------------------------------------------------------
    # RATE LIMIT
    # --------------------------------------------------------

    if comment_rate_limited():

        flash(
            "Please wait a few seconds before posting another reply.",
            "warning",
        )

        return back()

    # --------------------------------------------------------
    # VALIDATE
    # --------------------------------------------------------

    author_name = request.form.get(
        "author_name",
        "",
    ).strip()

    body = request.form.get(
        "body",
        "",
    ).strip()

    if not author_name:

        flash(
            "Enter your name before replying.",
            "error",
        )

        return back()

    if len(author_name) > AUTHOR_MAX_LENGTH:

        flash(
            "Your name is too long.",
            "error",
        )

        return back()

    if not body:

        flash(
            "Write something before replying.",
            "error",
        )

        return back()

    if len(body) > COMMENT_MAX_LENGTH:

        flash(
            "Your reply is too long.",
            "error",
        )

        return back()

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

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

    return back()


# ============================================================
# ROOT-STYLE NEWSLETTER SUBSCRIPTION
# ============================================================

@public_bp.route(
    "/newsletter/subscribe",
    methods=["POST"],
)
def newsletter_subscribe():
    """
    Newsletter subscription on a custom creator domain.
    """

    account = hosted_account()

    if account is None:
        abort(404)

    if account.account_status != "active":
        abort(404)

    return process_newsletter_subscription(
        creator_account_id=account.id,
        redirect_endpoint="public.home",
        redirect_values={},
    )


# ============================================================
# PLATFORM CREATOR NEWSLETTER SUBSCRIPTION
# ============================================================

@public_bp.route(
    "/@<string:username>/newsletter/subscribe",
    methods=["POST"],
)
def creator_newsletter_subscribe(username):
    """
    Subscribe to a creator using their platform URL.
    """

    account = get_public_creator_account(
        username
    )

    endpoint = (
        "public.home"
        if hosted_account()
        else "public.creator_home"
    )

    values = (
        {}
        if hosted_account()
        else {
            "username": account.username,
        }
    )

    return process_newsletter_subscription(
        creator_account_id=account.id,
        redirect_endpoint=endpoint,
        redirect_values=values,
    )


# ============================================================
# PROCESS NEWSLETTER SUBSCRIPTION
# ============================================================

def process_newsletter_subscription(
    creator_account_id,
    redirect_endpoint,
    redirect_values,
):
    """
    Store a pending subscriber and send
    a verification email.
    """

    def back():

        return redirect(
            url_for(
                redirect_endpoint,
                **redirect_values,
            ) + "#newsletter"
        )

    # --------------------------------------------------------
    # HONEYPOT
    # --------------------------------------------------------

    if request.form.get(
        "website",
        "",
    ).strip():

        return back()

    # --------------------------------------------------------
    # VALIDATE EMAIL
    # --------------------------------------------------------

    email = request.form.get(
        "email",
        "",
    ).strip().lower()

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

        return back()

    # --------------------------------------------------------
    # FIND EXISTING SUBSCRIBER
    # --------------------------------------------------------

    subscriber = EmailSubscriber.query.filter_by(
        creator_account_id=creator_account_id,
        email=email,
    ).first()

    if (
        subscriber is not None
        and subscriber.status == "active"
    ):

        flash(
            "You're already subscribed.",
            "success",
        )

        return back()

    # --------------------------------------------------------
    # GENERATE TOKENS
    # --------------------------------------------------------

    verification_token = secrets.token_urlsafe(
        48
    )

    unsubscribe_token = secrets.token_urlsafe(
        48
    )

    # --------------------------------------------------------
    # UPDATE EXISTING
    # --------------------------------------------------------

    if subscriber is not None:

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

    # --------------------------------------------------------
    # CREATE NEW
    # --------------------------------------------------------

    else:

        subscriber = EmailSubscriber(
            creator_account_id=creator_account_id,
            email=email,
            status="pending",
            verification_token=verification_token,
            unsubscribe_token=unsubscribe_token,
        )

        db.session.add(
            subscriber
        )

    db.session.commit()

    # --------------------------------------------------------
    # SEND VERIFICATION EMAIL
    # --------------------------------------------------------

    sent = send_verification_email(
        subscriber
    )

    if sent:

        flash(
            "Check your inbox and confirm your email to finish subscribing.",
            "success",
        )

    else:

        flash(
            "Your email was saved, but the verification email could not be sent. Please try again shortly.",
            "error",
        )

    return back()


# ============================================================
# NEWSLETTER VERIFY
# ============================================================

@public_bp.route(
    "/newsletter/verify/<string:token>"
)
def newsletter_verify(token):
    """
    Verify a creator newsletter subscription.
    """

    subscriber = EmailSubscriber.query.filter_by(
        verification_token=token,
    ).first()

    if subscriber is None:

        return render_template(
            "public/newsletter_message.html",

            title="Invalid link",

            heading="This link isn't valid.",

            message=(
                "The verification link may have expired "
                "or already been used."
            ),

        ), 404

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

    if account is None:
        abort(404)

    hosted = hosted_account()

    if (
        hosted is not None
        and hosted.id != account.id
    ):
        abort(404)

    # --------------------------------------------------------
    # ACTIVATE
    # --------------------------------------------------------

    subscriber.status = "active"

    subscriber.verified_at = utc_now()

    subscriber.unsubscribed_at = None

    subscriber.verification_token = None

    db.session.commit()

    send_welcome_email(
        subscriber
    )

    creator = get_public_creator_profile(
        account
    )

    return render_template(
        "public/newsletter_message.html",

        title="Subscription confirmed",

        heading="You're in.",

        message=(
            "Your email is confirmed. "
            "You'll now receive updates when "
            "new content is published."
        ),

        creator_username=account.username,

        **public_branding_context(
            creator,
            account.id,
        ),
    )


# ============================================================
# NEWSLETTER UNSUBSCRIBE
# ============================================================

@public_bp.route(
    "/newsletter/unsubscribe/<string:token>"
)
def newsletter_unsubscribe(token):
    """
    Unsubscribe from one creator's newsletter.
    """

    subscriber = EmailSubscriber.query.filter_by(
        unsubscribe_token=token,
    ).first()

    if subscriber is None:

        return render_template(
            "public/newsletter_message.html",

            title="Invalid link",

            heading="This link isn't valid.",

            message=(
                "We couldn't find a subscription "
                "for this unsubscribe link."
            ),

        ), 404

    hosted = hosted_account()

    if (
        hosted is not None
        and hosted.id
        != subscriber.creator_account_id
    ):
        abort(404)

    # --------------------------------------------------------
    # UNSUBSCRIBE
    # --------------------------------------------------------

    subscriber.status = "unsubscribed"

    subscriber.unsubscribed_at = utc_now()

    subscriber.verification_token = None

    db.session.commit()

    account = (
        db.session.get(
            CreatorAccount,
            subscriber.creator_account_id,
        )
        if subscriber.creator_account_id
        else None
    )

    branding_context = {}

    if account is not None:

        creator = get_public_creator_profile(
            account
        )

        branding_context = public_branding_context(
            creator,
            account.id,
        )

    return render_template(
        "public/newsletter_message.html",

        title="Unsubscribed",

        heading="You've been unsubscribed.",

        message=(
            "You won't receive new-post emails "
            "from this creator anymore. "
            "You can subscribe again from their "
            "website at any time."
        ),

        creator_username=(
            account.username
            if account
            else None
        ),

        **branding_context,
    )
