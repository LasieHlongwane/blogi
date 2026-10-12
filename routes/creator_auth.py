"""Creator registration/login for one-time activation plans.

Free creators enter Studio immediately; paid plans require verified Yoco
activation. Existing legacy pending accounts retain their approval state.
"""
import re
from functools import wraps
from sqlalchemy.exc import IntegrityError
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from extensions import db
from models import CreatorAccount, CreatorProfile, utc_now

creator_auth_bp = Blueprint('creator_auth', __name__, url_prefix='/creator')
PLAN_PRICES = {'free': 0, 'standard': 100, 'premium': 150}
VALID_PLANS = frozenset(PLAN_PRICES)


def normalize_username(value):
    return re.sub(r'[^a-z0-9_]+', '', str(value or '').strip().lower())


def get_logged_in_creator():
    creator_id = session.get('creator_account_id')
    return db.session.get(CreatorAccount, creator_id) if creator_id else None


def refresh_creator_subscription(creator):
    """Compatibility shim: no expiry enforcement for one-time plans."""
    return getattr(creator, 'platform_subscription', None)


def creator_can_enter_studio(creator):
    if not creator or creator.account_status != 'active':
        return False
    if creator.plan == 'free':
        return True
    return bool(creator.plan in ('standard', 'premium')
                and creator.payment_status == 'paid'
                and creator.registration_paid_at is not None)


def creator_login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        creator = get_logged_in_creator()
        if creator is None:
            session.pop('creator_account_id', None)
            flash('Please sign in to continue.', 'warning')
            return redirect(url_for('creator_auth.login'))
        return view(*args, **kwargs)
    return wrapped_view


def _register_page(selected_plan):
    return render_template('creator/register.html', selected_plan=selected_plan,
                           plan_prices=PLAN_PRICES)


@creator_auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    existing = get_logged_in_creator()
    if existing:
        return redirect(url_for('studio.dashboard') if creator_can_enter_studio(existing)
                        else url_for('creator_auth.pending'))

    selected_plan = str(request.values.get('plan') or 'free').strip().lower()
    if selected_plan not in VALID_PLANS:
        selected_plan = 'free'
    if request.method == 'GET':
        return _register_page(selected_plan)

    display_name = str(request.form.get('display_name') or '').strip()
    username = normalize_username(request.form.get('username'))
    email = str(request.form.get('email') or '').strip().lower()
    password = request.form.get('password') or ''
    confirmation = request.form.get('confirm_password') or ''
    if not (1 <= len(display_name) <= 120):
        flash('Enter a display name of up to 120 characters.', 'error')
    elif not (3 <= len(username) <= 80):
        flash('Username must be 3–80 letters, digits or underscores.', 'error')
    elif len(email) > 255 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        flash('Enter a valid email address.', 'error')
    elif len(password) < 8:
        flash('Password must contain at least 8 characters.', 'error')
    elif password != confirmation:
        flash('Passwords do not match.', 'error')
    elif (CreatorAccount.query.filter(db.func.lower(CreatorAccount.username) == username).first()
          or CreatorProfile.query.filter(db.func.lower(CreatorProfile.username) == username).first()):
        flash('That username is already taken.', 'error')
    elif CreatorAccount.query.filter(db.func.lower(CreatorAccount.email) == email).first():
        flash('An account already exists for that email address.', 'error')
    else:
        # A requested paid plan is an INTENT, not an entitlement. Persist
        # free until the Yoco webhook confirms the paid activation.
        creator = CreatorAccount(username=username, email=email, plan='free',
                                 account_status='active', payment_status='unpaid',
                                 subscription_status='inactive')
        creator.set_password(password)
        try:
            db.session.add(creator)
            db.session.flush()
            db.session.add(CreatorProfile(creator_account_id=creator.id,
                                          display_name=display_name, username=username))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('That username or email is already registered.', 'error')
            return _register_page(selected_plan)
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Creator registration failed')
            flash('Registration is temporarily unavailable.', 'error')
            return _register_page(selected_plan)
        session.clear()
        session['creator_account_id'] = creator.id
        if selected_plan in ('standard', 'premium'):
            # Session hint only; payment route still validates plan and price.
            session['requested_creator_plan'] = selected_plan
            flash('Your free account is ready. Activate your selected paid plan when ready.', 'success')
            return redirect(url_for('creator_auth.pending'))
        flash('Your free creator account is ready.', 'success')
        return redirect(url_for('studio.dashboard'))
    return _register_page(selected_plan)


@creator_auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    existing = get_logged_in_creator()
    if existing:
        return redirect(url_for('studio.dashboard') if creator_can_enter_studio(existing)
                        else url_for('creator_auth.pending'))
    if request.method == 'GET':
        return render_template('creator/login.html')
    identity = str(request.form.get('identity') or '').strip().lower()
    password = request.form.get('password') or ''
    creator = (CreatorAccount.query.filter(db.or_(
        db.func.lower(CreatorAccount.username) == identity,
        db.func.lower(CreatorAccount.email) == identity)).first()) if identity else None
    if not creator or not password or not creator.check_password(password):
        flash('Invalid login details.', 'error')
        return render_template('creator/login.html')
    if creator.account_status in ('rejected', 'suspended'):
        flash('This account is not currently available.', 'error')
        return render_template('creator/login.html')
    session.clear()
    session['creator_account_id'] = creator.id
    creator.last_login_at = utc_now()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Could not record creator login')
    return redirect(url_for('studio.dashboard') if creator_can_enter_studio(creator)
                    else url_for('creator_auth.pending'))


@creator_auth_bp.route('/pending')
@creator_login_required
def pending():
    creator = get_logged_in_creator()
    subscription = refresh_creator_subscription(creator)
    plan = creator.plan if creator.plan in VALID_PLANS else 'free'
    requested_plan = session.get('requested_creator_plan')
    if requested_plan not in ('standard', 'premium'):
        requested_plan = None
    # Do not redirect free users automatically: this page doubles as the
    # plan activation screen for free users.
    public_url = (url_for('public.creator_home', username=creator.username)
                  if creator.account_status == 'active' else None)
    return render_template('creator/pending.html', creator_account=creator,
                           subscription=subscription,
                           subscription_status=creator.subscription_status or 'inactive',
                           grace_days_remaining=0, selected_plan=plan,
                           selected_plan_price=PLAN_PRICES[plan],
                           plan_prices=PLAN_PRICES,
                           requested_plan=requested_plan,
                           public_creator_url=public_url)


@creator_auth_bp.route('/logout', methods=['POST'])
@creator_login_required
def logout():
    session.clear()
    flash('You have been signed out.', 'success')
    return redirect(url_for('creator_auth.login'))
