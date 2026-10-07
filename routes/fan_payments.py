import re
import uuid

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    request,
    redirect,
    url_for,
    render_template,
    flash,
    current_app,
    jsonify,
    abort,
)

from extensions import db

from models import (
    CreatorAccount,
    CreatorProfile,
    CreatorPayoutAccount,
    FundraisingCampaign,
    FanPayment,
)

from services.plan_service import (
    FEATURE_FAN_SUPPORT,
    FEATURE_FUNDRAISING,
    creator_has_feature,
)

from services.paystack_service import (
    PaystackError,
    initialize_fan_payment,
    verify_transaction,
    verify_paystack_webhook,
)


fan_payments_bp = Blueprint(
    "fan_payments",
    __name__,
    url_prefix="/support",
)


# ============================================================
# HELPERS
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    )


def creator_by_username_or_404(
    username,
):

    return (
        CreatorAccount.query
        .filter(
            db.func.lower(
                CreatorAccount.username
            )
            == username.lower(),
            CreatorAccount.account_status
            == "active",
        )
        .first_or_404()
    )


def creator_profile_for(
    creator,
):

    return (
        CreatorProfile.query
        .filter_by(
            creator_account_id=creator.id
        )
        .first()
    )


def active_payout_account(
    creator,
):

    return (
        CreatorPayoutAccount.query
        .filter_by(
            creator_account_id=creator.id,
            provider="paystack",
            status="active",
        )
        .first()
    )


def creator_campaign_or_404(
    creator,
    slug,
):

    return (
        FundraisingCampaign.query
        .filter_by(
            creator_account_id=creator.id,
            slug=slug,
        )
        .first_or_404()
    )


def parse_amount_to_cents(
    value,
):

    value = (
        str(value or "")
        .strip()
        .replace(",", "")
    )

    try:

        amount = Decimal(value)

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):

        return None

    if amount <= 0:

        return None

    amount = amount.quantize(
        Decimal("0.01")
    )

    return int(
        amount * 100
    )


def valid_email(
    value,
):

    value = (
        str(value or "")
        .strip()
    )

    return bool(
        re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            value,
        )
    )


def new_payment_reference():

    return (
        "KALXA-FAN-"
        + uuid.uuid4().hex.upper()
    )


def get_metadata(
    data,
):

    metadata = (
        data.get("metadata")
        or {}
    )

    if isinstance(
        metadata,
        str,
    ):

        try:

            import json

            metadata = json.loads(
                metadata
            )

        except Exception:

            metadata = {}

    if not isinstance(
        metadata,
        dict,
    ):

        metadata = {}

    return metadata


# ============================================================
# CREATOR SUPPORT PAGE
# ============================================================

@fan_payments_bp.route(
    "/<username>"
)
def creator_support(
    username,
):

    creator = (
        creator_by_username_or_404(
            username
        )
    )

    if not creator_has_feature(
        creator,
        FEATURE_FAN_SUPPORT,
    ):

        abort(404)

    profile = (
        creator_profile_for(
            creator
        )
    )

    payout_account = (
        active_payout_account(
            creator
        )
    )

    return render_template(
        "public/support_creator.html",
        creator_account=creator,
        creator=profile,
        payout_ready=bool(
            payout_account
            and payout_account.provider_subaccount_code
        ),
    )


# ============================================================
# CREATE BUY-ME-A-COFFEE PAYMENT
# ============================================================

