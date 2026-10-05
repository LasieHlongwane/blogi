# ============================================================
# CREATOR BLOG
# ADMIN / CREATOR STUDIO ROUTES
# ============================================================

import re

from datetime import datetime, timezone
from functools import wraps
from services.email_service import (
    notify_subscribers_about_post,
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
)
from services.cloudinary_service import (
    upload_image,
    upload_video,
    delete_media,
    validate_image,
    validate_video,
)

from extensions import db


from models import (
    AdminUser,
    CreatorProfile,
    ContentCategory,
    ContentPost,
    ContentMedia,
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
# HELPERS
# ============================================================

def utc_now():
    """
    Return the current UTC datetime.
    """

    return datetime.now(
        timezone.utc
    )


# ============================================================
# SLUGIFY
# ============================================================

def slugify(value):
    """
    Convert a title/name into a URL-safe slug.

    Example:

        My First Story
            ↓
        my-first-story
    """

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
# ADMIN AUTHENTICATION DECORATOR
# ============================================================

def admin_required(view):
    """
    Protect Creator Studio routes.

    The logged-in admin ID is stored inside the Flask session.
    """

    @wraps(view)
    def wrapped_view(
        *args,
        **kwargs,
    ):

        admin_id = session.get(
            "admin_user_id"
        )

        # ----------------------------------------------------
        # NOT LOGGED IN
        # ----------------------------------------------------

        if not admin_id:

            flash(
                "Please sign in to continue.",
                "warning",
            )

            return redirect(
                url_for(
                    "admin.login"
                )
            )

        # ----------------------------------------------------
        # LOAD ADMIN
        # ----------------------------------------------------

        admin = db.session.get(
            AdminUser,
            admin_id,
        )

        # ----------------------------------------------------
        # INVALID / DISABLED ADMIN
        # ----------------------------------------------------

        if (
            not admin
            or not admin.is_active
        ):

            session.clear()

            flash(
                "Your admin session is no longer valid.",
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
# UNIQUE POST SLUG
# ============================================================

def unique_post_slug(
    title,
    post_id=None,
):
    """
    Generate a unique slug for ContentPost.

    Example:

        my-story

    If it already exists:

        my-story-2
        my-story-3
        ...
    """

    base_slug = slugify(
        title
    )

    if not base_slug:

        base_slug = "post"

    candidate = base_slug

    counter = 2

    while True:

        query = (
            ContentPost.query
            .filter_by(
                slug=candidate
            )
        )

        # Ignore the current post while editing.
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

def unique_category_slug(
    name,
    category_id=None,
):
    """
    Generate a unique slug for ContentCategory.
    """

    base_slug = slugify(
        name
    )

    if not base_slug:

        base_slug = "folder"

    candidate = base_slug

    counter = 2

    while True:

        query = (
            ContentCategory.query
            .filter_by(
                slug=candidate
            )
        )

        if category_id is not None:

            query = query.filter(
                ContentCategory.id
                != category_id
            )

        if not query.first():

            return candidate

        candidate = (
            f"{base_slug}-{counter}"
        )

        counter += 1

# ============================================================
# POST MEDIA HELPERS
# ============================================================

def post_cloudinary_folder(
    post,
    media_group,
):
    """
    Build a predictable Cloudinary folder for a post.

    Example:

        creator-blog/posts/15/gallery
        creator-blog/posts/15/video
        creator-blog/posts/15/covers
    """

    root = current_app.config.get(
        "CLOUDINARY_FOLDER",
        "creator-blog",
    )

    return (
        f"{root}/posts/"
        f"{post.id}/"
        f"{media_group}"
    )


# ============================================================
# COVER IMAGE UPLOAD
# ============================================================

def process_cover_image(
    post,
    file,
):
    """
    Upload/replace the cover image for a post.

    For now ContentPost stores the cover URL.

    A ContentMedia row is also created so we retain the
    Cloudinary public_id required for deletion/replacement.
    """

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
            folder=post_cloudinary_folder(
                post,
                "covers",
            ),
        )

    except Exception:

        current_app.logger.exception(
            "Post cover upload failed."
        )

        return (
            False,
            "Cover image upload failed. "
            "Please try again.",
        )

    # --------------------------------------------------------
    # FIND EXISTING COVER MEDIA
    # --------------------------------------------------------

    existing_cover = (
        ContentMedia.query
        .filter_by(
            post_id=post.id,
            media_type="cover",
        )
        .first()
    )

    old_public_id = None

    if existing_cover:

        old_public_id = (
            existing_cover.public_id
        )

        existing_cover.media_url = (
            result["url"]
        )

        existing_cover.public_id = (
            result["public_id"]
        )

        existing_cover.resource_type = (
            "image"
        )

        existing_cover.thumbnail_url = None

        existing_cover.width = (
            result.get("width")
        )

        existing_cover.height = (
            result.get("height")
        )

    else:

        existing_cover = ContentMedia(
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
            existing_cover
        )

    # Main post card uses this URL.
    post.cover_image_url = (
        result["url"]
    )

    # --------------------------------------------------------
    # DELETE OLD CLOUDINARY ASSET
    # --------------------------------------------------------

    if old_public_id:

        try:

            delete_media(
                old_public_id,
                resource_type="image",
            )

        except Exception:

            current_app.logger.exception(
                "Old cover deletion failed."
            )

    return True, None


# ============================================================
# POST VIDEO UPLOAD
# ============================================================

def process_post_video(
    post,
    file,
):
    """
    Upload the primary Reel/Vlog video.

    A Reel or Vlog currently has one primary video.
    Uploading another replaces the previous one.
    """

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
            folder=post_cloudinary_folder(
                post,
                "video",
            ),
        )

    except Exception:

        current_app.logger.exception(
            "Post video upload failed."
        )

        return (
            False,
            "Video upload failed. "
            "Please try again.",
        )

    existing_video = (
        ContentMedia.query
        .filter_by(
            post_id=post.id,
            media_type="video",
        )
        .first()
    )

    old_public_id = None

    if existing_video:

        old_public_id = (
            existing_video.public_id
        )

        existing_video.media_url = (
            result["url"]
        )

        existing_video.public_id = (
            result["public_id"]
        )

        existing_video.resource_type = (
            "video"
        )

        existing_video.thumbnail_url = (
            result.get(
                "thumbnail_url"
            )
        )

        existing_video.duration_seconds = (
            result.get(
                "duration"
            )
        )

        existing_video.width = (
            result.get(
                "width"
            )
        )

        existing_video.height = (
            result.get(
                "height"
            )
        )

    else:

        existing_video = ContentMedia(
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
            width=result.get(
                "width"
            ),
            height=result.get(
                "height"
            ),
            media_order=0,
        )

        db.session.add(
            existing_video
        )

    if old_public_id:

        try:

            delete_media(
                old_public_id,
                resource_type="video",
            )

        except Exception:

            current_app.logger.exception(
                "Old post video deletion failed."
            )

    return True, None


