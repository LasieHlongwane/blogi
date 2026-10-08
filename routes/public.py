"""Public creator websites, posts, comments and newsletters (tenant-safe)."""
import secrets
import time
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort, g
from extensions import db
from models import CreatorAccount, CreatorProfile, ContentCategory, ContentPost, ContentMedia, Comment, EmailSubscriber, utc_now
from services.email_service import send_verification_email, send_welcome_email

public_bp = Blueprint("public", __name__)
COMMENT_MAX_LENGTH = 1500
AUTHOR_MAX_LENGTH = 80
COMMENT_COOLDOWN_SECONDS = 8


def hosted_account():
    return getattr(g, "creator_domain_account", None)


def get_current_creator():
    """Use the hosted tenant if present, otherwise retain legacy root behavior."""
    account = hosted_account()
    if account:
        return CreatorProfile.query.filter_by(creator_account_id=account.id).first()
    return CreatorProfile.query.order_by(CreatorProfile.id.asc()).first()


def get_current_creator_account_id():
    creator = get_current_creator()
    return creator.creator_account_id if creator else None


def get_public_creator_account(username):
    normalized_username = (username or "").strip().lower()
    hosted = hosted_account()
    if hosted and hosted.username.lower() != normalized_username:
        abort(404)
    account = CreatorAccount.query.filter(
        db.func.lower(CreatorAccount.username) == normalized_username,
        CreatorAccount.account_status == "active",
    ).first()
    if not account:
        abort(404)
    return account


def get_public_creator_profile(account):
    creator = CreatorProfile.query.filter_by(creator_account_id=account.id).first()
    if not creator:
        abort(404)
    return creator


def creator_home_url(account):
    if hosted_account() and hosted_account().id == account.id:
        return url_for("public.home")
    return url_for("public.creator_home", username=account.username)


def creator_content_url(account, post):
    if hosted_account() and hosted_account().id == account.id:
        return url_for("public.content_detail", slug=post.slug)
    return url_for("public.creator_content_detail", username=account.username, slug=post.slug)


def get_anonymous_session_id():
    anonymous_id = session.get("anonymous_session_id")
    if not anonymous_id:
        anonymous_id = secrets.token_urlsafe(24)
        session["anonymous_session_id"] = anonymous_id
    return anonymous_id


def comment_rate_limited():
    current_time = time.time()
    previous_time = session.get("last_comment_time")
    if previous_time and current_time - previous_time < COMMENT_COOLDOWN_SECONDS:
        return True
    session["last_comment_time"] = current_time
    return False


def render_creator_home(creator, creator_account_id, public_username=None):
    categories = ContentCategory.query.filter_by(
        creator_account_id=creator_account_id, is_active=True
    ).order_by(ContentCategory.display_order.asc(), ContentCategory.name.asc()).all()
    posts = ContentPost.query.filter_by(
        creator_account_id=creator_account_id, status="published"
    ).order_by(ContentPost.published_at.desc(), ContentPost.created_at.desc()).limit(12).all()
    return render_template("public/home.html", creator=creator, categories=categories,
                           posts=posts, public_username=public_username)


def render_content_detail(creator, post, public_username=None):
    gallery_images = ContentMedia.query.filter_by(
        post_id=post.id, media_type="gallery_image"
    ).order_by(ContentMedia.media_order.asc()).all()
    video = ContentMedia.query.filter_by(post_id=post.id, media_type="video").first()
    comments = Comment.query.filter_by(
        post_id=post.id, parent_id=None, status="approved"
    ).order_by(Comment.created_at.desc()).all()
    comment_count = Comment.query.filter_by(post_id=post.id, status="approved").count()
    return render_template("public/content_detail.html", creator=creator, post=post,
                           gallery_images=gallery_images, video=video, comments=comments,
                           comment_count=comment_count, public_username=public_username)


@public_bp.route("/")
def home():
    creator = get_current_creator()
    if not creator:
        abort(404)
    creator_account_id = creator.creator_account_id
    if creator_account_id is None:
        # Original unassigned content is visible only on the platform host.
        if hosted_account():
            abort(404)
        categories = ContentCategory.query.filter_by(creator_account_id=None, is_active=True).order_by(
            ContentCategory.display_order.asc(), ContentCategory.name.asc()).all()
        posts = ContentPost.query.filter_by(creator_account_id=None, status="published").order_by(
            ContentPost.published_at.desc(), ContentPost.created_at.desc()).limit(12).all()
        return render_template("public/home.html", creator=creator, categories=categories,
                               posts=posts, public_username=None)
    return render_creator_home(creator, creator_account_id, public_username=None)


@public_bp.route("/@<string:username>")
def creator_home(username):
    account = get_public_creator_account(username)
    creator = get_public_creator_profile(account)
    # Hosted pages use root-style URLs; platform pages use /@username URLs.
    public_username = None if hosted_account() else account.username
    return render_creator_home(creator, account.id, public_username=public_username)