@fan_payments_bp.route(
    "/<username>/pay",
    methods=["POST"],
)
def creator_support_pay(
    username,
):

    creator = (
        creator_by_username_or_404(
            username
        )
    )

    if not creator_has_feature(
        creator,
        FEATURE_FAN_SUPPORT,
    ):

        abort(404)

    payout_account = (
        active_payout_account(
            creator
        )
    )

    if (
        not payout_account
        or not payout_account
        .provider_subaccount_code
    ):

        flash(
            (
                "This creator is not ready "
                "to receive payments yet."
            ),
            "warning",
        )

        return redirect(
            url_for(
                "fan_payments.creator_support",
                username=creator.username,
            )
        )

    amount_cents = (
        parse_amount_to_cents(
            request.form.get(
                "amount"
            )
        )
    )

    if amount_cents is None:

        flash(
            "Enter a valid support amount.",
            "error",
        )

        return redirect(
            url_for(
                "fan_payments.creator_support",
                username=creator.username,
            )
        )

    email = (
        request.form
        .get("email", "")
        .strip()
        .lower()
    )

    if not valid_email(
        email
    ):

        flash(
            (
                "Enter a valid email "
                "address for the payment."
            ),
            "error",
        )

        return redirect(
            url_for(
                "fan_payments.creator_support",
                username=creator.username,
            )
        )

    supporter_name = (
        request.form
        .get("name", "")
        .strip()
    )

    supporter_message = (
        request.form
        .get("message", "")
        .strip()
    )

    if len(supporter_name) > 120:

        supporter_name = (
            supporter_name[:120]
        )

    if len(supporter_message) > 500:

        supporter_message = (
            supporter_message[:500]
        )

    is_anonymous = (
        request.form.get(
            "is_anonymous"
        )
        == "on"
    )

    reference = (
        new_payment_reference()
    )

    payment = FanPayment(
        creator_account_id=creator.id,
        campaign_id=None,
        payment_type="support",
        supporter_name=(
            supporter_name
            or None
        ),
        supporter_email=email,
        supporter_message=(
            supporter_message
            or None
        ),
        is_anonymous=is_anonymous,
        amount_cents=amount_cents,
        currency="ZAR",
        platform_fee_cents=0,
        provider="paystack",
        provider_reference=reference,
        status="pending",
    )

    db.session.add(
        payment
    )

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to create FanPayment."
        )

        flash(
            (
                "Payment could not be "
                "started. Please try again."
            ),
            "error",
        )

        return redirect(
            url_for(
                "fan_payments.creator_support",
                username=creator.username,
            )
        )

    try:

        checkout = (
            initialize_fan_payment(
                email=email,
                amount_cents=(
                    payment.amount_cents
                ),
                reference=reference,
                subaccount_code=(
                    payout_account
                    .provider_subaccount_code
                ),
                callback_url=(
                    url_for(
                        "fan_payments.payment_return",
                        _external=True,
                    )
                ),
                metadata={
                    "product_type": (
                        "creator_support"
                    ),
                    "fan_payment_id": (
                        payment.id
                    ),
                    "creator_account_id": (
                        creator.id
                    ),
                    "creator_username": (
                        creator.username
                    ),
                    "payment_type": (
                        "support"
                    ),
                },
            )
        )

    except PaystackError:

        current_app.logger.exception(
            (
                "Paystack support checkout "
                "initialization failed. "
                "fan_payment_id=%s"
            ),
            payment.id,
        )

        flash(
            (
                "We could not open the "
                "payment page. Please try again."
            ),
            "error",
        )

        return redirect(
            url_for(
                "fan_payments.creator_support",
                username=creator.username,
            )
        )

    authorization_url = (
        checkout.get(
            "authorization_url"
        )
    )

    if not authorization_url:

        flash(
            (
                "The payment provider did "
                "not return a checkout page."
            ),
            "error",
        )

        return redirect(
            url_for(
                "fan_payments.creator_support",
                username=creator.username,
            )
        )

    return redirect(
        authorization_url
    )


# ============================================================
# PUBLIC CAMPAIGN PAGE
# ============================================================

@fan_payments_bp.route(
    "/<username>/campaigns/<slug>"
)
def campaign_detail(
    username,
    slug,
):

    creator = (
        creator_by_username_or_404(
            username
        )
    )

    if not creator_has_feature(
        creator,
        FEATURE_FUNDRAISING,
    ):

        abort(404)

    campaign = (
        creator_campaign_or_404(
            creator,
            slug,
        )
    )

    if campaign.status not in {
        "active",
        "completed",
    }:

        abort(404)

    raised_cents = int(
        db.session.query(
            db.func.coalesce(
                db.func.sum(
                    FanPayment.amount_cents
                ),
                0,
            )
        )
        .filter(
            FanPayment.creator_account_id
            == creator.id,
            FanPayment.campaign_id
            == campaign.id,
            FanPayment.payment_type
            == "campaign",
            FanPayment.status
            == "paid",
        )
        .scalar()
        or 0
    )

    supporter_count = (
        FanPayment.query
        .filter_by(
            creator_account_id=creator.id,
            campaign_id=campaign.id,
            payment_type="campaign",
            status="paid",
        )
        .count()
    )

    progress_percent = 0

    if campaign.goal_amount_cents:

        progress_percent = min(
            100,
            round(
                (
                    raised_cents
                    / campaign.goal_amount_cents
                )
                * 100,
                1,
            ),
        )

    payout_account = (
        active_payout_account(
            creator
        )
    )

    return render_template(
        "public/fundraising_campaign.html",
        creator_account=creator,
        creator=(
            creator_profile_for(
                creator
            )
        ),
        campaign=campaign,
        raised_cents=raised_cents,
        supporter_count=(
            supporter_count
        ),
        progress_percent=(
            progress_percent
        ),
        payout_ready=bool(
            payout_account
            and payout_account
            .provider_subaccount_code
        ),
    )