# ============================================================
# STORY GALLERY UPLOAD
# ============================================================

def process_story_gallery(
    post,
    files,
):
    """
    Upload multiple story gallery images.

    Existing images remain in place.

    Newly uploaded images are appended to the gallery.
    """

    valid_files = [
        file
        for file in files
        if file and file.filename
    ]

    if not valid_files:

        return True, None

    # Keep the MVP reasonable.
    if len(valid_files) > 10:

        return (
            False,
            "You can upload up to 10 gallery "
            "images at a time.",
        )

    # Validate everything BEFORE uploading.
    for file in valid_files:

        valid, error = validate_image(
            file
        )

        if not valid:

            return False, error

    # Find current highest ordering number.
    existing_gallery = (
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

    if existing_gallery:

        next_order = (
            existing_gallery.media_order
            + 1
        )

    else:

        next_order = 1

    uploaded_assets = []

    try:

        for file in valid_files:

            result = upload_image(
                file,
                folder=post_cloudinary_folder(
                    post,
                    "gallery",
                ),
            )

            uploaded_assets.append(
                result
            )

            media = ContentMedia(
                post_id=post.id,
                media_type="gallery_image",
                media_url=result["url"],
                public_id=result["public_id"],
                resource_type="image",
                width=result.get(
                    "width"
                ),
                height=result.get(
                    "height"
                ),
                media_order=next_order,
            )

            db.session.add(
                media
            )

            next_order += 1

    except Exception:

        current_app.logger.exception(
            "Story gallery upload failed."
        )

        # If some uploads succeeded before one failed,
        # remove those Cloudinary assets.
        for uploaded in uploaded_assets:

            try:

                delete_media(
                    uploaded.get(
                        "public_id"
                    ),
                    resource_type="image",
                )

            except Exception:

                current_app.logger.exception(
                    "Gallery cleanup failed."
                )

        db.session.rollback()

        return (
            False,
            "Gallery upload failed. "
            "Please try again.",
        )

    return True, None
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

    # --------------------------------------------------------
    # ALREADY LOGGED IN
    # --------------------------------------------------------

    if session.get(
        "admin_user_id"
    ):

        return redirect(
            url_for(
                "admin.dashboard"
            )
        )

    # --------------------------------------------------------
    # LOGIN SUBMISSION
    # --------------------------------------------------------

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

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # FIND ADMIN
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # INVALID LOGIN
        # ----------------------------------------------------

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
        # SUCCESS
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
            "Welcome back.",
            "success",
        )

        return redirect(
            url_for(
                "admin.dashboard"
            )
        )

    # --------------------------------------------------------
    # GET
    # --------------------------------------------------------

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
# DASHBOARD
# ============================================================

