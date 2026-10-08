"""Attach website settings endpoints to the existing studio blueprint.
Import register_website_settings and call it before app.register_blueprint(studio_bp).
"""
import re
import secrets
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import CreatorBranding, CreatorDomain
from services.cloudinary_service import upload_image, validate_image, delete_media
from services.plan_service import (
    FEATURE_BRANDING, FEATURE_ADVANCED_BRANDING, FEATURE_CUSTOM_DOMAIN,
    creator_has_feature, creator_plan_summary,
)
from services.hostname_resolver import normalize_host

HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')
VALID_THEMES = {'light', 'dark'}
VALID_FONTS = {'system', 'sans', 'serif', 'mono'}
DOMAIN_SUFFIX = '.creators.kalxa.co.za'


def register_website_settings(studio_bp, studio_required, current_creator_account):
    """Register once before registering studio_bp on the Flask app."""

    def settings_context(account):
        branding = CreatorBranding.query.filter_by(creator_account_id=account.id).first()
        domains = CreatorDomain.query.filter_by(creator_account_id=account.id).order_by(CreatorDomain.created_at.asc()).all()
        return dict(creator_account=account, branding=branding, domains=domains,
                    plan_summary=creator_plan_summary(account),
                    expected_subdomain=f'{account.username.lower()}{DOMAIN_SUFFIX}',
                    verification_prefix='_kalxa-verification')

    def settings_page(account):
        return render_template('studio/website_settings.html', **settings_context(account))

    def get_or_create_branding(account):
        branding = CreatorBranding.query.filter_by(creator_account_id=account.id).first()
        if branding is None:
            branding = CreatorBranding(creator_account_id=account.id)
            db.session.add(branding)
        return branding

    @studio_bp.route('/website', methods=['GET'], endpoint='website_settings')
    @studio_required
    def website_settings():
        account = current_creator_account()
        if not creator_has_feature(account, FEATURE_BRANDING):
            abort(403)
        return settings_page(account)

    @studio_bp.route('/website/branding', methods=['POST'], endpoint='website_branding_save')
    @studio_required
    def website_branding_save():
        account = current_creator_account()
        if not creator_has_feature(account, FEATURE_BRANDING):
            abort(403)
        branding = get_or_create_branding(account)
        site_title = request.form.get('site_title', '').strip()
        tagline = request.form.get('site_tagline', '').strip()
        if len(site_title) > 120 or len(tagline) > 255:
            flash('Website title or tagline is too long.', 'error')
            return redirect(url_for('studio.website_settings'))
        branding.site_title = site_title or None
        branding.site_tagline = tagline or None
        for field in ('primary_color', 'accent_color'):
            color = request.form.get(field, '').strip()
            if not HEX_COLOR.fullmatch(color):
                flash(f'Invalid {field.replace("_", " ")}.', 'error')
                db.session.rollback()
                return redirect(url_for('studio.website_settings'))
            setattr(branding, field, color.upper())
        if creator_has_feature(account, FEATURE_ADVANCED_BRANDING):
            for field in ('background_color', 'text_color'):
                color = request.form.get(field, '').strip()
                if not HEX_COLOR.fullmatch(color):
                    flash(f'Invalid {field.replace("_", " ")}.', 'error')
                    db.session.rollback()
                    return redirect(url_for('studio.website_settings'))
                setattr(branding, field, color.upper())
            theme = request.form.get('theme', 'light')
            font = request.form.get('font_family', 'system')
            footer = request.form.get('footer_text', '').strip()
            if theme not in VALID_THEMES or font not in VALID_FONTS or len(footer) > 255:
                flash('Invalid advanced branding settings.', 'error')
                db.session.rollback()
                return redirect(url_for('studio.website_settings'))
            branding.theme = theme
            branding.font_family = font
            branding.footer_text = footer or None
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Failed saving creator branding')
            flash('Unable to save website settings.', 'error')
        else:
            flash('Website branding saved.', 'success')
        return redirect(url_for('studio.website_settings'))

    @studio_bp.route('/website/media/<kind>', methods=['POST'], endpoint='website_media_upload')
    @studio_required
    def website_media_upload(kind):
        account = current_creator_account()
        if not creator_has_feature(account, FEATURE_BRANDING):
            abort(403)
        if kind not in {'logo', 'favicon', 'cover_image'}:
            abort(404)
        file = request.files.get('image')
        if not file or not file.filename:
            flash('Select an image.', 'error')
            return redirect(url_for('studio.website_settings'))
        valid, error = validate_image(file)
        if not valid:
            flash(error, 'error')
            return redirect(url_for('studio.website_settings'))
        try:
            root = current_app.config.get('CLOUDINARY_FOLDER', 'creator-blog')
            result = upload_image(file, folder=f'{root}/creators/{account.id}/branding/{kind}')
        except Exception:
            current_app.logger.exception('Branding media upload failed')
            flash('Image upload failed.', 'error')
            return redirect(url_for('studio.website_settings'))
        branding = get_or_create_branding(account)
        old_id = getattr(branding, f'{kind}_public_id')
        setattr(branding, f'{kind}_url', result['url'])
        setattr(branding, f'{kind}_public_id', result['public_id'])
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            try:
                delete_media(result['public_id'], resource_type='image')
            except Exception:
                current_app.logger.exception('Failed cleaning up uncommitted branding upload')
            flash('Image could not be saved.', 'error')
            return redirect(url_for('studio.website_settings'))
        if old_id and old_id != result['public_id']:
            try:
                delete_media(old_id, resource_type='image')
            except Exception:
                current_app.logger.exception('Failed deleting previous branding image')
        flash('Image updated.', 'success')
        return redirect(url_for('studio.website_settings'))

    @studio_bp.route('/website/media/<kind>/remove', methods=['POST'], endpoint='website_media_remove')
    @studio_required
    def website_media_remove(kind):
        account = current_creator_account()
        if not creator_has_feature(account, FEATURE_BRANDING):
            abort(403)
        if kind not in {'logo', 'favicon', 'cover_image'}:
            abort(404)
        branding = CreatorBranding.query.filter_by(creator_account_id=account.id).first()
        if branding:
            old_id = getattr(branding, f'{kind}_public_id')
            setattr(branding, f'{kind}_url', None)
            setattr(branding, f'{kind}_public_id', None)
            db.session.commit()
            if old_id:
                try:
                    delete_media(old_id, resource_type='image')
                except Exception:
                    current_app.logger.exception('Failed deleting branding image')
        flash('Image removed.', 'success')
        return redirect(url_for('studio.website_settings'))

    @studio_bp.route('/website/subdomain', methods=['POST'], endpoint='website_subdomain_create')
    @studio_required
    def website_subdomain_create():
        account = current_creator_account()
        hostname = f'{account.username.lower()}{DOMAIN_SUFFIX}'
        existing = CreatorDomain.query.filter_by(hostname=hostname).first()
        if existing and existing.creator_account_id != account.id:
            abort(409)
        if not existing:
            # DNS wildcard and TLS must be configured at infrastructure level.
            existing = CreatorDomain(creator_account_id=account.id, hostname=hostname,
                                     domain_type='subdomain', verification_status='verified',
                                     verified_at=datetime.now(timezone.utc), is_active=True,
                                     activated_at=datetime.now(timezone.utc), is_primary=True)
            db.session.add(existing)
        else:
            existing.verification_status = 'verified'
            existing.verified_at = existing.verified_at or datetime.now(timezone.utc)
            existing.is_active = True
            existing.activated_at = existing.activated_at or datetime.now(timezone.utc)
        try:
            db.session.commit()
            flash('Creator subdomain registered. It will work after wildcard DNS and TLS are configured.', 'success')
        except IntegrityError:
            db.session.rollback()
            flash('This subdomain is already registered.', 'error')
        return redirect(url_for('studio.website_settings'))

    @studio_bp.route('/website/domains', methods=['POST'], endpoint='website_domain_add')
    @studio_required
    def website_domain_add():
        account = current_creator_account()
        if not creator_has_feature(account, FEATURE_CUSTOM_DOMAIN):
            abort(403)
        raw = request.form.get('hostname', '').strip().lower()
        hostname = normalize_host(raw)
        if (not hostname or ':' in raw or '/' in raw or hostname.endswith(DOMAIN_SUFFIX)
                or hostname in {'kalxa.co.za', 'creators.kalxa.co.za'}
                or hostname.endswith('.kalxa.co.za') or '.' not in hostname
                or hostname.replace('.', '').isdigit()):
            flash('Enter a valid external domain, e.g. www.example.co.za (without https://).', 'error')
            return redirect(url_for('studio.website_settings'))
        existing = CreatorDomain.query.filter_by(hostname=hostname).first()
        if existing:
            flash('This domain is already registered.', 'warning')
            return redirect(url_for('studio.website_settings'))
        domain = CreatorDomain(creator_account_id=account.id, hostname=hostname,
                               domain_type='custom', verification_status='pending',
                               verification_token=secrets.token_urlsafe(32),
                               is_active=False, is_primary=False)
        db.session.add(domain)
        try:
            db.session.commit()
            flash('Domain added. Create the DNS TXT record shown below, then verify.', 'success')
        except IntegrityError:
            db.session.rollback()
            flash('Domain already claimed.', 'error')
        return redirect(url_for('studio.website_settings'))

    @studio_bp.route('/website/domains/<int:domain_id>/verify', methods=['POST'], endpoint='website_domain_verify')
    @studio_required
    def website_domain_verify(domain_id):
        account = current_creator_account()
        if not creator_has_feature(account, FEATURE_CUSTOM_DOMAIN):
            abort(403)
        domain = CreatorDomain.query.filter_by(id=domain_id, creator_account_id=account.id,
                                               domain_type='custom').first_or_404()
        try:
            import dns.resolver
            name = f'_kalxa-verification.{domain.hostname}'
            answers = dns.resolver.resolve(name, 'TXT', lifetime=5)
            verified = any(str(domain.verification_token) == b''.join(answer.strings).decode('utf-8')
                           for answer in answers)
        except Exception:
            verified = False
        if not verified:
            flash('DNS TXT verification not found yet. DNS propagation can take time.', 'warning')
        else:
            domain.verification_status = 'verified'
            domain.verified_at = datetime.now(timezone.utc)
            # Deliberately NOT activated: hosting provider must provision DNS target + TLS.
            db.session.commit()
            flash('Ownership verified. Domain awaits platform DNS/TLS activation.', 'success')
        return redirect(url_for('studio.website_settings'))

    @studio_bp.route('/website/domains/<int:domain_id>/remove', methods=['POST'], endpoint='website_domain_remove')
    @studio_required
    def website_domain_remove(domain_id):
        account = current_creator_account()
        domain = CreatorDomain.query.filter_by(id=domain_id, creator_account_id=account.id,
                                               domain_type='custom').first_or_404()
        db.session.delete(domain)
        db.session.commit()
        flash('Custom domain disconnected.', 'success')
        return redirect(url_for('studio.website_settings'))