# ============================================================
# CAMPAIGN CONTRIBUTION
# ============================================================

@fan_payments_bp.route(
    "/<username>/campaigns/<slug>/pay",
    methods=["POST"],
)
def campaign_pay(
    username,
    slug,
):

    creator = (
        creator_by_username_or_404(
            username
        )
    )

    if not creator_has_feature(
        creator,
        FEATURE_FUNDRAISING,
    ):

        abort(404)

    campaign = (
        creator_campaign_or_404(
            creator,
            slug,
        )
    )

    if campaign.status != "active":

        flash(
            (
                "This campaign is not "
                "accepting contributions."
            ),
            "warning",
        )

        return redirect(
            url_for(
                "fan_payments.campaign_detail",
                username=creator.username,
                slug=campaign.slug,
            )
        )

    now = utc_now()

    if (
        campaign.starts_at
        and campaign.starts_at > now
    ):

        flash(
            (
                "This campaign has not "
                "started yet."
            ),
            "warning",
        )

        return redirect(
            url_for(
                "fan_payments.campaign_detail",
                username=creator.username,
                slug=campaign.slug,
            )
        )

    if (
        campaign.ends_at
        and campaign.ends_at < now
    ):

        flash(
            "This campaign has ended.",
            "warning",
        )

        return redirect(
            url_for(
                "fan_payments.campaign_detail",
                username=creator.username,
                slug=campaign.slug,
            )
        )

    payout_account = (
        active_payout_account(
            creator
        )
    )

    if (
        not payout_account
        or not payout_account
        .provider_subaccount_code
    ):

        flash(
            (
                "This campaign cannot "
                "receive payments yet."
            ),
            "warning",
        )

        return redirect(
            url_for(
                "fan_payments.campaign_detail",
                username=creator.username,
                slug=campaign.slug,
            )
        )

    amount_cents = (
        parse_amount_to_cents(
            request.form.get(
                "amount"
            )
        )
    )

    if amount_cents is None:

        flash(
            "Enter a valid contribution.",
            "error",
        )

        return redirect(
            url_for(
                "fan_payments.campaign_detail",
                username=creator.username,
                slug=campaign.slug,
            )
        )

    email = (
        request.form
        .get("email", "")
        .strip()
        .lower()
    )

    if not valid_email(
        email
    ):

        flash(
            "Enter a valid email address.",
            "error",
        )

        return redirect(
            url_for(
                "fan_payments.campaign_detail",
                username=creator.username,
                slug=campaign.slug,
            )
        )

    supporter_name = (
        request.form
        .get("name", "")
        .strip()
    )[:120]

    supporter_message = (
        request.form
        .get("message", "")
        .strip()
    )[:500]

    is_anonymous = (
        request.form.get(
            "is_anonymous"
        )
        == "on"
    )

    reference = (
        new_payment_reference()
    )

    payment = FanPayment(
        creator_account_id=creator.id,
        campaign_id=campaign.id,
        payment_type="campaign",
        supporter_name=(
            supporter_name
            or None
        ),
        supporter_email=email,
        supporter_message=(
            supporter_message
            or None
        ),
        is_anonymous=is_anonymous,
        amount_cents=amount_cents,
        currency="ZAR",
        platform_fee_cents=0,
        provider="paystack",
        provider_reference=reference,
        status="pending",
    )

    db.session.add(
        payment
    )

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            (
                "Campaign FanPayment "
                "creation failed."
            )
        )

        flash(
            (
                "Contribution could not "
                "be started."
            ),
            "error",
        )

        return redirect(
            url_for(
                "fan_payments.campaign_detail",
                username=creator.username,
                slug=campaign.slug,
            )
        )

    try:

        checkout = (
            initialize_fan_payment(
                email=email,
                amount_cents=(
                    amount_cents
                ),
                reference=reference,
                subaccount_code=(
                    payout_account
                    .provider_subaccount_code
                ),
                callback_url=(
                    url_for(
                        "fan_payments.payment_return",
                        _external=True,
                    )
                ),
                metadata={
                    "product_type": (
                        "fundraising"
                    ),
                    "fan_payment_id": (
                        payment.id
                    ),
                    "creator_account_id": (
                        creator.id
                    ),
                    "creator_username": (
                        creator.username
                    ),
                    "campaign_id": (
                        campaign.id
                    ),
                    "payment_type": (
                        "campaign"
                    ),
                },
            )
        )

    except PaystackError:

        current_app.logger.exception(
            (
                "Paystack campaign checkout "
                "initialization failed."
            )
        )

        flash(
            (
                "We could not open the "
                "payment page."
            ),
            "error",
        )

        return redirect(
            url_for(
                "fan_payments.campaign_detail",
                username=creator.username,
                slug=campaign.slug,
            )
        )

    return redirect(
        checkout["authorization_url"]
    )


