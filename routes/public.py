"""Kalxa Creator public routes: tenant-safe websites, content, comments and newsletters.

Exclusive posts fail closed until a verified, active email membership session exists.
"""
import re
import secrets
import time
from datetime import datetime, timezone

from flask import (Blueprint, abort, current_app, flash, g, redirect,
                   render_template, request, session, url_for)
from extensions import db
from models import (CreatorAccount, CreatorProfile, CreatorBranding, ContentCategory,
                    ContentPost, ContentMedia, Comment, EmailSubscriber, utc_now)
from services.email_service import send_verification_email, send_welcome_email

public_bp = Blueprint('public', __name__)
COMMENT_MAX_LENGTH = 1500
AUTHOR_MAX_LENGTH = 80
COMMENT_COOLDOWN_SECONDS = 8
BRANDING_DEFAULTS = {
    'primary_color': '#111318', 'accent_color': '#F4B942',
    'background_color': '#FFFFFF', 'text_color': '#17191D',
    'theme': 'light', 'font_family': 'system',
}


def hosted_account():
    return getattr(g, 'creator_domain_account', None)


def get_current_creator():
    account = hosted_account()
    return (CreatorProfile.query.filter_by(creator_account_id=account.id).first()
            if account is not None else None)


def get_current_creator_account_id():
    account = hosted_account()
    return account.id if account else None


def get_public_creator_account(username):
    username = str(username or '').strip().lower()
    if not username:
        abort(404)
    hosted = hosted_account()
    if hosted and str(hosted.username or '').lower() != username:
        abort(404)
    account = CreatorAccount.query.filter(
        db.func.lower(CreatorAccount.username) == username,
        CreatorAccount.account_status == 'active',
    ).first()
    if account is None:
        abort(404)
    return account


def get_public_creator_profile(account):
    if account is None:
        abort(404)
    return CreatorProfile.query.filter_by(creator_account_id=account.id).first_or_404()


def creator_home_url(account):
    hosted = hosted_account()
    if hosted is not None and hosted.id == account.id:
        return url_for('public.home')
    return url_for('public.creator_home', username=account.username)


def creator_content_url(account, post):
    hosted = hosted_account()
    if hosted is not None and hosted.id == account.id:
        return url_for('public.content_detail', slug=post.slug)
    return url_for('public.creator_content_detail', username=account.username, slug=post.slug)


def public_branding_context(creator, account_id):
    account = db.session.get(CreatorAccount, account_id) if account_id is not None else None
    branding = (CreatorBranding.query.filter_by(creator_account_id=account_id).first()
                if account else None)
    premium = bool(account and (account.plan or '').lower() == 'premium'
                   and account.account_status == 'active'
                   and account.payment_status == 'paid'
                   and account.registration_paid_at is not None)

    def color(field):
        value = getattr(branding, field, None) if branding else None
        if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            return value
        return BRANDING_DEFAULTS[field]

    theme = getattr(branding, 'theme', 'light') if premium and branding else 'light'
    if theme not in {'light', 'dark'}:
        theme = 'light'
    font = getattr(branding, 'font_family', 'system') if premium and branding else 'system'
    if font not in {'system', 'sans', 'serif', 'mono'}:
        font = 'system'
    return {
        'creator_account': account,
        'branding': branding,
        'site_brand': {
            'title': (getattr(branding, 'site_title', None) if branding else None) or creator.display_name,
            'tagline': (getattr(branding, 'site_tagline', None) if branding else None) or (creator.tagline or ''),
            'logo_url': getattr(branding, 'logo_url', None) if branding else None,
            'favicon_url': getattr(branding, 'favicon_url', None) if branding else None,
            'cover_image_url': getattr(branding, 'cover_image_url', None) if branding else None,
            'primary_color': color('primary_color'),
            'accent_color': color('accent_color'),
            'background_color': color('background_color') if premium else BRANDING_DEFAULTS['background_color'],
            'text_color': color('text_color') if premium else BRANDING_DEFAULTS['text_color'],
            'theme': theme,
            'font_family': font,
            'footer_text': getattr(branding, 'footer_text', None) if premium and branding else None,
            'show_platform_branding': not premium,
        },
    }


