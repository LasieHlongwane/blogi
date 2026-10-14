
"""
Kalxa Creator — Website Settings Routes

Attach website settings endpoints to the existing Studio blueprint.

In routes/studio.py, call:

    register_website_settings(
        studio_bp,
        studio_required,
        current_creator_account,
    )

before registering studio_bp on the Flask application.

Features:
- Website title and tagline
- Basic branding colours
- Advanced branding
- Logo, favicon and cover image uploads
- Creator subdomain registration
- Custom domain ownership verification
- Custom domain removal

Important:
DNS ownership verification does not automatically activate
a custom domain. DNS routing and TLS must be configured
at the infrastructure level.
"""

import ipaddress
import re
import secrets

from datetime import datetime, timezone

from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from sqlalchemy.exc import IntegrityError

from extensions import db

from models import (
    CreatorBranding,
    CreatorDomain,
)

from services.cloudinary_service import (
    delete_media,
    upload_image,
    validate_image,
)

from services.plan_service import (
    FEATURE_ADVANCED_BRANDING,
    FEATURE_BRANDING,
    FEATURE_CUSTOM_DOMAIN,
    creator_has_feature,
    creator_plan_summary,
)

from services.hostname_resolver import normalize_host


# ============================================================
# CONSTANTS
# ============================================================

HEX_COLOR = re.compile(
    r"^#[0-9a-fA-F]{6}$"
)

DOMAIN_LABEL = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)

VALID_THEMES = {
    "light",
    "dark",
}

VALID_FONTS = {
    "system",
    "sans",
    "serif",
    "mono",
}

MEDIA_KINDS = {
    "logo",
    "favicon",
    "cover_image",
}

DOMAIN_SUFFIX = ".creators.kalxa.co.za"

VERIFICATION_PREFIX = "_kalxa-verification"


# ============================================================
# UTILITIES
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def valid_external_hostname(hostname):
    """
    Validate a custom hostname.

    Only public-looking DNS hostnames are accepted.

    This does not prove ownership.
    Ownership is checked separately through DNS TXT.
    """

    if not isinstance(hostname, str):
        return False

    hostname = hostname.strip().lower()

    if not hostname:
        return False

    if len(hostname) > 253:
        return False

    if hostname.endswith("."):
        return False

    if hostname.startswith("."):
        return False

    if "." not in hostname:
        return False

    if any(
        character in hostname
        for character in (
            "/",
            "\\",
            ":",
            "@",
            " ",
            "\t",
            "\n",
        )
    ):
        return False

    if hostname in {
        "kalxa.co.za",
        "creators.kalxa.co.za",
    }:
        return False

    if hostname.endswith(".kalxa.co.za"):
        return False

    labels = hostname.split(".")

    if len(labels) < 2:
        return False

    if not all(
        DOMAIN_LABEL.fullmatch(label)
        for label in labels
    ):
        return False

    if labels[-1].isdigit():
        return False

    try:
        ipaddress.ip_address(hostname)
        return False
    except ValueError:
        pass

    return True


def verify_domain_txt_record(domain):
    """
    Check the DNS TXT ownership challenge.

    Required record:

        _kalxa-verification.example.co.za

    TXT value:

        domain.verification_token

    DNS lookup failures return False.
    """

    try:
        import dns.resolver

        record_name = (
            f"{VERIFICATION_PREFIX}."
            f"{domain.hostname}"
        )

        answers = dns.resolver.resolve(
            record_name,
            "TXT",
            lifetime=5,
        )

        expected_token = str(
            domain.verification_token or ""
        )

        if not expected_token:
            return False

        for answer in answers:

            try:
                record_value = b"".join(
                    answer.strings
                ).decode(
                    "utf-8"
                )

            except (
                AttributeError,
                UnicodeDecodeError,
                TypeError,
            ):
                continue

            if secrets.compare_digest(
                record_value,
                expected_token,
            ):
                return True

    except Exception:
        current_app.logger.info(
            "DNS TXT verification unavailable "
            "for creator domain ID %s",
            domain.id,
        )

    return False


# ============================================================
# ROUTE REGISTRATION
# ============================================================