@admin_bp.route("/")
@admin_required
def dashboard():

    # --------------------------------------------------------
    # COUNTS
    # --------------------------------------------------------

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

    exclusive_posts = (
        ContentPost.query
        .filter_by(
            access_level="subscriber"
        )
        .count()
    )

    email_subscribers = (
        EmailSubscriber.query
        .filter_by(
            status="active"
        )
        .count()
    )

    categories_count = (
        ContentCategory.query
        .count()
    )

    # --------------------------------------------------------
    # RECENT CONTENT
    # --------------------------------------------------------

    recent_posts = (
        ContentPost.query
        .order_by(
            ContentPost
            .created_at
            .desc()
        )
        .limit(6)
        .all()
    )

    # --------------------------------------------------------
    # CREATOR
    # --------------------------------------------------------

    creator = (
        CreatorProfile.query
        .first()
    )

    return render_template(
        "admin/dashboard.html",

        creator=creator,

        total_posts=total_posts,

        published_posts=published_posts,

        draft_posts=draft_posts,

        exclusive_posts=exclusive_posts,

        email_subscribers=(
            email_subscribers
        ),

        categories_count=(
            categories_count
        ),

        recent_posts=recent_posts,
    )


# ============================================================
# ANALYTICS
# ============================================================

@admin_bp.route(
    "/analytics"
)
@admin_required
def analytics():

    # ========================================================
    # CONTENT COUNTS
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

    # ========================================================
    # ACCESS LEVEL
    # ========================================================

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
    # CONTENT TYPES
    # ========================================================

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
    # NEWSLETTER SUBSCRIBERS
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
    # EMAIL DELIVERY
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
    # RECENT CONTENT
    # ========================================================

    recent_posts = (
        ContentPost.query
        .order_by(
            ContentPost
            .created_at
            .desc()
        )
        .limit(10)
        .all()
    )

    # ========================================================
    # MOST DISCUSSED CONTENT
    # ========================================================
    #
    # Count comments/replies belonging to each post.
    #
    # This is useful now because comments are one of the
    # engagement signals the platform already records.
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

            ContentPost
            .created_at
            .desc(),
        )
        .limit(5)
        .all()
    )

    # ========================================================
    # CREATOR
    # ========================================================

    creator = (
        CreatorProfile.query
        .first()
    )

    # ========================================================
    # TEMPLATE
    # ========================================================

    return render_template(
        "admin/analytics.html",

        creator=creator,

        # Content
        total_posts=total_posts,
        published_posts=published_posts,
        draft_posts=draft_posts,
        archived_posts=archived_posts,

        # Access
        public_posts=public_posts,
        exclusive_posts=exclusive_posts,

        # Types
        story_count=story_count,
        reel_count=reel_count,
        vlog_count=vlog_count,

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
        subscriber_count=(
            subscriber_count
        ),
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

        # Content activity
        recent_posts=recent_posts,

        most_commented_posts=(
            most_commented_posts
        ),
    )


# ============================================================
# CONTENT LIST
# ============================================================

@admin_bp.route(
    "/content"
)
@admin_required
def content_list():

    # --------------------------------------------------------
    # FILTERS
    # --------------------------------------------------------

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
    )

    # --------------------------------------------------------
    # STATUS FILTER
    # --------------------------------------------------------

    if status in {
        "draft",
        "published",
        "archived",
    }:

        query = (
            query.filter_by(
                status=status
            )
        )

    # --------------------------------------------------------
    # TYPE FILTER
    # --------------------------------------------------------

    if content_type in {
        "story",
        "reel",
        "vlog",
    }:

        query = (
            query.filter_by(
                content_type=(
                    content_type
                )
            )
        )

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    posts = (
        query
        .order_by(
            ContentPost
            .created_at
            .desc()
        )
        .all()
    )

    return render_template(
        "admin/content_list.html",

        posts=posts,

        selected_status=status,

        selected_type=(
            content_type
        ),
    )