def creator_has_memberships(account):
    """Paid-plan eligibility. Never grant access from plan alone."""
    return bool(account and account.account_status == 'active'
                and account.plan in ('standard', 'premium')
                and account.payment_status == 'paid'
                and account.registration_paid_at is not None)


def membership_join_url(account):
    """Use only a registered membership endpoint; don't invent one."""
    candidates = ('membership.membership_join', 'membership.join',
                  'membership.creator_membership', 'membership_bp.membership_join')
    for endpoint in candidates:
        if endpoint in current_app.view_functions:
            try:
                return url_for(endpoint, username=account.username)
            except Exception:
                continue
    return None


def has_active_membership(creator_account_id):
    """Fail closed unless email magic-link authentication is established.

    The magic-link handler must set BOTH session keys after validating a
    single-use token sent to the subscriber's email address. Merely typing
    an email in a form must never set these values.
    """
    subscriber_id = session.get('membership_subscriber_id')
    if type(subscriber_id) is not int or not session.get('membership_email_verified'):
        return False
    try:
        from membership_models import CreatorMembership, MembershipSubscriber
    except ImportError:
        current_app.logger.error('Membership models are not installed; exclusive access denied')
        return False
    subscriber = db.session.get(MembershipSubscriber, subscriber_id)
    if subscriber is None:
        return False
    membership = CreatorMembership.query.filter_by(
        subscriber_id=subscriber.id, creator_account_id=creator_account_id,
        status='active',
    ).first()
    if membership is None or membership.current_period_end is None:
        return False
    expires = membership.current_period_end
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires.astimezone(timezone.utc) > datetime.now(timezone.utc)


def is_exclusive(post):
    return post.access_level in ('subscriber', 'exclusive')


def can_view_post(post):
    if not is_exclusive(post):
        return True
    creator = db.session.get(CreatorAccount, post.creator_account_id)
    return creator_has_memberships(creator) and has_active_membership(post.creator_account_id)


def require_post_access(post):
    """Never load/render protected media for an unauthorized visitor."""
    if not can_view_post(post):
        abort(403, description='An active, email-verified membership is required to view this content.')


def get_anonymous_session_id():
    anonymous_id = session.get('anonymous_session_id')
    if not anonymous_id:
        anonymous_id = secrets.token_urlsafe(24)
        session['anonymous_session_id'] = anonymous_id
    return anonymous_id


def comment_rate_limited():
    now = time.time()
    previous = session.get('last_comment_time')
    if previous and now - previous < COMMENT_COOLDOWN_SECONDS:
        return True
    session['last_comment_time'] = now
    return False


def render_creator_home(creator, creator_account_id, public_username=None):
    if creator is None or creator_account_id is None:
        abort(404)
    account = db.session.get(CreatorAccount, creator_account_id)
    categories = ContentCategory.query.filter_by(
        creator_account_id=creator_account_id, is_active=True,
    ).order_by(ContentCategory.display_order.asc(), ContentCategory.name.asc()).all()
    posts = ContentPost.query.filter_by(
        creator_account_id=creator_account_id, status='published',
    ).order_by(ContentPost.published_at.desc(), ContentPost.created_at.desc()).limit(12).all()
    return render_template(
        'public/home.html', creator=creator, categories=categories,
        posts=posts, public_username=public_username,
        membership_enabled=creator_has_memberships(account),
        membership_join_url=membership_join_url(account) if creator_has_memberships(account) else None,
        member_has_access=has_active_membership(creator_account_id),
        **public_branding_context(creator, creator_account_id),
    )