def register_website_settings(
    studio_bp,
    studio_required,
    current_creator_account,
):
    """
    Register website settings routes on the Studio blueprint.

    Call once before app.register_blueprint(studio_bp).
    """

    # ========================================================
    # CONTEXT
    # ========================================================

    def settings_context(account):

        branding = (
            CreatorBranding.query
            .filter_by(
                creator_account_id=account.id
            )
            .first()
        )

        domains = (
            CreatorDomain.query
            .filter_by(
                creator_account_id=account.id
            )
            .order_by(
                CreatorDomain.created_at.asc()
            )
            .all()
        )

        return {
            "creator_account": account,
            "branding": branding,
            "domains": domains,
            "plan_summary": creator_plan_summary(
                account
            ),
            "expected_subdomain": (
                f"{account.username.lower()}"
                f"{DOMAIN_SUFFIX}"
            ),
            "verification_prefix": (
                VERIFICATION_PREFIX
            ),
            "can_use_branding": creator_has_feature(
                account,
                FEATURE_BRANDING,
            ),
            "can_use_advanced_branding": creator_has_feature(
                account,
                FEATURE_ADVANCED_BRANDING,
            ),
            "can_use_custom_domain": creator_has_feature(
                account,
                FEATURE_CUSTOM_DOMAIN,
            ),
        }

    def settings_page(account):

        return render_template(
            "studio/website_settings.html",
            **settings_context(account),
        )

    # ========================================================
    # BRANDING HELPERS
    # ========================================================

    def get_or_create_branding(account):

        branding = (
            CreatorBranding.query
            .filter_by(
                creator_account_id=account.id
            )
            .first()
        )

        if branding is None:

            branding = CreatorBranding(
                creator_account_id=account.id
            )

            db.session.add(
                branding
            )

        return branding

    def save_error(message):

        db.session.rollback()

        flash(
            message,
            "error",
        )

        return redirect(
            url_for(
                "studio.website_settings"
            )
        )

    # ========================================================
    # WEBSITE SETTINGS PAGE
    # ========================================================

    @studio_bp.route(
        "/website",
        methods=["GET"],
        endpoint="website_settings",
    )
    @studio_required
    def website_settings():

        account = current_creator_account()

        if not creator_has_feature(
            account,
            FEATURE_BRANDING,
        ):
            abort(403)

        return settings_page(
            account
        )

    # ========================================================
    # SAVE BRANDING
    # ========================================================

    @studio_bp.route(
        "/website/branding",
        methods=["POST"],
        endpoint="website_branding_save",
    )
    @studio_required
    def website_branding_save():

        account = current_creator_account()

        if not creator_has_feature(
            account,
            FEATURE_BRANDING,
        ):
            abort(403)

        site_title = request.form.get(
            "site_title",
            "",
        ).strip()

        tagline = request.form.get(
            "site_tagline",
            "",
        ).strip()

        if (
            len(site_title) > 120
            or len(tagline) > 255
        ):
            flash(
                "Website title or tagline is too long.",
                "error",
            )

            return redirect(
                url_for(
                    "studio.website_settings"
                )
            )

        # Validate basic colours before modifying database.

        basic_colors = {}

        for field in (
            "primary_color",
            "accent_color",
        ):

            color = request.form.get(
                field,
                "",
            ).strip()

            if not HEX_COLOR.fullmatch(color):

                flash(
                    f'Invalid {field.replace("_", " ")}.',
                    "error",
                )

                return redirect(
                    url_for(
                        "studio.website_settings"
                    )
                )

            basic_colors[field] = color.upper()

        advanced_values = {}

        if creator_has_feature(
            account,
            FEATURE_ADVANCED_BRANDING,
        ):

            for field in (
                "background_color",
                "text_color",
            ):

                color = request.form.get(
                    field,
                    "",
                ).strip()

                if not HEX_COLOR.fullmatch(color):

                    flash(
                        f'Invalid {field.replace("_", " ")}.',
                        "error",
                    )

                    return redirect(
                        url_for(
                            "studio.website_settings"
                        )
                    )

                advanced_values[field] = (
                    color.upper()
                )

            theme = request.form.get(
                "theme",
                "light",
            )

            font = request.form.get(
                "font_family",
                "system",
            )

            footer = request.form.get(
                "footer_text",
                "",
            ).strip()

            if (
                theme not in VALID_THEMES
                or font not in VALID_FONTS
                or len(footer) > 255
            ):

                flash(
                    "Invalid advanced branding settings.",
                    "error",
                )

                return redirect(
                    url_for(
                        "studio.website_settings"
                    )
                )

            advanced_values.update({
                "theme": theme,
                "font_family": font,
                "footer_text": footer or None,
            })

        try:

            branding = get_or_create_branding(
                account
            )

            branding.site_title = (
                site_title or None
            )

            branding.site_tagline = (
                tagline or None
            )

            for field, value in basic_colors.items():

                setattr(
                    branding,
                    field,
                    value,
                )

            for field, value in advanced_values.items():

                setattr(
                    branding,
                    field,
                    value,
                )

            db.session.commit()

        except Exception:

            current_app.logger.exception(
                "Failed saving creator branding "
                "for account %s",
                account.id,
            )

            return save_error(
                "Unable to save website settings."
            )

        flash(
            "Website branding saved.",
            "success",
        )

        return redirect(
            url_for(
                "studio.website_settings"
            )
        )

    # ========================================================
    # UPLOAD BRANDING MEDIA
    # ========================================================

    @studio_bp.route(
        "/website/media/<kind>",
        methods=["POST"],
        endpoint="website_media_upload",
    )
    @studio_required
    def website_media_upload(kind):

        account = current_creator_account()

        if not creator_has_feature(
            account,
            FEATURE_BRANDING,
        ):
            abort(403)

        if kind not in MEDIA_KINDS:
            abort(404)

        file = request.files.get(
            "image"
        )

        if (
            not file
            or not file.filename
        ):

            flash(
                "Select an image.",
                "error",
            )

            return redirect(
                url_for(
                    "studio.website_settings"
                )
            )

        valid, error = validate_image(
            file
        )

        if not valid:

            flash(
                error,
                "error",
            )

            return redirect(
                url_for(
                    "studio.website_settings"
                )
            )

        # Upload to Cloudinary first.
        # Do not replace the existing database image
        # until the new upload has succeeded.

        try:

            root = current_app.config.get(
                "CLOUDINARY_FOLDER",
                "creator-blog",
            )

            result = upload_image(
                file,
                folder=(
                    f"{root}/creators/"
                    f"{account.id}/branding/{kind}"
                ),
            )

            new_url = result["url"]
            new_public_id = result["public_id"]

            if not new_url or not new_public_id:
                raise ValueError(
                    "Cloudinary returned incomplete upload data."
                )

        except Exception:

            current_app.logger.exception(
                "Branding media upload failed "
                "for creator %s",
                account.id,
            )

            flash(
                "Image upload failed.",
                "error",
            )

            return redirect(
                url_for(
                    "studio.website_settings"
                )
            )

        # Persist the new media.

        try:

            branding = get_or_create_branding(
                account
            )

            old_public_id = getattr(
                branding,
                f"{kind}_public_id",
            )

            setattr(
                branding,
                f"{kind}_url",
                new_url,
            )

            setattr(
                branding,
                f"{kind}_public_id",
                new_public_id,
            )

            db.session.commit()

        except Exception:

            db.session.rollback()

            current_app.logger.exception(
                "Failed saving branding media "
                "for creator %s",
                account.id,
            )

            try:
                delete_media(
                    new_public_id,
                    resource_type="image",
                )
            except Exception:
                current_app.logger.exception(
                    "Failed cleaning up "
                    "uncommitted branding upload"
                )

            flash(
                "Image could not be saved.",
                "error",
            )

            return redirect(
                url_for(
                    "studio.website_settings"
                )
            )

        # Only delete the previous image after
        # the database commit succeeds.

        if (
            old_public_id
            and old_public_id != new_public_id
        ):

            try:

                delete_media(
                    old_public_id,
                    resource_type="image",
                )

            except Exception:

                current_app.logger.exception(
                    "Failed deleting previous "
                    "branding image"
                )

        flash(
            "Image updated.",
            "success",
        )

        return redirect(
            url_for(
                "studio.website_settings"
            )
        )

    # ========================================================
    # REMOVE BRANDING MEDIA
    # ========================================================

    @studio_bp.route(
        "/website/media/<kind>/remove",
        methods=["POST"],
        endpoint="website_media_remove",
    )
    @studio_required
    def website_media_remove(kind):

        account = current_creator_account()

        if not creator_has_feature(
            account,
            FEATURE_BRANDING,
        ):
            abort(403)

        if kind not in MEDIA_KINDS:
            abort(404)

        branding = (
            CreatorBranding.query
            .filter_by(
                creator_account_id=account.id
            )
            .first()
        )

        if branding is None:

            flash(
                "No branding image to remove.",
                "warning",
            )

            return redirect(
                url_for(
                    "studio.website_settings"
                )
            )

        old_public_id = getattr(
            branding,
            f"{kind}_public_id",
        )

        try:

            setattr(
                branding,
                f"{kind}_url",
                None,
            )

            setattr(
                branding,
                f"{kind}_public_id",
                None,
            )

            db.session.commit()

        except Exception:

            current_app.logger.exception(
                "Failed removing branding image "
                "for creator %s",
                account.id,
            )

            return save_error(
                "Unable to remove image."
            )

        if old_public_id:

            try:

                delete_media(
                    old_public_id,
                    resource_type="image",
                )

            except Exception:

                current_app.logger.exception(
                    "Failed deleting branding image "
                    "from Cloudinary"
                )

        flash(
            "Image removed.",
            "success",
        )

        return redirect(
            url_for(
                "studio.website_settings"
            )
        )

    # ========================================================
    # REGISTER CREATOR SUBDOMAIN
    # ========================================================

    @studio_bp.route(
        "/website/subdomain",
        methods=["POST"],
        endpoint="website_subdomain_create",
    )
    @studio_required
    def website_subdomain_create():

        account = current_creator_account()

        if not creator_has_feature(
            account,
            FEATURE_BRANDING,
        ):
            abort(403)

        hostname = (
            f"{account.username.lower()}"
            f"{DOMAIN_SUFFIX}"
        )

        existing = (
            CreatorDomain.query
            .filter_by(
                hostname=hostname
            )
            .first()
        )

        if (
            existing
            and existing.creator_account_id != account.id
        ):
            abort(409)

        now = utc_now()

        try:

            if existing is None:

                existing = CreatorDomain(
                    creator_account_id=account.id,
                    hostname=hostname,
                    domain_type="subdomain",
                    verification_status="verified",
                    verified_at=now,
                    is_active=False,
                    is_primary=False,
                )

                db.session.add(
                    existing
                )

            else:

                if existing.domain_type != "subdomain":
                    abort(409)

                existing.verification_status = (
                    "verified"
                )

                existing.verified_at = (
                    existing.verified_at or now
                )

            # A creator subdomain is only reserved here.
            # Do not claim it is live until DNS routing
            # and HTTPS/TLS are configured.

            db.session.commit()

        except IntegrityError:

            db.session.rollback()

            flash(
                "This subdomain is already registered.",
                "error",
            )

            return redirect(
                url_for(
                    "studio.website_settings"
                )
            )

        flash(
            "Creator subdomain reserved. "
            "It will become available after "
            "Kalxa configures domain routing and HTTPS.",
            "success",
        )

        return redirect(
            url_for(
                "studio.website_settings"
            )
        )

    # ========================================================
    # ADD CUSTOM DOMAIN
    # ========================================================

    @studio_bp.route(
        "/website/domains",
        methods=["POST"],
        endpoint="website_domain_add",
    )
    @studio_required
    def website_domain_add():

        account = current_creator_account()

        if not creator_has_feature(
            account,
            FEATURE_CUSTOM_DOMAIN,
        ):
            abort(403)

        raw = request.form.get(
            "hostname",
            "",
        ).strip().lower()

        # Require a hostname, not a full URL.

        if (
            "://" in raw
            or "/" in raw
            or "\\" in raw
            or ":" in raw
            or "@" in raw
        ):

            flash(
                "Enter a domain without https:// "
                "or a path.",
                "error",
            )

            return redirect(
                url_for(
                    "studio.website_settings"
                )
            )

        hostname = normalize_host(
            raw
        )

        if not valid_external_hostname(
            hostname
        ):

            flash(
                "Enter a valid external domain, "
                "such as www.example.co.za.",
                "error",
            )

            return redirect(
                url_for(
                    "studio.website_settings"
                )
            )

        existing = (
            CreatorDomain.query
            .filter_by(
                hostname=hostname
            )
            .first()
        )

        if existing:

            flash(
                "This domain is already registered.",
                "warning",
            )

            return redirect(
                url_for(
                    "studio.website_settings"
                )
            )

        domain = CreatorDomain(
            creator_account_id=account.id,
            hostname=hostname,
            domain_type="custom",
            verification_status="pending",
            verification_token=secrets.token_urlsafe(32),
            is_active=False,
            is_primary=False,
        )

        db.session.add(
            domain
        )

        try:

            db.session.commit()

        except IntegrityError:

            db.session.rollback()

            flash(
                "This domain is already claimed.",
                "error",
            )

            return redirect(
                url_for(
                    "studio.website_settings"
                )
            )

        flash(
            "Domain added. Create the DNS TXT "
            "record shown below, then verify ownership.",
            "success",
        )

        return redirect(
            url_for(
                "studio.website_settings"
            )
        )

    # ========================================================
    # VERIFY CUSTOM DOMAIN OWNERSHIP
    # ========================================================

    @studio_bp.route(
        "/website/domains/<int:domain_id>/verify",
        methods=["POST"],
        endpoint="website_domain_verify",
    )
    @studio_required
    def website_domain_verify(domain_id):

        account = current_creator_account()

        if not creator_has_feature(
            account,
            FEATURE_CUSTOM_DOMAIN,
        ):
            abort(403)

        domain = (
            CreatorDomain.query
            .filter_by(
                id=domain_id,
                creator_account_id=account.id,
                domain_type="custom",
            )
            .first_or_404()
        )

        if verify_domain_txt_record(
            domain
        ):

            try:

                domain.verification_status = (
                    "verified"
                )

                domain.verified_at = (
                    utc_now()
                )

                # DNS ownership is verified,
                # but HTTPS/routing are not.
                #
                # Do not automatically activate.

                db.session.commit()

            except Exception:

                return save_error(
                    "Unable to save domain verification."
                )

            flash(
                "Domain ownership verified. "
                "Your domain now awaits Kalxa "
                "DNS routing and HTTPS activation.",
                "success",
            )

        else:

            flash(
                "DNS TXT verification not found yet. "
                "Please check your DNS record and "
                "allow time for propagation.",
                "warning",
            )

        return redirect(
            url_for(
                "studio.website_settings"
            )
        )

    # ========================================================
    # REMOVE CUSTOM DOMAIN
    # ========================================================

    @studio_bp.route(
        "/website/domains/<int:domain_id>/remove",
        methods=["POST"],
        endpoint="website_domain_remove",
    )
    @studio_required
    def website_domain_remove(domain_id):

        account = current_creator_account()

        if not creator_has_feature(
            account,
            FEATURE_CUSTOM_DOMAIN,
        ):
            abort(403)

        domain = (
            CreatorDomain.query
            .filter_by(
                id=domain_id,
                creator_account_id=account.id,
                domain_type="custom",
            )
            .first_or_404()
        )

        try:

            db.session.delete(
                domain
            )

            db.session.commit()

        except Exception:

            current_app.logger.exception(
                "Failed removing custom domain %s "
                "for creator %s",
                domain_id,
                account.id,
            )

            return save_error(
                "Unable to disconnect custom domain."
            )

        flash(
            "Custom domain disconnected.",
            "success",
        )

        return redirect(
            url_for(
                "studio.website_settings"
            )
        )