# ============================================================
# CREATE CONTENT
# ============================================================

@admin_bp.route(
    "/content/new",
    methods=[
        "GET",
        "POST",
    ],
)
@admin_required
def content_new():

    categories = (
        ContentCategory.query
        .filter_by(
            is_active=True
        )
        .order_by(
            ContentCategory
            .display_order
            .asc(),

            ContentCategory
            .name
            .asc(),
        )
        .all()
    )

    # ========================================================
    # POST
    # ========================================================

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

        is_featured = (
            request.form.get(
                "is_featured"
            )
            == "on"
        )

        # ====================================================
        # VALIDATION
        # ====================================================

        if not title:

            flash(
                "Title is required.",
                "error",
            )

            return render_template(
                "admin/content_form.html",
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

        if status not in {
            "draft",
            "published",
            "archived",
        }:

            abort(400)

        # ====================================================
        # CATEGORY
        # ====================================================

        category = None

        if category_id:

            category = db.session.get(
                ContentCategory,
                category_id,
            )

            if not category:

                abort(400)

        # ====================================================
        # CREATE POST
        # ====================================================

        post = ContentPost(
            title=title,

            slug=unique_post_slug(
                title
            ),

            excerpt=(
                excerpt or None
            ),

            body=(
                body or None
            ),

            content_type=(
                content_type
            ),

            access_level=(
                access_level
            ),

            status=status,

            category=category,

            is_featured=(
                is_featured
            ),
        )

        if status == "published":

            post.published_at = (
                utc_now()
            )

        db.session.add(
            post
        )

        # Flush creates the ID without
        # permanently committing yet.
        db.session.flush()

        # ====================================================
        # COVER IMAGE
        # ====================================================

        cover_image = (
            request.files.get(
                "cover_image"
            )
        )

        success, error = (
            process_cover_image(
                post,
                cover_image,
            )
        )

        if not success:

            db.session.rollback()

            flash(
                error,
                "error",
            )

            return render_template(
                "admin/content_form.html",
                post=None,
                categories=categories,
            )

        # ====================================================
        # VIDEO
        # ====================================================

        if content_type in {
            "reel",
            "vlog",
        }:

            video_file = (
                request.files.get(
                    "video_file"
                )
            )

            success, error = (
                process_post_video(
                    post,
                    video_file,
                )
            )

            if not success:

                db.session.rollback()

                flash(
                    error,
                    "error",
                )

                return render_template(
                    "admin/content_form.html",
                    post=None,
                    categories=categories,
                )

        # ====================================================
        # STORY GALLERY
        # ====================================================

        if content_type == "story":

            gallery_files = (
                request.files.getlist(
                    "gallery_images"
                )
            )

            success, error = (
                process_story_gallery(
                    post,
                    gallery_files,
                )
            )

            if not success:

                db.session.rollback()

                flash(
                    error,
                    "error",
                )

                return render_template(
                    "admin/content_form.html",
                    post=None,
                    categories=categories,
                )

        # ====================================================
        # COMMIT
        # ====================================================

        # ====================================================
# SAVE POST FIRST
# ====================================================

        db.session.commit()


# ====================================================
# NEWSLETTER
# ====================================================

        if (
          post.status == "published"
          and post.access_level == "public"
        ):

          try:

            result = (
              notify_subscribers_about_post(
                post
              )
            )

            if result["sent"] > 0:

              flash(
                f'Content published and '
                f'{result["sent"]} subscriber '
                f'notification(s) sent.',
                "success",
              )

            else:

              flash(
                "Content published successfully.",
                "success",
              )

            if result["failed"] > 0:

              flash(
                f'{result["failed"]} email '
                f'notification(s) failed.',
                "warning",
              )

          except Exception:

            current_app.logger.exception(
              "Subscriber notification process failed."
            )

            flash(
              "Content was published, but subscriber "
              "notifications could not be completed.",
              "warning",
            )

        else:

         flash(
          "Content created successfully.",
          "success",
         )


        return redirect(
          url_for(
           "admin.content_edit",
           post_id=post.id,
          )
        )

    # ========================================================
    # GET
    # ========================================================

    return render_template(
        "admin/content_form.html",
        post=None,
        categories=categories,
    )


# ============================================================
# EDIT CONTENT
# ============================================================

@admin_bp.route(
    "/content/<int:post_id>/edit",
    methods=[
        "GET",
        "POST",
    ],
)
@admin_required
def content_edit(
    post_id
):

    post = db.get_or_404(
        ContentPost,
        post_id,
    )

    categories = (
        ContentCategory.query
        .filter_by(
            is_active=True
        )
        .order_by(
            ContentCategory
            .display_order
            .asc(),

            ContentCategory
            .name
            .asc(),
        )
        .all()
    )

    # ========================================================
    # UPDATE
    # ========================================================

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
                "admin/content_form.html",
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

        # ====================================================
        # VALIDATION
        # ====================================================

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

        if status not in {
            "draft",
            "published",
            "archived",
        }:

            abort(400)

        # ====================================================
        # CATEGORY
        # ====================================================

        category_id = (
            request.form.get(
                "category_id",
                type=int,
            )
        )

        category = None

        if category_id:

            category = db.session.get(
                ContentCategory,
                category_id,
            )

            if not category:

                abort(400)

        previous_status = (
            post.status
        )

        # ====================================================
        # UPDATE TEXT
        # ====================================================

        post.title = title

        post.slug = (
            unique_post_slug(
                title,
                post_id=post.id,
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

        # ====================================================
        # COVER
        # ====================================================

        cover_image = (
            request.files.get(
                "cover_image"
            )
        )

        success, error = (
            process_cover_image(
                post,
                cover_image,
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
                    "admin.content_edit",
                    post_id=post.id,
                )
            )

        # ====================================================
        # VIDEO
        # ====================================================

        if content_type in {
            "reel",
            "vlog",
        }:

            video_file = (
                request.files.get(
                    "video_file"
                )
            )

            success, error = (
                process_post_video(
                    post,
                    video_file,
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
                        "admin.content_edit",
                        post_id=post.id,
                    )
                )

        # ====================================================
        # STORY GALLERY
        # ====================================================

        if content_type == "story":

            gallery_files = (
                request.files.getlist(
                    "gallery_images"
                )
            )

            success, error = (
                process_story_gallery(
                    post,
                    gallery_files,
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
                        "admin.content_edit",
                        post_id=post.id,
                    )
                )

        # ====================================================
        # SAVE
        # ====================================================

        db.session.commit()

        flash(
            "Content updated.",
            "success",
        )

        return redirect(
            url_for(
                "admin.content_edit",
                post_id=post.id,
            )
        )

    # ========================================================
    # GET
    # ========================================================

    return render_template(
        "admin/content_form.html",
        post=post,
        categories=categories,
    )


# ============================================================
# REMOVE POST COVER
# ============================================================

@admin_bp.route(
    "/content/<int:post_id>/cover/remove",
    methods=["POST"],
)
@admin_required
def content_remove_cover(
    post_id
):

    post = db.get_or_404(
        ContentPost,
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
                        "admin.content_edit",
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
            "admin.content_edit",
            post_id=post.id,
        )
    )


# ============================================================
# REMOVE POST VIDEO
# ============================================================

@admin_bp.route(
    "/content/<int:post_id>/video/remove",
    methods=["POST"],
)
@admin_required
def content_remove_video(
    post_id
):

    post = db.get_or_404(
        ContentPost,
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
                "admin.content_edit",
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
                "Post video deletion failed."
            )

            flash(
                "Video could not be removed.",
                "error",
            )

            return redirect(
                url_for(
                    "admin.content_edit",
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
            "admin.content_edit",
            post_id=post.id,
        )
    )


# ============================================================
# REMOVE STORY GALLERY IMAGE
# ============================================================

@admin_bp.route(
    "/content/<int:post_id>/gallery/<int:media_id>/remove",
    methods=["POST"],
)
@admin_required
def content_remove_gallery_image(
    post_id,
    media_id,
):

    post = db.get_or_404(
        ContentPost,
        post_id,
    )

    media = db.get_or_404(
        ContentMedia,
        media_id,
    )

    # Important:
    # prevent deleting media belonging to another post.
    if (
        media.post_id != post.id
        or media.media_type
        != "gallery_image"
    ):

        abort(404)

    if media.public_id:

        try:

            delete_media(
                media.public_id,
                resource_type="image",
            )

        except Exception:

            current_app.logger.exception(
                "Gallery image deletion failed."
            )

            flash(
                "Gallery image could not be removed.",
                "error",
            )

            return redirect(
                url_for(
                    "admin.content_edit",
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
            "admin.content_edit",
            post_id=post.id,
        )
    )
# ============================================================
# PUBLISH CONTENT
# ============================================================
# ============================================================
# PUBLISH CONTENT
# ============================================================

@admin_bp.route(
    "/content/<int:post_id>/publish",
    methods=["POST"],
)
@admin_required
def content_publish(
    post_id
):

    post = db.get_or_404(
        ContentPost,
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

    # ========================================================
    # NEWSLETTER
    # ========================================================

    if (
        not was_published
        and post.access_level == "public"
    ):

        try:

            result = (
                notify_subscribers_about_post(
                    post
                )
            )

            flash(
                "Content published.",
                "success",
            )

            if result["sent"] > 0:

                flash(
                    f'{result["sent"]} subscriber '
                    f'notification(s) sent.',
                    "success",
                )

            if result["failed"] > 0:

                flash(
                    f'{result["failed"]} email '
                    f'notification(s) failed.',
                    "warning",
                )

        except Exception:

            current_app.logger.exception(
                "Subscriber notification failed."
            )

            flash(
                "Content was published, but "
                "subscriber notifications failed.",
                "warning",
            )

    else:

        flash(
            "Content published.",
            "success",
        )

    return redirect(
        url_for(
            "admin.content_list"
        )
    )
# ============================================================
# ARCHIVE CONTENT
# ============================================================

@admin_bp.route(
    "/content/<int:post_id>/archive",
    methods=["POST"],
)
@admin_required
def content_archive(
    post_id
):

    post = db.get_or_404(
        ContentPost,
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
            "admin.content_list"
        )
    )



# ============================================================
# DELETE CONTENT
# ============================================================

@admin_bp.route(
    "/content/<int:post_id>/delete",
    methods=["POST"],
)
@admin_required
def content_delete(
    post_id
):

    post = db.get_or_404(
        ContentPost,
        post_id,
    )

    title = post.title

    # ========================================================
    # DELETE CLOUDINARY MEDIA
    # ========================================================

    media_items = list(
        post.media
    )

    for media in media_items:

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
                "Could not delete Cloudinary "
                "asset while deleting post."
            )

    # ========================================================
    # DELETE DATABASE POST
    # ========================================================

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
            "admin.content_list"
        )
    )