def render_content_detail(creator, post, public_username=None):
    if creator is None or post is None or creator.creator_account_id != post.creator_account_id:
        abort(404)
    require_post_access(post)
    gallery_images = ContentMedia.query.filter_by(
        post_id=post.id, media_type='gallery_image',
    ).order_by(ContentMedia.media_order.asc()).all()
    video = ContentMedia.query.filter_by(post_id=post.id, media_type='video').first()
    comments = Comment.query.filter_by(
        post_id=post.id, parent_id=None, status='approved',
    ).order_by(Comment.created_at.desc()).all()
    comment_count = Comment.query.filter_by(post_id=post.id, status='approved').count()
    return render_template(
        'public/content_detail.html', creator=creator, post=post,
        gallery_images=gallery_images, video=video, comments=comments,
        comment_count=comment_count, public_username=public_username,
        member_has_access=has_active_membership(post.creator_account_id),
        **public_branding_context(creator, post.creator_account_id),
    )


@public_bp.route('/')
def home():
    account = hosted_account()
    if account is not None:
        if account.account_status != 'active':
            abort(404)
        return render_creator_home(get_public_creator_profile(account), account.id)
    return render_template('public/platform_home.html', platform_name='Kalxa Creator', plans={
        'free': {'name': 'Free', 'price': 0, 'commission': 25, 'billing': 'forever'},
        'standard': {'name': 'Standard', 'price': 300, 'commission': 8, 'billing': 'once-off'},
        'premium': {'name': 'Premium', 'price': 500, 'commission': 5, 'billing': 'once-off'},
    })


@public_bp.route('/@<string:username>')
def creator_home(username):
    account = get_public_creator_account(username)
    return render_creator_home(
        get_public_creator_profile(account), account.id,
        public_username=None if hosted_account() else account.username,
    )


@public_bp.route('/content/<string:slug>')
def content_detail(slug):
    account = hosted_account()
    if account is None or account.account_status != 'active':
        abort(404)
    post = ContentPost.query.filter_by(
        creator_account_id=account.id, slug=slug, status='published',
    ).first_or_404()
    return render_content_detail(get_public_creator_profile(account), post)


@public_bp.route('/@<string:username>/content/<string:slug>')
def creator_content_detail(username, slug):
    account = get_public_creator_account(username)
    post = ContentPost.query.filter_by(
        creator_account_id=account.id, slug=slug, status='published',
    ).first_or_404()
    return render_content_detail(
        get_public_creator_profile(account), post,
        public_username=None if hosted_account() else account.username,
    )


def post_comment_redirect(post, *, comment_id=None):
    account = db.session.get(CreatorAccount, post.creator_account_id)
    anchor = f'#comment-{comment_id}' if comment_id else '#comments'
    return redirect(creator_content_url(account, post) + anchor)


@public_bp.route('/content/<int:post_id>/comments', methods=['POST'])
def add_comment(post_id):
    account = hosted_account()
    if account is None or account.account_status != 'active':
        abort(404)
    post = ContentPost.query.filter_by(
        id=post_id, creator_account_id=account.id, status='published',
    ).first_or_404()
    require_post_access(post)
    return process_comment(post, 'public.content_detail', {'slug': post.slug})


@public_bp.route('/@<string:username>/content/<int:post_id>/comments', methods=['POST'])
def creator_add_comment(username, post_id):
    account = get_public_creator_account(username)
    post = ContentPost.query.filter_by(
        id=post_id, creator_account_id=account.id, status='published',
    ).first_or_404()
    require_post_access(post)
    endpoint = 'public.content_detail' if hosted_account() else 'public.creator_content_detail'
    values = {'slug': post.slug}
    if not hosted_account():
        values['username'] = account.username
    return process_comment(post, endpoint, values)