@public_bp.route("/content/<string:slug>")
def content_detail(slug):
    creator = get_current_creator()
    if not creator:
        abort(404)
    query = ContentPost.query.filter_by(slug=slug, status="published")
    if creator.creator_account_id is not None:
        query = query.filter_by(creator_account_id=creator.creator_account_id)
    elif hosted_account():
        abort(404)
    else:
        query = query.filter_by(creator_account_id=None)
    post = query.first_or_404()
    return render_content_detail(creator, post, public_username=None)


@public_bp.route("/@<string:username>/content/<string:slug>")
def creator_content_detail(username, slug):
    account = get_public_creator_account(username)
    creator = get_public_creator_profile(account)
    post = ContentPost.query.filter_by(
        creator_account_id=account.id, slug=slug, status="published"
    ).first_or_404()
    return render_content_detail(creator, post,
                                 public_username=None if hosted_account() else account.username)


@public_bp.route("/content/<int:post_id>/comments", methods=["POST"])
def add_comment(post_id):
    creator = get_current_creator()
    if not creator:
        abort(404)
    post = ContentPost.query.filter_by(id=post_id, status="published").first_or_404()
    if creator.creator_account_id is not None and post.creator_account_id != creator.creator_account_id:
        abort(404)
    if hosted_account() and post.creator_account_id != hosted_account().id:
        abort(404)
    if creator.creator_account_id is None and post.creator_account_id is not None:
        abort(404)
    return process_comment(post, "public.content_detail", {"slug": post.slug})


@public_bp.route("/@<string:username>/content/<int:post_id>/comments", methods=["POST"])
def creator_add_comment(username, post_id):
    account = get_public_creator_account(username)
    post = ContentPost.query.filter_by(
        id=post_id, creator_account_id=account.id, status="published"
    ).first_or_404()
    endpoint = "public.content_detail" if hosted_account() else "public.creator_content_detail"
    values = {"slug": post.slug}
    if not hosted_account():
        values["username"] = account.username
    return process_comment(post, endpoint, values)


def process_comment(post, redirect_endpoint, redirect_values):
    def back():
        return redirect(url_for(redirect_endpoint, **redirect_values) + "#comments")
    if request.form.get("website", "").strip():
        return back()
    if comment_rate_limited():
        flash("Please wait a few seconds before posting another comment.", "warning")
        return back()
    author_name = request.form.get("author_name", "").strip()
    body = request.form.get("body", "").strip()
    if not author_name:
        flash("Enter your name before commenting.", "error")
        return back()
    if len(author_name) > AUTHOR_MAX_LENGTH:
        flash("Your name is too long.", "error")
        return back()
    if not body:
        flash("Write something before posting.", "error")
        return back()
    if len(body) > COMMENT_MAX_LENGTH:
        flash("Your comment is too long.", "error")
        return back()
    db.session.add(Comment(post_id=post.id, author_name=author_name, body=body,
                           status="approved", is_creator=False,
                           anonymous_session_id=get_anonymous_session_id()))
    db.session.commit()
    flash("Your comment was posted.", "success")
    return back()


@public_bp.route("/comments/<int:comment_id>/reply", methods=["POST"])
def add_reply(comment_id):
    creator = get_current_creator()
    if not creator:
        abort(404)
    parent = db.session.get(Comment, comment_id)
    if not parent or not parent.post or parent.post.status != "published":
        abort(404)
    post = parent.post
    if creator.creator_account_id is not None and post.creator_account_id != creator.creator_account_id:
        abort(404)
    if hosted_account() and post.creator_account_id != hosted_account().id:
        abort(404)
    if creator.creator_account_id is None and post.creator_account_id is not None:
        abort(404)
    return process_reply(parent, post, "public.content_detail", {"slug": post.slug})


@public_bp.route("/@<string:username>/comments/<int:comment_id>/reply", methods=["POST"])
def creator_add_reply(username, comment_id):
    account = get_public_creator_account(username)
    parent = Comment.query.join(ContentPost, Comment.post_id == ContentPost.id).filter(
        Comment.id == comment_id, ContentPost.creator_account_id == account.id,
        ContentPost.status == "published"
    ).first_or_404()
    post = parent.post
    endpoint = "public.content_detail" if hosted_account() else "public.creator_content_detail"
    values = {"slug": post.slug}
    if not hosted_account():
        values["username"] = account.username
    return process_reply(parent, post, endpoint, values)


def process_reply(parent, post, redirect_endpoint, redirect_values):
    if parent.parent_id is not None:
        abort(400)

    def back():
        return redirect(url_for(redirect_endpoint, **redirect_values) + f"#comment-{parent.id}")

    if request.form.get("website", "").strip():
        return back()
    if comment_rate_limited():
        flash("Please wait a few seconds before posting another reply.", "warning")
        return back()
    author_name = request.form.get("author_name", "").strip()
    body = request.form.get("body", "").strip()
    if not author_name:
        flash("Enter your name before replying.", "error")
        return back()
    if len(author_name) > AUTHOR_MAX_LENGTH:
        flash("Your name is too long.", "error")
        return back()
    if not body:
        flash("Write something before replying.", "error")
        return back()
    if len(body) > COMMENT_MAX_LENGTH:
        flash("Your reply is too long.", "error")
        return back()
    db.session.add(Comment(post_id=post.id, parent_id=parent.id, author_name=author_name,
                           body=body, status="approved", is_creator=False,
                           anonymous_session_id=get_anonymous_session_id()))
    db.session.commit()
    flash("Your reply was posted.", "success")
    return back()


