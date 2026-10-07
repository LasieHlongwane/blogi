# ============================================================
# CREATOR PLATFORM
# PLATFORM PAYMENTS
# ============================================================
#
# Stage 3:
#
# This blueprint exists so that the creator registration /
# pending-payment flow has a valid checkout endpoint.
#
# IMPORTANT:
# No payment is processed here yet.
# No creator is activated here.
# No subscription is started here.
#
# Stage 4 will replace the temporary checkout handler with
# the real Yoco hosted checkout integration.
# ============================================================

from flask import (
    Blueprint,
    redirect,
    url_for,
    flash,
    session,
)

from extensions import db

from models import (
    CreatorAccount,
)

from services.plan_service import (
    PLAN_STANDARD,
    PLAN_PRICES,
    VALID_PLANS,
    normalize_plan,
)


# ============================================================
# BLUEPRINT
# ============================================================

payments_bp = Blueprint(
    "payments",
    __name__,
    url_prefix="/payments",
)


# ============================================================
# HELPERS
# ============================================================

def get_logged_in_creator():

    creator_id = session.get(
        "creator_account_id"
    )

    if not creator_id:
        return None

    return db.session.get(
        CreatorAccount,
        creator_id,
    )


# ============================================================
# CREATOR CHECKOUT
# ============================================================

@payments_bp.route(
    "/creator/checkout",
    methods=["POST"],
)
def creator_checkout():

    creator = (
        get_logged_in_creator()
    )

    if not creator:

        flash(
            "Please sign in to continue.",
            "warning",
        )

        return redirect(
            url_for(
                "creator_auth.login"
            )
        )

    # --------------------------------------------------------
    # USE THE PLAN STORED ON THE CREATOR ACCOUNT
    # --------------------------------------------------------
    #
    # We intentionally DO NOT trust:
    #
    #     request.form["price"]
    #     request.form["amount"]
    #
    # The backend determines the plan and its price.
    # --------------------------------------------------------

    selected_plan = normalize_plan(
        creator.plan,
        default=PLAN_STANDARD,
    )

    if selected_plan not in VALID_PLANS:

        selected_plan = PLAN_STANDARD

    amount = PLAN_PRICES[
        selected_plan
    ]

    # --------------------------------------------------------
    # STAGE 3 ONLY
    # --------------------------------------------------------
    #
    # Do not mark payment as paid.
    # Do not activate the creator.
    # Do not start a subscription.
    #
    # Stage 4 will create the real Yoco hosted checkout here.
    # --------------------------------------------------------

    flash(
        (
            f"{selected_plan.title()} plan selected "
            f"at R{amount}/month. "
            "Payment checkout will be connected next."
        ),
        "info",
    )

    return redirect(
        url_for(
            "creator_auth.pending"
        )
    )