def process_comment(post, redirect_endpoint, redirect_values):
    def back():
        return redirect(url_for(redirect_endpoint, **redirect_values) + '#comments')
    if request.form.get('website', '').strip():
        return back()
    if comment_rate_limited():
        flash('Please wait a few seconds before posting another comment.', 'warning')
        return back()
    name = request.form.get('author_name', '').strip()
    body = request.form.get('body', '').strip()
    if not name or len(name) > AUTHOR_MAX_LENGTH:
        flash('Enter a valid name (up to 80 characters).', 'error')
        return back()
    if not body or len(body) > COMMENT_MAX_LENGTH:
        flash('Write a comment (up to 1500 characters).', 'error')
        return back()
    db.session.add(Comment(
        post_id=post.id, author_name=name, body=body, status='approved',
        is_creator=False, anonymous_session_id=get_anonymous_session_id(),
    ))
    db.session.commit()
    flash('Your comment was posted.', 'success')
    return back()


@public_bp.route('/comments/<int:comment_id>/reply', methods=['POST'])
def add_reply(comment_id):
    account = hosted_account()
    if account is None or account.account_status != 'active':
        abort(404)
    parent = Comment.query.join(ContentPost, Comment.post_id == ContentPost.id).filter(
        Comment.id == comment_id, ContentPost.creator_account_id == account.id,
        ContentPost.status == 'published',
    ).first_or_404()
    require_post_access(parent.post)
    return process_reply(parent, parent.post, 'public.content_detail', {'slug': parent.post.slug})


@public_bp.route('/@<string:username>/comments/<int:comment_id>/reply', methods=['POST'])
def creator_add_reply(username, comment_id):
    account = get_public_creator_account(username)
    parent = Comment.query.join(ContentPost, Comment.post_id == ContentPost.id).filter(
        Comment.id == comment_id, ContentPost.creator_account_id == account.id,
        ContentPost.status == 'published',
    ).first_or_404()
    require_post_access(parent.post)
    endpoint = 'public.content_detail' if hosted_account() else 'public.creator_content_detail'
    values = {'slug': parent.post.slug}
    if not hosted_account():
        values['username'] = account.username
    return process_reply(parent, parent.post, endpoint, values)


def process_reply(parent, post, redirect_endpoint, redirect_values):
    if parent.parent_id is not None:
        abort(400)
    if parent.status != 'approved':
        abort(404)

    def back():
        return redirect(url_for(redirect_endpoint, **redirect_values) + f'#comment-{parent.id}')

    if request.form.get('website', '').strip():
        return back()
    if comment_rate_limited():
        flash('Please wait a few seconds before posting another reply.', 'warning')
        return back()
    name = request.form.get('author_name', '').strip()
    body = request.form.get('body', '').strip()
    if not name or len(name) > AUTHOR_MAX_LENGTH:
        flash('Enter a valid name (up to 80 characters).', 'error')
        return back()
    if not body or len(body) > COMMENT_MAX_LENGTH:
        flash('Write a reply (up to 1500 characters).', 'error')
        return back()
    db.session.add(Comment(
        post_id=post.id, parent_id=parent.id, author_name=name, body=body,
        status='approved', is_creator=False,
        anonymous_session_id=get_anonymous_session_id(),
    ))
    db.session.commit()
    flash('Your reply was posted.', 'success')
    return back()


@public_bp.route('/newsletter/subscribe', methods=['POST'])
def newsletter_subscribe():
    account = hosted_account()
    if account is None or account.account_status != 'active':
        abort(404)
    return process_newsletter_subscription(account.id, 'public.home', {})


@public_bp.route('/@<string:username>/newsletter/subscribe', methods=['POST'])
def creator_newsletter_subscribe(username):
    account = get_public_creator_account(username)
    endpoint = 'public.home' if hosted_account() else 'public.creator_home'
    values = {} if hosted_account() else {'username': account.username}
    return process_newsletter_subscription(account.id, endpoint, values)


