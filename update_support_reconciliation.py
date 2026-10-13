"""Safely add a creator-owned, CSRF-protected payment verification button.
Run from the project root: python update_support_reconciliation.py
Creates .bak backups; idempotent.
"""
from pathlib import Path

studio = Path('routes/studio.py')
template = Path('templates/studio/support_setup.html')
for p in (studio, template):
    if not p.is_file():
        raise SystemExit(f'Missing {p}; run this script from the Flask project root.')

s = studio.read_text(encoding='utf-8')
t = template.read_text(encoding='utf-8')
if 'def verify_support_payment(' in s or 'studio.verify_support_payment' in t:
    raise SystemExit('Reconciliation appears already installed. No files changed.')

anchor = '# ============================================================\n# SUPPORT SETUP\n# ============================================================'
if s.count(anchor) != 1:
    raise SystemExit('Could not uniquely locate SUPPORT SETUP in routes/studio.py. No files changed.')

new_route = '''# ============================================================
# VERIFY EXISTING FAN PAYMENT (CREATOR-OWNED + CSRF)
# ============================================================

@studio_bp.route(
    "/monetisation/support/<int:payment_id>/verify",
    methods=["POST"],
)
@studio_required
def verify_support_payment(payment_id):
    """Reconcile an existing payment; never create a new charge."""
    import hmac
    from routes.fan_payments import confirm_fan_payment

    account = current_creator_account()
    if account is None:
        abort(403)

    if not creator_has_feature(account, FEATURE_FAN_SUPPORT):
        abort(403)

    expected_token = session.get("support_verify_csrf")
    submitted_token = request.form.get("csrf_token", "")
    if (
        not isinstance(expected_token, str)
        or not isinstance(submitted_token, str)
        or not expected_token
        or not hmac.compare_digest(expected_token, submitted_token)
    ):
        abort(400, description="Invalid payment verification token.")

    payment = FanPayment.query.filter_by(
        id=payment_id,
        creator_account_id=account.id,
        payment_type="support",
    ).first_or_404()

    if payment.status == "paid":
        flash("This contribution is already confirmed.", "success")
        return redirect(url_for("studio.support_setup"), code=303)

    if payment.status == "refunded":
        flash("Refunded contributions cannot be reconfirmed.", "warning")
        return redirect(url_for("studio.support_setup"), code=303)

    if payment.status not in {"pending", "failed"}:
        flash("This payment is not eligible for verification.", "warning")
        return redirect(url_for("studio.support_setup"), code=303)

    reference = payment.provider_reference
    if not isinstance(reference, str) or not reference.strip():
        flash("This payment has no Paystack reference.", "error")
        return redirect(url_for("studio.support_setup"), code=303)

    # Avoid retaining the prior read transaction while Paystack is queried.
    db.session.rollback()
    confirmed, reason = confirm_fan_payment(
        reference,
        source="creator_studio_reconciliation",
    )

    # Recheck ownership and status after verification before reporting success.
    updated = FanPayment.query.filter_by(
        id=payment_id,
        creator_account_id=account.id,
        payment_type="support",
    ).first()

    if confirmed and updated is not None and updated.status == "paid":
        flash("Paystack verified this contribution. Status: Paid.", "success")
    else:
        current_app.logger.warning(
            "Studio payment verification unsuccessful creator_id=%s payment_id=%s reason=%s",
            account.id, payment_id, reason,
        )
        flash(
            "Payment could not be confirmed. Check Render logs for the verification reason.",
            "warning",
        )

    return redirect(url_for("studio.support_setup"), code=303)


'''

s = s.replace(anchor, new_route + anchor, 1)

render_anchor = '    return render_template(\n        "studio/support_setup.html",'
if s.count(render_anchor) != 1:
    raise SystemExit('Could not uniquely locate support template rendering. No files changed.')

s = s.replace(render_anchor, '''    # Dedicated session CSRF token for this payment-verification action.
    # Flask session is signed by SECRET_KEY; do not expose this token in logs.
    import secrets
    if not session.get("support_verify_csrf"):
        session["support_verify_csrf"] = secrets.token_urlsafe(32)

''' + render_anchor, 1)

context_anchor = '        recent_support=recent_support,\n'
if s.count(context_anchor) != 1:
    raise SystemExit('Could not uniquely locate support template context. No files changed.')
s = s.replace(context_anchor, context_anchor + '        support_verify_csrf=session["support_verify_csrf"],\n', 1)

head_anchor = '''                            <th>
                                Date
                            </th>'''
if t.count(head_anchor) != 1:
    raise SystemExit('Could not uniquely locate Date table header. No files changed.')
t = t.replace(head_anchor, head_anchor + '''

                            <th>
                                Action
                            </th>''', 1)

row_anchor = '''                                <td>

                                    {% if payment.created_at %}'''
if t.count(row_anchor) != 1:
    raise SystemExit('Could not uniquely locate payment Date table cell. No files changed.')

# Add action cell just before the date cell; header follows the same order.
action_cell = '''                                <td>
                                    {% if payment.status in ['pending', 'failed'] %}
                                        <form method="POST"
                                              action="{{ url_for('studio.verify_support_payment', payment_id=payment.id) }}">
                                            <input type="hidden" name="csrf_token"
                                                   value="{{ support_verify_csrf }}">
                                            <button type="submit" class="support-button secondary"
                                                    style="margin-top:0;white-space:nowrap">
                                                Verify payment
                                            </button>
                                        </form>
                                    {% else %}
                                        —
                                    {% endif %}
                                </td>

'''
# Header Action added after Date, so insert action AFTER date cell, not before.
date_end = '''                                </td>

                            </tr>'''
if t.count(date_end) != 1:
    raise SystemExit('Could not uniquely locate end of payment row. No files changed.')
t = t.replace(date_end, '                                </td>\n\n' + action_cell + '                            </tr>', 1)

for p in (studio, template):
    p.with_name(p.name + '.bak').write_text(p.read_text(encoding='utf-8'), encoding='utf-8')
studio.write_text(s, encoding='utf-8')
template.write_text(t, encoding='utf-8')
print('Updated routes/studio.py and templates/studio/support_setup.html')
print('Backups saved as .bak files.')