# ============================================================
# CATEGORIES / FOLDERS
# ============================================================

@admin_bp.route(
    "/categories",
    methods=[
        "GET",
        "POST",
    ],
)
@admin_required
def categories():

    # --------------------------------------------------------
    # CREATE CATEGORY
    # --------------------------------------------------------

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

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if not name:

            flash(
                "Folder name is required.",
                "error",
            )

            return redirect(
                url_for(
                    "admin.categories"
                )
            )

        # ----------------------------------------------------
        # CREATE
        # ----------------------------------------------------

        category = ContentCategory(
            name=name,

            slug=unique_category_slug(
                name
            ),

            description=(
                description or None
            ),

            is_active=True,

            display_order=(
                ContentCategory.query
                .count()
                + 1
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
                "admin.categories"
            )
        )

    # --------------------------------------------------------
    # LIST CATEGORIES
    # --------------------------------------------------------

    category_items = (
        ContentCategory.query
        .order_by(
            ContentCategory
            .display_order
            .asc(),

            ContentCategory
            .name
            .asc(),
        )
        .all()
    )

    return render_template(
        "admin/categories.html",
        categories=category_items,
    )
    
    
    
    
# ============================================================
# CREATOR PROFILE
# ============================================================

@admin_bp.route(
    "/profile",
    methods=[
        "GET",
        "POST",
    ],
)
@admin_required
def profile():

    creator = (
        CreatorProfile.query
        .first()
    )

    if not creator:

        flash(
            "Creator profile was not found.",
            "error",
        )

        return redirect(
            url_for(
                "admin.dashboard"
            )
        )

    # ========================================================
    # UPDATE PROFILE
    # ========================================================

    if request.method == "POST":

        display_name = (
            request.form
            .get(
                "display_name",
                "",
            )
            .strip()
        )

        username = (
            request.form
            .get(
                "username",
                "",
            )
            .strip()
            .lower()
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

        instagram_url = (
            request.form
            .get(
                "instagram_url",
                "",
            )
            .strip()
        )

        tiktok_url = (
            request.form
            .get(
                "tiktok_url",
                "",
            )
            .strip()
        )

        youtube_url = (
            request.form
            .get(
                "youtube_url",
                "",
            )
            .strip()
        )

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if not display_name:

            flash(
                "Display name is required.",
                "error",
            )

            return render_template(
                "admin/profile.html",
                creator=creator,
            )

        if not username:

            flash(
                "Username is required.",
                "error",
            )

            return render_template(
                "admin/profile.html",
                creator=creator,
            )

        duplicate_username = (
            CreatorProfile.query
            .filter(
                CreatorProfile.username
                == username,

                CreatorProfile.id
                != creator.id,
            )
            .first()
        )

        if duplicate_username:

            flash(
                "That username is already being used.",
                "error",
            )

            return render_template(
                "admin/profile.html",
                creator=creator,
            )

        # ----------------------------------------------------
        # FILES
        # ----------------------------------------------------

        profile_image = (
            request.files.get(
                "profile_image"
            )
        )

        intro_reel = (
            request.files.get(
                "intro_reel"
            )
        )

        # ----------------------------------------------------
        # PROFILE IMAGE
        # ----------------------------------------------------

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
                    "admin/profile.html",
                    creator=creator,
                )

            try:

                image_result = (
                    upload_image(
                        profile_image,
                        folder=(
                            current_app.config[
                                "CLOUDINARY_FOLDER"
                            ]
                            + "/profile"
                        ),
                    )
                )

            except Exception as exc:

                current_app.logger.exception(
                    "Profile image upload failed."
                )

                flash(
                    "Profile image upload failed. "
                    "Please try again.",
                    "error",
                )

                return render_template(
                    "admin/profile.html",
                    creator=creator,
                )

            old_public_id = (
                creator
                .profile_image_public_id
            )

            creator.profile_image_url = (
                image_result["url"]
            )

            creator.profile_image_public_id = (
                image_result[
                    "public_id"
                ]
            )

            # Delete old image only AFTER
            # the new upload succeeded.

            if old_public_id:

                try:

                    delete_media(
                        old_public_id,
                        resource_type="image",
                    )

                except Exception:

                    current_app.logger.exception(
                        "Could not delete old "
                        "profile image."
                    )

        # ----------------------------------------------------
        # INTRO REEL
        # ----------------------------------------------------

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
                    "admin/profile.html",
                    creator=creator,
                )

            try:

                video_result = (
                    upload_video(
                        intro_reel,
                        folder=(
                            current_app.config[
                                "CLOUDINARY_FOLDER"
                            ]
                            + "/intro-reels"
                        ),
                    )
                )

            except Exception:

                current_app.logger.exception(
                    "Intro reel upload failed."
                )

                flash(
                    "Intro reel upload failed. "
                    "Please try again.",
                    "error",
                )

                return render_template(
                    "admin/profile.html",
                    creator=creator,
                )

            old_public_id = (
                creator
                .intro_reel_public_id
            )

            creator.intro_reel_url = (
                video_result["url"]
            )

            creator.intro_reel_public_id = (
                video_result[
                    "public_id"
                ]
            )

            creator.intro_reel_thumbnail_url = (
                video_result[
                    "thumbnail_url"
                ]
            )

            if old_public_id:

                try:

                    delete_media(
                        old_public_id,
                        resource_type="video",
                    )

                except Exception:

                    current_app.logger.exception(
                        "Could not delete old "
                        "intro reel."
                    )

        # ----------------------------------------------------
        # UPDATE TEXT
        # ----------------------------------------------------

        creator.display_name = (
            display_name
        )

        creator.username = username

        creator.tagline = (
            tagline or None
        )

        creator.bio = (
            bio or None
        )

        creator.instagram_url = (
            instagram_url or None
        )

        creator.tiktok_url = (
            tiktok_url or None
        )

        creator.youtube_url = (
            youtube_url or None
        )

        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        db.session.commit()

        flash(
            "Profile updated successfully.",
            "success",
        )

        return redirect(
            url_for(
                "admin.profile"
            )
        )

    return render_template(
        "admin/profile.html",
        creator=creator,
    )