# ============================================================
# PAYSTACK CALLBACK
# ============================================================
#
# Browser return is NOT proof of payment.
#
# We verify with Paystack, but the webhook remains the
# authoritative asynchronous payment path.
# ============================================================

@fan_payments_bp.route(
    "/payment/return"
)
def payment_return():

    reference = (
        request.args
        .get("reference", "")
        .strip()
    )

    if not reference:

        return render_template(
            "public/payment_result.html",
            payment_confirmed=False,
            message=(
                "We could not identify "
                "this payment."
            ),
        )

    payment = (
        FanPayment.query
        .filter_by(
            provider="paystack",
            provider_reference=reference,
        )
        .first()
    )

    if not payment:

        abort(404)

    # Do not mark it paid here.
    #
    # Browser redirect is not trusted.

    return render_template(
        "public/payment_result.html",
        payment=payment,
        payment_confirmed=(
            payment.status == "paid"
        ),
        message=(
            "Payment confirmed. Thank you!"
            if payment.status == "paid"
            else (
                "Your payment is being "
                "confirmed."
            )
        ),
    )


# ============================================================
# PAYSTACK WEBHOOK
# ============================================================

@fan_payments_bp.route(
    "/paystack/webhook",
    methods=["POST"],
)
def paystack_webhook():

    raw_body = request.get_data(
        cache=True,
        as_text=False,
    )

    signature = (
        request.headers.get(
            "x-paystack-signature",
            "",
        )
    )

    try:

        verified = (
            verify_paystack_webhook(
                raw_body,
                signature,
            )
        )

    except PaystackError:

        current_app.logger.exception(
            (
                "Paystack webhook "
                "verification configuration "
                "error."
            )
        )

        return "", 500

    if not verified:

        current_app.logger.warning(
            (
                "Rejected Paystack webhook "
                "with invalid signature."
            )
        )

        return "", 401

    event = (
        request.get_json(
            silent=True
        )
        or {}
    )

    event_type = (
        event.get("event")
    )

    # We only mutate FanPayment from
    # successful charge events.

    if event_type != "charge.success":

        return "", 200

    event_data = (
        event.get("data")
        or {}
    )

    reference = (
        str(
            event_data.get(
                "reference"
            )
            or ""
        )
        .strip()
    )

    if not reference:

        return "", 200

    try:

        # ----------------------------------------------------
        # DATABASE LOCK
        # ----------------------------------------------------

        payment = (
            db.session.query(
                FanPayment
            )
            .filter(
                FanPayment.provider
                == "paystack",
                FanPayment.provider_reference
                == reference,
            )
            .with_for_update()
            .first()
        )

        if not payment:

            db.session.rollback()

            current_app.logger.warning(
                (
                    "Paystack webhook reference "
                    "does not match FanPayment. "
                    "reference=%s"
                ),
                reference,
            )

            return "", 200

        # ----------------------------------------------------
        # IDEMPOTENCY
        # ----------------------------------------------------

        if payment.status == "paid":

            db.session.rollback()

            return "", 200

        # ----------------------------------------------------
        # VERIFY WITH PAYSTACK API
        # ----------------------------------------------------

        verified_data = (
            verify_transaction(
                reference
            )
        )

        provider_status = (
            str(
                verified_data.get(
                    "status"
                )
                or ""
            )
            .lower()
        )

        provider_reference = (
            str(
                verified_data.get(
                    "reference"
                )
                or ""
            )
        )

        provider_currency = (
            str(
                verified_data.get(
                    "currency"
                )
                or ""
            )
            .upper()
        )

        try:

            provider_amount = int(
                verified_data.get(
                    "amount"
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            provider_amount = -1

        # ----------------------------------------------------
        # SERVER-SIDE FINANCIAL VALIDATION
        # ----------------------------------------------------

        if provider_status != "success":

            db.session.rollback()

            return "", 200

        if (
            provider_reference
            != payment.provider_reference
        ):

            db.session.rollback()

            current_app.logger.error(
                (
                    "Paystack payment reference "
                    "mismatch. fan_payment_id=%s"
                ),
                payment.id,
            )

            return "", 200

        if provider_currency != "ZAR":

            db.session.rollback()

            current_app.logger.error(
                (
                    "Paystack currency mismatch. "
                    "fan_payment_id=%s"
                ),
                payment.id,
            )

            return "", 200

        if (
            provider_amount
            != payment.amount_cents
        ):

            db.session.rollback()

            current_app.logger.error(
                (
                    "Paystack amount mismatch. "
                    "fan_payment_id=%s"
                ),
                payment.id,
            )

            return "", 200

        # ----------------------------------------------------
        # METADATA DEFENCE-IN-DEPTH
        # ----------------------------------------------------

        metadata = (
            get_metadata(
                verified_data
            )
        )

        metadata_creator_id = (
            metadata.get(
                "creator_account_id"
            )
        )

        metadata_payment_id = (
            metadata.get(
                "fan_payment_id"
            )
        )

        metadata_payment_type = (
            metadata.get(
                "payment_type"
            )
        )

        if (
            str(metadata_creator_id)
            != str(
                payment.creator_account_id
            )
        ):

            db.session.rollback()

            current_app.logger.error(
                (
                    "Paystack creator metadata "
                    "mismatch. fan_payment_id=%s"
                ),
                payment.id,
            )

            return "", 200

        if (
            str(metadata_payment_id)
            != str(payment.id)
        ):

            db.session.rollback()

            current_app.logger.error(
                (
                    "Paystack payment metadata "
                    "mismatch. fan_payment_id=%s"
                ),
                payment.id,
            )

            return "", 200

        if (
            metadata_payment_type
            != payment.payment_type
        ):

            db.session.rollback()

            current_app.logger.error(
                (
                    "Paystack payment type "
                    "mismatch. fan_payment_id=%s"
                ),
                payment.id,
            )

            return "", 200

        # ----------------------------------------------------
        # CAMPAIGN INTEGRITY
        # ----------------------------------------------------

        if (
            payment.payment_type
            == "campaign"
        ):

            metadata_campaign_id = (
                metadata.get(
                    "campaign_id"
                )
            )

            if (
                str(metadata_campaign_id)
                != str(payment.campaign_id)
            ):

                db.session.rollback()

                current_app.logger.error(
                    (
                        "Paystack campaign metadata "
                        "mismatch. fan_payment_id=%s"
                    ),
                    payment.id,
                )

                return "", 200

        # ----------------------------------------------------
        # PROVIDER TRANSACTION ID
        # ----------------------------------------------------

        provider_transaction_id = (
            verified_data.get("id")
        )

        if provider_transaction_id is not None:

            provider_transaction_id = (
                str(
                    provider_transaction_id
                )
            )

        # ----------------------------------------------------
        # MARK PAID
        # ----------------------------------------------------

        payment.status = "paid"

        payment.provider_transaction_id = (
            provider_transaction_id
        )

        payment.paid_at = utc_now()

        db.session.commit()

        current_app.logger.info(
            (
                "Fan payment confirmed. "
                "fan_payment_id=%s "
                "creator_account_id=%s "
                "payment_type=%s"
            ),
            payment.id,
            payment.creator_account_id,
            payment.payment_type,
        )

        return "", 200

    except PaystackError:

        db.session.rollback()

        current_app.logger.exception(
            (
                "Paystack transaction "
                "verification failed."
            )
        )

        # Return non-2xx so Paystack can retry.
        return "", 500

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            (
                "Unexpected Paystack "
                "webhook processing error."
            )
        )

        return "", 500