def process_newsletter_subscription(creator_account_id, redirect_endpoint, redirect_values):
    def back():
        return redirect(url_for(redirect_endpoint, **redirect_values) + '#newsletter')
    if request.form.get('website', '').strip():
        return back()
    email = request.form.get('email', '').strip().lower()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email) or len(email) > 255:
        flash('Enter a valid email address.', 'error')
        return back()
    subscriber = EmailSubscriber.query.filter_by(
        creator_account_id=creator_account_id, email=email,
    ).first()
    if subscriber is not None and subscriber.status == 'active':
        flash("You're already subscribed.", 'success')
        return back()
    verification_token = secrets.token_urlsafe(48)
    unsubscribe_token = secrets.token_urlsafe(48)
    if subscriber is not None:
        subscriber.status = 'pending'
        subscriber.verification_token = verification_token
        if not subscriber.unsubscribe_token:
            subscriber.unsubscribe_token = unsubscribe_token
        subscriber.verified_at = None
        subscriber.unsubscribed_at = None
    else:
        subscriber = EmailSubscriber(
            creator_account_id=creator_account_id, email=email, status='pending',
            verification_token=verification_token, unsubscribe_token=unsubscribe_token,
        )
        db.session.add(subscriber)
    db.session.commit()
    if send_verification_email(subscriber):
        flash('Check your inbox and confirm your email to finish subscribing.', 'success')
    else:
        flash('Your email was saved, but the verification email could not be sent. Please try again shortly.', 'error')
    return back()


@public_bp.route('/newsletter/verify/<string:token>')
def newsletter_verify(token):
    subscriber = EmailSubscriber.query.filter_by(verification_token=token).first()
    if subscriber is None:
        return render_template('public/newsletter_message.html', title='Invalid link',
                               heading="This link isn't valid.",
                               message='The verification link may have expired or already been used.'), 404
    if subscriber.creator_account_id is None:
        return render_template('public/newsletter_message.html', title='Subscription unavailable',
                               heading="We couldn't confirm this subscription.",
                               message='This subscription is not connected to a creator account.'), 400
    account = db.session.get(CreatorAccount, subscriber.creator_account_id)
    if account is None:
        abort(404)
    hosted = hosted_account()
    if hosted is not None and hosted.id != account.id:
        abort(404)
    subscriber.status = 'active'
    subscriber.verified_at = utc_now()
    subscriber.unsubscribed_at = None
    subscriber.verification_token = None
    db.session.commit()
    send_welcome_email(subscriber)
    creator = get_public_creator_profile(account)
    return render_template(
        'public/newsletter_message.html', title='Subscription confirmed',
        heading="You're in.",
        message="Your email is confirmed. You'll now receive updates when new content is published.",
        creator_username=account.username,
        **public_branding_context(creator, account.id),
    )


@public_bp.route('/newsletter/unsubscribe/<string:token>')
def newsletter_unsubscribe(token):
    subscriber = EmailSubscriber.query.filter_by(unsubscribe_token=token).first()
    if subscriber is None:
        return render_template('public/newsletter_message.html', title='Invalid link',
                               heading="This link isn't valid.",
                               message="We couldn't find a subscription for this unsubscribe link."), 404
    hosted = hosted_account()
    if hosted is not None and hosted.id != subscriber.creator_account_id:
        abort(404)
    subscriber.status = 'unsubscribed'
    subscriber.unsubscribed_at = utc_now()
    subscriber.verification_token = None
    db.session.commit()
    account = (db.session.get(CreatorAccount, subscriber.creator_account_id)
               if subscriber.creator_account_id else None)
    branding_context = {}
    if account is not None:
        creator = get_public_creator_profile(account)
        branding_context = public_branding_context(creator, account.id)
    return render_template(
        'public/newsletter_message.html', title='Unsubscribed',
        heading="You've been unsubscribed.",
        message="You won't receive new-post emails from this creator anymore. You can subscribe again from their website at any time.",
        creator_username=account.username if account else None,
        **branding_context,
    )