# ============================================================
# REMOVE PROFILE IMAGE
# ============================================================

@admin_bp.route(
    "/profile/remove-image",
    methods=["POST"],
)
@admin_required
def profile_remove_image():

    creator = (
        CreatorProfile.query
        .first()
    )

    if not creator:

        abort(404)

    public_id = (
        creator
        .profile_image_public_id
    )

    if public_id:

        try:

            delete_media(
                public_id,
                resource_type="image",
            )

        except Exception:

            current_app.logger.exception(
                "Profile image deletion failed."
            )

            flash(
                "The image could not be removed.",
                "error",
            )

            return redirect(
                url_for(
                    "admin.profile"
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
            "admin.profile"
        )
    )


# ============================================================
# REMOVE INTRO REEL
# ============================================================

@admin_bp.route(
    "/profile/remove-intro-reel",
    methods=["POST"],
)
@admin_required
def profile_remove_intro_reel():

    creator = (
        CreatorProfile.query
        .first()
    )

    if not creator:

        abort(404)

    public_id = (
        creator
        .intro_reel_public_id
    )

    if public_id:

        try:

            delete_media(
                public_id,
                resource_type="video",
            )

        except Exception:

            current_app.logger.exception(
                "Intro reel deletion failed."
            )

            flash(
                "The intro reel could not be removed.",
                "error",
            )

            return redirect(
                url_for(
                    "admin.profile"
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
            "admin.profile"
        )
    )
    
    
