# ============================================================
# CLOUDINARY MEDIA SERVICE
# ============================================================

import cloudinary
import cloudinary.uploader

from flask import current_app


# ============================================================
# ALLOWED FILES
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

    if not all(
        [
            cloud_name,
            api_key,
            api_secret,
        ]
    ):

        raise RuntimeError(
            "Cloudinary is not configured. "
            "Check CLOUDINARY_CLOUD_NAME, "
            "CLOUDINARY_API_KEY and "
            "CLOUDINARY_API_SECRET in .env."
        )

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )


# ============================================================
# EXTENSION
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
# UPLOAD IMAGE
# ============================================================

def upload_image(
    file,
    folder,
):

    configure_cloudinary()

    result = (
        cloudinary.uploader.upload(
            file,
            folder=folder,
            resource_type="image",
            overwrite=False,
        )
    )

    return {
        "url": result.get(
            "secure_url"
        ),

        "public_id": result.get(
            "public_id"
        ),

        "resource_type": "image",

        "width": result.get(
            "width"
        ),

        "height": result.get(
            "height"
        ),
    }


# ============================================================
# UPLOAD VIDEO
# ============================================================

def upload_video(
    file,
    folder,
):

    configure_cloudinary()

    result = (
        cloudinary.uploader.upload(
            file,
            folder=folder,
            resource_type="video",
            overwrite=False,
        )
    )

    public_id = result.get(
        "public_id"
    )

    thumbnail_url = None

    if public_id:

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

    return {
        "url": result.get(
            "secure_url"
        ),

        "public_id": public_id,

        "resource_type": "video",

        "thumbnail_url": (
            thumbnail_url
        ),

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
# DELETE MEDIA
# ============================================================

def delete_media(
    public_id,
    resource_type="image",
):

    if not public_id:

        return None

    configure_cloudinary()

    return (
        cloudinary.uploader.destroy(
            public_id,
            resource_type=resource_type,
            invalidate=True,
        )
    )