@public_bp.route("/newsletter/subscribe", methods=["POST"])
def newsletter_subscribe():
    creator = get_current_creator()
    if not creator:
        abort(404)
    if creator.creator_account_id is None:
        abort(503, description="Creator ownership has not been configured yet.")
    return process_newsletter_subscription(creator.creator_account_id, "public.home", {})


@public_bp.route("/@<string:username>/newsletter/subscribe", methods=["POST"])
def creator_newsletter_subscribe(username):
    account = get_public_creator_account(username)
    endpoint = "public.home" if hosted_account() else "public.creator_home"
    values = {} if hosted_account() else {"username": account.username}
    return process_newsletter_subscription(account.id, endpoint, values)


def process_newsletter_subscription(creator_account_id, redirect_endpoint, redirect_values):
    def back():
        return redirect(url_for(redirect_endpoint, **redirect_values) + "#newsletter")

    email = request.form.get("email", "").strip().lower()
    if request.form.get("website", "").strip():
        return back()
    if not email or "@" not in email or "." not in email.split("@")[-1] or len(email) > 255:
        flash("Enter a valid email address.", "error")
        return back()
    subscriber = EmailSubscriber.query.filter_by(
        creator_account_id=creator_account_id, email=email
    ).first()
    if subscriber and subscriber.status == "active":
        flash("You're already subscribed.", "success")
        return back()
    verification_token = secrets.token_urlsafe(48)
    unsubscribe_token = secrets.token_urlsafe(48)
    if subscriber:
        subscriber.status = "pending"
        subscriber.verification_token = verification_token
        if not subscriber.unsubscribe_token:
            subscriber.unsubscribe_token = unsubscribe_token
        subscriber.verified_at = None
        subscriber.unsubscribed_at = None
    else:
        subscriber = EmailSubscriber(
            creator_account_id=creator_account_id, email=email, status="pending",
            verification_token=verification_token, unsubscribe_token=unsubscribe_token,
        )
        db.session.add(subscriber)
    db.session.commit()
    sent = send_verification_email(subscriber)
    if sent:
        flash("Check your inbox and confirm your email to finish subscribing.", "success")
    else:
        flash("Your email was saved, but the verification email could not be sent. Please try again shortly.", "error")
    return back()


@public_bp.route("/newsletter/verify/<string:token>")
def newsletter_verify(token):
    subscriber = EmailSubscriber.query.filter_by(verification_token=token).first()
    if not subscriber:
        return render_template("public/newsletter_message.html", title="Invalid link",
                               heading="This link isn't valid.", message="The verification link may have expired or already been used."), 404
    if subscriber.creator_account_id is None:
        return render_template("public/newsletter_message.html", title="Subscription unavailable",
                               heading="We couldn't confirm this subscription.",
                               message="This subscription is not connected to a creator account."), 400
    account = db.session.get(CreatorAccount, subscriber.creator_account_id)
    if not account:
        abort(404)
    if hosted_account() and hosted_account().id != account.id:
        abort(404)
    subscriber.status = "active"
    subscriber.verified_at = utc_now()
    subscriber.unsubscribed_at = None
    subscriber.verification_token = None
    db.session.commit()
    send_welcome_email(subscriber)
    return render_template("public/newsletter_message.html", title="Subscription confirmed",
                           heading="You're in.", message="Your email is confirmed. You'll now receive updates when new content is published.",
                           creator_username=account.username)


@public_bp.route("/newsletter/unsubscribe/<string:token>")
def newsletter_unsubscribe(token):
    subscriber = EmailSubscriber.query.filter_by(unsubscribe_token=token).first()
    if not subscriber:
        return render_template("public/newsletter_message.html", title="Invalid link",
                               heading="This link isn't valid.",
                               message="We couldn't find a subscription for this unsubscribe link."), 404
    if hosted_account() and hosted_account().id != subscriber.creator_account_id:
        abort(404)
    subscriber.status = "unsubscribed"
    subscriber.unsubscribed_at = utc_now()
    subscriber.verification_token = None
    db.session.commit()
    account = db.session.get(CreatorAccount, subscriber.creator_account_id) if subscriber.creator_account_id else None
    return render_template("public/newsletter_message.html", title="Unsubscribed",
                           heading="You've been unsubscribed.",
                           message="You won't receive new-post emails from this creator anymore. You can subscribe again from their website at any time.",
                           creator_username=account.username if account else None)
