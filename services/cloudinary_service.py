# ============================================================
# KALXA CREATOR
# CLOUDINARY MEDIA SERVICE
# ============================================================
#
# Supports:
#
# 1. Public image uploads
# 2. Public video uploads
# 3. Authenticated image uploads
# 4. Authenticated video uploads
# 5. Public video thumbnails
# 6. Media validation
# 7. Media deletion
# 8. Authenticated media delivery URLs
#
# IMPORTANT:
#
# Exclusive media must be uploaded using:
#
#     private=True
#
# Authenticated media must only be delivered after
# verifying the fan's membership on the server.
#
# ============================================================

import cloudinary
import cloudinary.uploader
import cloudinary.utils

from flask import current_app


# ============================================================
# ALLOWED FILE EXTENSIONS
# ============================================================

IMAGE_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
}

VIDEO_EXTENSIONS = {
    "mp4",
    "mov",
    "m4v",
    "webm",
}


# ============================================================
# CONFIGURATION
# ============================================================

def configure_cloudinary():

    cloud_name = current_app.config.get(
        "CLOUDINARY_CLOUD_NAME"
    )

    api_key = current_app.config.get(
        "CLOUDINARY_API_KEY"
    )

    api_secret = current_app.config.get(
        "CLOUDINARY_API_SECRET"
    )

    if not all([
        cloud_name,
        api_key,
        api_secret,
    ]):

        raise RuntimeError(
            "Cloudinary is not configured. "
            "Check CLOUDINARY_CLOUD_NAME, "
            "CLOUDINARY_API_KEY and "
            "CLOUDINARY_API_SECRET."
        )

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )


# ============================================================
# FILE EXTENSION
# ============================================================

def get_extension(filename):

    if (
        not filename
        or "." not in filename
    ):
        return ""

    return (
        filename
        .rsplit(".", 1)[1]
        .lower()
    )


# ============================================================
# IMAGE VALIDATION
# ============================================================

def validate_image(file):

    if (
        not file
        or not file.filename
    ):

        return (
            False,
            "Please select an image.",
        )

    extension = get_extension(
        file.filename
    )

    if extension not in IMAGE_EXTENSIONS:

        return (
            False,
            "Image must be JPG, JPEG, PNG or WebP.",
        )

    return True, None


# ============================================================
# VIDEO VALIDATION
# ============================================================

def validate_video(file):

    if (
        not file
        or not file.filename
    ):

        return (
            False,
            "Please select a video.",
        )

    extension = get_extension(
        file.filename
    )

    if extension not in VIDEO_EXTENSIONS:

        return (
            False,
            "Video must be MP4, MOV, M4V or WebM.",
        )

    return True, None


# ============================================================
# INTERNAL UPLOAD HELPER
# ============================================================

def _upload_media(
    file,
    folder,
    resource_type,
    private=False,
):

    configure_cloudinary()

    if resource_type not in {
        "image",
        "video",
    }:

        raise ValueError(
            "Unsupported Cloudinary resource type."
        )

    delivery_type = (
        "authenticated"
        if private
        else "upload"
    )

    result = cloudinary.uploader.upload(
        file,
        folder=folder,
        resource_type=resource_type,
        type=delivery_type,
        overwrite=False,
    )

    public_id = result.get(
        "public_id"
    )

    thumbnail_url = None

    # --------------------------------------------------------
    # PUBLIC VIDEO THUMBNAILS
    # --------------------------------------------------------
    #
    # Never create a public thumbnail for exclusive videos.
    #
    # --------------------------------------------------------

    if (
        resource_type == "video"
        and public_id
        and not private
    ):

        thumbnail_url = (
            cloudinary.CloudinaryVideo(
                public_id
            )
            .build_url(
                format="jpg",
                start_offset="1",
                width=720,
                crop="limit",
                secure=True,
            )
        )

    # --------------------------------------------------------
    # RETURN MEDIA METADATA
    # --------------------------------------------------------

    return {

        # Do not expose authenticated asset URLs.
        "url": (
            None
            if private
            else result.get("secure_url")
        ),

        "public_id": public_id,

        "resource_type": resource_type,

        "delivery_type": delivery_type,

        "is_private": bool(private),

        "thumbnail_url": thumbnail_url,

        "duration": result.get(
            "duration"
        ),

        "width": result.get(
            "width"
        ),

        "height": result.get(
            "height"
        ),
    }


# ============================================================
# UPLOAD IMAGE
# ============================================================

def upload_image(
    file,
    folder,
    private=False,
):

    return _upload_media(
        file=file,
        folder=folder,
        resource_type="image",
        private=private,
    )


# ============================================================
# UPLOAD VIDEO
# ============================================================

def upload_video(
    file,
    folder,
    private=False,
):

    return _upload_media(
        file=file,
        folder=folder,
        resource_type="video",
        private=private,
    )


# ============================================================
# AUTHENTICATED MEDIA URL
# ============================================================
#
# This helper generates a signed Cloudinary URL.
#
# IMPORTANT:
#
# A signed URL is not automatically a short-lived URL.
#
# The caller must:
#
# 1. Verify the creator owns the post, or
# 2. Verify the fan has an active membership.
#
# For production-grade expiring access, configure
# Cloudinary token-based authentication.
#
# Do not use this function as a substitute for
# membership authorization.
#
# ============================================================

def authenticated_media_url(
    public_id,
    resource_type="image",
    **transformations,
):

    if not public_id:

        raise ValueError(
            "Media public_id is required."
        )

    if resource_type not in {
        "image",
        "video",
    }:

        raise ValueError(
            "Unsupported media resource type."
        )

    configure_cloudinary()

    options = {

        "resource_type": resource_type,

        "type": "authenticated",

        "secure": True,

        "sign_url": True,
    }

    # Prevent callers from overriding security options.
    forbidden_options = {
        "type",
        "resource_type",
        "secure",
        "sign_url",
        "api_secret",
        "api_key",
        "cloud_name",
    }

    for key in transformations:

        if key in forbidden_options:

            raise ValueError(
                "Cannot override authenticated "
                "delivery settings."
            )

    options.update(
        transformations
    )

    url, _ = cloudinary.utils.cloudinary_url(
        public_id,
        **options,
    )

    return url


# ============================================================
# DELETE MEDIA
# ============================================================

def delete_media(
    public_id,
    resource_type="image",
    delivery_type="upload",
):

    if not public_id:

        return None

    if resource_type not in {
        "image",
        "video",
    }:

        raise ValueError(
            "Unsupported media resource type."
        )

    if delivery_type not in {
        "upload",
        "authenticated",
    }:

        raise ValueError(
            "Unsupported Cloudinary delivery type."
        )

    configure_cloudinary()

    return cloudinary.uploader.destroy(
        public_id,
        resource_type=resource_type,
        type=delivery_type,
        invalidate=True,
    )