# ============================================================
# COMMENTS
# ============================================================

@admin_bp.route(
    "/comments"
)
@admin_required
def comments():

    status = (
        request.args
        .get(
            "status",
            "",
        )
        .strip()
    )

    query = Comment.query

    if status in {
        "approved",
        "hidden",
        "pending",
    }:

        query = query.filter_by(
            status=status
        )

    comment_items = (
        query
        .order_by(
            Comment.created_at.desc()
        )
        .all()
    )

    approved_count = (
        Comment.query
        .filter_by(
            status="approved"
        )
        .count()
    )

    hidden_count = (
        Comment.query
        .filter_by(
            status="hidden"
        )
        .count()
    )

    pending_count = (
        Comment.query
        .filter_by(
            status="pending"
        )
        .count()
    )

    return render_template(
        "admin/comments.html",
        comments=comment_items,
        selected_status=status,
        approved_count=approved_count,
        hidden_count=hidden_count,
        pending_count=pending_count,
    )


# ============================================================
# APPROVE COMMENT
# ============================================================

@admin_bp.route(
    "/comments/<int:comment_id>/approve",
    methods=["POST"],
)
@admin_required
def comment_approve(
    comment_id
):

    comment = db.get_or_404(
        Comment,
        comment_id,
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
            "admin.comments"
        )
    )


