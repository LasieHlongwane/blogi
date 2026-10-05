# ============================================================
# CREATOR PLATFORM
# CREATOR STUDIO
# ============================================================

import re

from datetime import datetime, timezone
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
    current_app,
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
    EmailDelivery,
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

        # ----------------------------------------------------
        # ACCOUNT MUST BE ACTIVE
        # ----------------------------------------------------

        if (
            creator.account_status
            != "active"
        ):

            return redirect(
                url_for(
                    "creator_auth.pending"
                )
            )

        # ----------------------------------------------------
        # PLATFORM SUBSCRIPTION MUST BE ACTIVE
        # ----------------------------------------------------

        if (
            creator.subscription_status
            != "active"
        ):

            return redirect(
                url_for(
                    "creator_auth.pending"
                )
            )

        return view(
            *args,
            **kwargs,
        )

    return wrapped_view

def require_creator_feature(
    creator,
    feature,
):
    """
    Server-side creator plan feature gate.

    Returns True when access is allowed.

    Routes must never rely only on hidden template buttons.
    """

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

def slugify(value):

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

# ============================================================
# UNIQUE POST SLUG
# ============================================================

def unique_post_slug(
    creator,
    title,
    post_id=None,
):

    base_slug = (
        slugify(title)
        or "post"
    )

    candidate = base_slug
    counter = 2

    while True:

        # ====================================================
        # TENANT-SCOPED LOOKUP
        # ====================================================
        #
        # Only check posts belonging to THIS creator.
        #
        # Another creator is allowed to use the exact same
        # slug.
        # ====================================================

        query = (
            ContentPost.query
            .filter_by(
                creator_account_id=(
                    creator.id
                ),
                slug=candidate,
            )
        )

        if post_id is not None:

            query = query.filter(
                ContentPost.id
                != post_id
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

# ============================================================
# UNIQUE CATEGORY SLUG
# ============================================================

def unique_category_slug(
    creator,
    name,
):

    base_slug = (
        slugify(name)
        or "folder"
    )

    candidate = base_slug
    counter = 2

    while True:

        # ====================================================
        # TENANT-SCOPED LOOKUP
        # ====================================================

        existing = (
            ContentCategory.query
            .filter_by(
                creator_account_id=(
                    creator.id
                ),
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
# CLOUDINARY FOLDER
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


# ============================================================
# COVER IMAGE
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

    valid, error = (
        validate_image(file)
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

        existing.resource_type = "image"

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
                "Old creator cover deletion failed."
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

    valid, error = (
        validate_video(file)
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

        existing.resource_type = "video"

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
                "Old creator video deletion failed."
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
        if file and file.filename
    ]

    if not files:

        return True, None

    if len(files) > 10:

        return (
            False,
            "You can upload up to 10 gallery "
            "images at a time.",
        )

    for file in files:

        valid, error = (
            validate_image(file)
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
                    media_type=(
                        "gallery_image"
                    ),
                    media_url=(
                        result["url"]
                    ),
                    public_id=(
                        result["public_id"]
                    ),
                    resource_type="image",
                    width=result.get(
                        "width"
                    ),
                    height=result.get(
                        "height"
                    ),
                    media_order=(
                        next_order
                    ),
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
# DASHBOARD
# ============================================================

@studio_bp.route("/")
@studio_required
def dashboard():

    account = (
        current_creator_account()
    )

    creator = (
        creator_profile(account)
    )

    base_posts = (
        ContentPost.query
        .filter_by(
            creator_account_id=account.id
        )
    )

    total_posts = (
        base_posts.count()
    )

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

    plan_summary = creator_plan_summary(
        account
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
        plan_summary=plan_summary,
        recent_posts=recent_posts,
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
        .get(
            "status",
            "",
        )
        .strip()
    )

    content_type = (
        request.args
        .get(
            "type",
            "",
        )
        .strip()
    )

    query = (
        ContentPost.query
        .filter_by(
            creator_account_id=(
                account.id
            )
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
            .get(
                "title",
                "",
            )
            .strip()
        )

        excerpt = (
            request.form
            .get(
                "excerpt",
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

           # ====================================================
        # PREMIUM: EXCLUSIVE CONTENT
        # ====================================================

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

            abort(400)

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
            creator_account_id=(
                account.id
            ),
            title=title,
            slug=unique_post_slug(
                account,
                title,
            ),
            excerpt=(
                excerpt or None
            ),
            body=(
                body or None
            ),
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
            post.status
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
                    "Creator subscriber "
                    "notification failed."
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
            .get(
                "title",
                "",
            )
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

        
        # ====================================================
        # PREMIUM: EXCLUSIVE CONTENT
        # ====================================================

        if (
            access_level == "subscriber"
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
            abort(400)

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

        post.title = title

        post.slug = (
            unique_post_slug(
                account,
                title,
                post.id,
            )
        )

        post.excerpt = (
            request.form
            .get(
                "excerpt",
                "",
            )
            .strip()
            or None
        )

        post.body = (
            request.form
            .get(
                "body",
                "",
            )
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

        # Notify only when transitioning into published.
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
                    "Creator subscriber "
                    "notification failed."
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
# PUBLISH
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
                "Creator newsletter "
                "notification failed."
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
# ARCHIVE
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
# DELETE
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
                resource_type=(
                    resource_type
                ),
            )

        except Exception:

            current_app.logger.exception(
                "Creator media deletion failed."
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
                    "Cover image could not be removed.",
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
                "Video could not be removed.",
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
                "Gallery image could not be removed.",
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
            .get(
                "name",
                "",
            )
            .strip()
        )

        description = (
            request.form
            .get(
                "description",
                "",
            )
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
                creator_account_id=(
                    account.id
                )
            )
            .count()
        )

        category = ContentCategory(
            creator_account_id=(
                account.id
            ),
            name=name,
            slug=unique_category_slug(
                account,
                name,
            ),
            description=(
                description or None
            ),
            is_active=True,
            display_order=(
                count + 1
            ),
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
            creator_account_id=(
                account.id
            )
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

    creator = (
        creator_profile(account)
    )

    if not creator:

        abort(404)

    if request.method == "POST":

        display_name = (
            request.form
            .get(
                "display_name",
                "",
            )
            .strip()
        )

        tagline = (
            request.form
            .get(
                "tagline",
                "",
            )
            .strip()
        )

        bio = (
            request.form
            .get(
                "bio",
                "",
            )
            .strip()
        )

        if not display_name:

            flash(
                "Display name is required.",
                "error",
            )

            return render_template(
                "studio/profile.html",
                creator=creator,
            )

        # ----------------------------------------------------
        # USERNAME
        # ----------------------------------------------------
        #
        # CreatorAccount is canonical.
        #
        # Do not independently change profile.username here.
        # ----------------------------------------------------

        creator.username = (
            account.username
        )

        creator.display_name = (
            display_name
        )

        creator.tagline = (
            tagline or None
        )

        creator.bio = (
            bio or None
        )

        creator.instagram_url = (
            request.form
            .get(
                "instagram_url",
                "",
            )
            .strip()
            or None
        )

        creator.tiktok_url = (
            request.form
            .get(
                "tiktok_url",
                "",
            )
            .strip()
            or None
        )

        creator.youtube_url = (
            request.form
            .get(
                "youtube_url",
                "",
            )
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

            result = upload_image(
                profile_image,
                folder=(
                    current_app.config[
                        "CLOUDINARY_FOLDER"
                    ]
                    + f"/creators/{account.id}/profile"
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
                        "Old profile image "
                        "deletion failed."
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

            result = upload_video(
                intro_reel,
                folder=(
                    current_app.config[
                        "CLOUDINARY_FOLDER"
                    ]
                    + f"/creators/{account.id}/intro-reels"
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
                        "Old intro reel deletion failed."
                    )

        db.session.commit()

        flash(
            "Profile updated successfully.",
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
        .get(
            "status",
            "",
        )
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
# COMMENT STATUS
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
        .get(
            "body",
            "",
        )
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

    profile = (
        creator_profile(account)
    )

    reply = Comment(
        post_id=parent.post_id,
        parent_id=parent.id,
        author_name=(
            profile.display_name
            if profile
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
        .get(
            "status",
            "",
        )
        .strip()
    )

    query = (
        EmailSubscriber.query
        .filter_by(
            creator_account_id=(
                account.id
            )
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

    creator = (
        creator_profile(account)
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
                "Creator profile image "
                "deletion failed."
            )

            flash(
                "Profile image could not "
                "be removed.",
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

    creator = (
        creator_profile(account)
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
                "Creator intro reel "
                "deletion failed."
            )

            flash(
                "Intro reel could not "
                "be removed.",
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
