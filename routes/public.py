# ============================================================
# CREATOR BLOG
# PUBLIC ROUTES
# ============================================================

import secrets
import time
import secrets
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
# ANONYMOUS SESSION
# ============================================================

def get_anonymous_session_id():

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
# COMMENT COOLDOWN
# ============================================================

def comment_rate_limited():

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
# HOME
# ============================================================

@public_bp.route("/")
def home():

    creator = (
        CreatorProfile.query
        .first()
    )

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
    )


# ============================================================
# CONTENT DETAIL
# ============================================================

@public_bp.route(
    "/content/<string:slug>"
)
def content_detail(
    slug
):

    post = (
        ContentPost.query
        .filter_by(
            slug=slug,
            status="published",
        )
        .first_or_404()
    )

    creator = (
        CreatorProfile.query
        .first()
    )

    # ========================================================
    # MEDIA
    # ========================================================

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

    # ========================================================
    # COMMENTS
    # ========================================================

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
    )


# ============================================================
# ADD COMMENT
# ============================================================

@public_bp.route(
    "/content/<int:post_id>/comments",
    methods=["POST"],
)
def add_comment(
    post_id
):

    post = db.get_or_404(
        ContentPost,
        post_id,
    )

    # Only published content accepts public comments.
    if post.status != "published":

        abort(404)

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

        # Pretend submission succeeded.
        # Bots filling hidden fields don't
        # need to know they were rejected.

        return redirect(
            url_for(
                "public.content_detail",
                slug=post.slug,
            )
            + "#comments"
        )

    # ========================================================
    # RATE LIMIT
    # ========================================================

    if comment_rate_limited():

        flash(
            "Please wait a few seconds before "
            "posting another comment.",
            "warning",
        )

        return redirect(
            url_for(
                "public.content_detail",
                slug=post.slug,
            )
            + "#comments"
        )

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

        return redirect(
            url_for(
                "public.content_detail",
                slug=post.slug,
            )
            + "#comments"
        )

    if (
        len(author_name)
        > AUTHOR_MAX_LENGTH
    ):

        flash(
            "Your name is too long.",
            "error",
        )

        return redirect(
            url_for(
                "public.content_detail",
                slug=post.slug,
            )
            + "#comments"
        )

    if not body:

        flash(
            "Write something before posting.",
            "error",
        )

        return redirect(
            url_for(
                "public.content_detail",
                slug=post.slug,
            )
            + "#comments"
        )

    if (
        len(body)
        > COMMENT_MAX_LENGTH
    ):

        flash(
            "Your comment is too long.",
            "error",
        )

        return redirect(
            url_for(
                "public.content_detail",
                slug=post.slug,
            )
            + "#comments"
        )

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

    return redirect(
        url_for(
            "public.content_detail",
            slug=post.slug,
        )
        + "#comments"
    )


# ============================================================
# ADD REPLY
# ============================================================

@public_bp.route(
    "/comments/<int:comment_id>/reply",
    methods=["POST"],
)
def add_reply(
    comment_id
):

    parent = db.get_or_404(
        Comment,
        comment_id,
    )

    post = parent.post

    if post.status != "published":

        abort(404)

    # ========================================================
    # ONLY ONE LEVEL OF REPLIES
    # ========================================================

    if parent.parent_id is not None:

        abort(400)

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

        return redirect(
            url_for(
                "public.content_detail",
                slug=post.slug,
            )
            + f"#comment-{parent.id}"
        )

    # ========================================================
    # RATE LIMIT
    # ========================================================

    if comment_rate_limited():

        flash(
            "Please wait a few seconds before "
            "posting another reply.",
            "warning",
        )

        return redirect(
            url_for(
                "public.content_detail",
                slug=post.slug,
            )
            + f"#comment-{parent.id}"
        )

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

        return redirect(
            url_for(
                "public.content_detail",
                slug=post.slug,
            )
            + f"#comment-{parent.id}"
        )

    if (
        len(author_name)
        > AUTHOR_MAX_LENGTH
    ):

        flash(
            "Your name is too long.",
            "error",
        )

        return redirect(
            url_for(
                "public.content_detail",
                slug=post.slug,
            )
            + f"#comment-{parent.id}"
        )

    if not body:

        flash(
            "Write something before replying.",
            "error",
        )

        return redirect(
            url_for(
                "public.content_detail",
                slug=post.slug,
            )
            + f"#comment-{parent.id}"
        )

    if (
        len(body)
        > COMMENT_MAX_LENGTH
    ):

        flash(
            "Your reply is too long.",
            "error",
        )

        return redirect(
            url_for(
                "public.content_detail",
                slug=post.slug,
            )
            + f"#comment-{parent.id}"
        )

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

    return redirect(
        url_for(
            "public.content_detail",
            slug=post.slug,
        )
        + f"#comment-{parent.id}"
    )
    
    
    
# ============================================================
# NEWSLETTER SUBSCRIBE
# ============================================================

@public_bp.route(
    "/newsletter/subscribe",
    methods=["POST"],
)
def newsletter_subscribe():

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

        return redirect(
            url_for(
                "public.home"
            )
            + "#newsletter"
        )

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

        return redirect(
            url_for(
                "public.home"
            )
            + "#newsletter"
        )

    subscriber = (
        EmailSubscriber.query
        .filter_by(
            email=email
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

        return redirect(
            url_for(
                "public.home"
            )
            + "#newsletter"
        )

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

        # Keep an existing unsubscribe token
        # if one already exists.

        if not subscriber.unsubscribe_token:

            subscriber.unsubscribe_token = (
                unsubscribe_token
            )

        subscriber.verified_at = None
        subscriber.unsubscribed_at = None

    else:

        subscriber = EmailSubscriber(
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
    # SEND VERIFICATION
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

    return redirect(
        url_for(
            "public.home"
        )
        + "#newsletter"
    )


# ============================================================
# VERIFY NEWSLETTER EMAIL
# ============================================================

@public_bp.route(
    "/newsletter/verify/<string:token>"
)
def newsletter_verify(
    token
):

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

    # ========================================================
    # ACTIVATE
    # ========================================================

    subscriber.status = "active"

    subscriber.verified_at = (
        utc_now()
    )

    subscriber.unsubscribed_at = None

    # One-time verification token.
    subscriber.verification_token = None

    db.session.commit()

    # Welcome failure should NOT undo verification.
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
    )


# ============================================================
# UNSUBSCRIBE
# ============================================================

@public_bp.route(
    "/newsletter/unsubscribe/<string:token>"
)
def newsletter_unsubscribe(
    token
):

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

    subscriber.verification_token = (
        None
    )

    db.session.commit()

    return render_template(
        "public/newsletter_message.html",
        title="Unsubscribed",
        heading="You've been unsubscribed.",
        message=(
            "You won't receive new-post "
            "emails anymore. You can subscribe "
            "again from the website at any time."
        ),
    )