# ============================================================
# HIDE COMMENT
# ============================================================

@admin_bp.route(
    "/comments/<int:comment_id>/hide",
    methods=["POST"],
)
@admin_required
def comment_hide(
    comment_id
):

    comment = db.get_or_404(
        Comment,
        comment_id,
    )

    comment.status = "hidden"

    # Hide replies when the parent is hidden.
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
            "admin.comments"
        )
    )


# ============================================================
# DELETE COMMENT
# ============================================================

@admin_bp.route(
    "/comments/<int:comment_id>/delete",
    methods=["POST"],
)
@admin_required
def comment_delete(
    comment_id
):

    comment = db.get_or_404(
        Comment,
        comment_id,
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
            "admin.comments"
        )
    )


# ============================================================
# CREATOR REPLY
# ============================================================

@admin_bp.route(
    "/comments/<int:comment_id>/reply",
    methods=["POST"],
)
@admin_required
def comment_creator_reply(
    comment_id
):

    parent = db.get_or_404(
        Comment,
        comment_id,
    )

    # Keep replies one level deep.
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

    if not body:

        flash(
            "Write a reply first.",
            "error",
        )

        return redirect(
            url_for(
                "admin.comments"
            )
        )

    if len(body) > 1500:

        flash(
            "Reply is too long.",
            "error",
        )

        return redirect(
            url_for(
                "admin.comments"
            )
        )

    creator = (
        CreatorProfile.query
        .first()
    )

    creator_name = (
        creator.display_name
        if creator
        else "Creator"
    )

    reply = Comment(
        post_id=parent.post_id,
        parent_id=parent.id,
        author_name=creator_name,
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
            "admin.comments"
        )
    )
    
    
# ============================================================
# SUBSCRIBERS
# ============================================================

@admin_bp.route(
    "/subscribers"
)
@admin_required
def subscribers():

    status = (
        request.args
        .get(
            "status",
            "",
        )
        .strip()
    )

    query = EmailSubscriber.query

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
            EmailSubscriber
            .created_at
            .desc()
        )
        .all()
    )

    total_count = (
        EmailSubscriber.query.count()
    )

    active_count = (
        EmailSubscriber.query
        .filter_by(
            status="active"
        )
        .count()
    )

    pending_count = (
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

    recent_deliveries = (
        EmailDelivery.query
        .order_by(
            EmailDelivery
            .created_at
            .desc()
        )
        .limit(20)
        .all()
    )

    return render_template(
        "admin/subscribers.html",
        subscribers=subscriber_items,
        selected_status=status,
        total_count=total_count,
        active_count=active_count,
        pending_count=pending_count,
        unsubscribed_count=(
            unsubscribed_count
        ),
        recent_deliveries=(
            recent_deliveries
        ),
    )
