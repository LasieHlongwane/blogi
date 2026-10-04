# ============================================================
# CREATOR BLOG
# EMAIL SERVICE
# ============================================================

import smtplib
import ssl

from email.message import EmailMessage

from flask import current_app

from extensions import db

from models import (
    CreatorProfile,
    EmailDelivery,
    EmailSubscriber,
    ContentPost,
    utc_now,
)


# ============================================================
# SMTP CONFIGURATION
# ============================================================

def smtp_configured():

    required = [
        current_app.config.get(
            "SMTP_HOST"
        ),
        current_app.config.get(
            "SMTP_PORT"
        ),
        current_app.config.get(
            "SMTP_USERNAME"
        ),
        current_app.config.get(
            "SMTP_PASSWORD"
        ),
        current_app.config.get(
            "SMTP_FROM_EMAIL"
        ),
    ]

    return all(required)


# ============================================================
# SITE URL
# ============================================================

def site_url():

    return (
        current_app.config.get(
            "SITE_URL",
            "http://127.0.0.1:5000",
        )
        .rstrip("/")
    )


# ============================================================
# SEND SMTP EMAIL
# ============================================================

def send_email(
    to_email,
    subject,
    text_body,
    html_body=None,
):

    if not smtp_configured():

        raise RuntimeError(
            "SMTP is not configured. "
            "Check your SMTP environment variables."
        )

    host = current_app.config[
        "SMTP_HOST"
    ]

    port = current_app.config[
        "SMTP_PORT"
    ]

    username = current_app.config[
        "SMTP_USERNAME"
    ]

    password = current_app.config[
        "SMTP_PASSWORD"
    ]

    from_email = current_app.config[
        "SMTP_FROM_EMAIL"
    ]

    from_name = current_app.config.get(
        "SMTP_FROM_NAME",
        "Creator Blog",
    )

    use_tls = current_app.config.get(
        "SMTP_USE_TLS",
        True,
    )

    # ========================================================
    # MESSAGE
    # ========================================================

    message = EmailMessage()

    message["Subject"] = subject

    message["From"] = (
        f"{from_name} <{from_email}>"
    )

    message["To"] = to_email

    message.set_content(
        text_body
    )

    if html_body:

        message.add_alternative(
            html_body,
            subtype="html",
        )

    # ========================================================
    # SMTP
    # ========================================================

    context = (
        ssl.create_default_context()
    )

    with smtplib.SMTP(
        host,
        port,
        timeout=30,
    ) as smtp:

        smtp.ehlo()

        if use_tls:

            smtp.starttls(
                context=context
            )

            smtp.ehlo()

        smtp.login(
            username,
            password,
        )

        smtp.send_message(
            message
        )


# ============================================================
# DELIVERY LOG
# ============================================================

def create_delivery_log(
    subscriber,
    email_type,
    subject,
    status,
    post=None,
    error_message=None,
):

    delivery = EmailDelivery(
        subscriber_id=(
            subscriber.id
            if subscriber
            else None
        ),

        post_id=(
            post.id
            if post
            else None
        ),

        email_type=email_type,

        recipient_email=(
            subscriber.email
        ),

        subject=subject,

        status=status,

        error_message=(
            error_message
        ),

        sent_at=(
            utc_now()
            if status == "sent"
            else None
        ),
    )

    db.session.add(
        delivery
    )

    db.session.commit()

    return delivery


# ============================================================
# CREATOR NAME
# ============================================================

def creator_name():

    creator = (
        CreatorProfile.query
        .first()
    )

    if creator:

        return creator.display_name

    return current_app.config.get(
        "SMTP_FROM_NAME",
        "Creator",
    )


# ============================================================
# VERIFICATION EMAIL
# ============================================================

def send_verification_email(
    subscriber,
):

    verify_url = (
        f"{site_url()}"
        f"/newsletter/verify/"
        f"{subscriber.verification_token}"
    )

    unsubscribe_url = (
        f"{site_url()}"
        f"/newsletter/unsubscribe/"
        f"{subscriber.unsubscribe_token}"
    )

    name = creator_name()

    subject = (
        f"Confirm your subscription to {name}"
    )

    text_body = f"""
Hi,

Thanks for subscribing to {name}.

Please confirm your email address:

{verify_url}

If you didn't request this, you can ignore this email.

Unsubscribe:
{unsubscribe_url}
""".strip()

    html_body = f"""
<!doctype html>
<html>
<body style="
    margin:0;
    padding:0;
    background:#f5f1e9;
    font-family:Arial,Helvetica,sans-serif;
    color:#17191d;
">

    <div style="
        max-width:600px;
        margin:0 auto;
        padding:40px 20px;
    ">

        <div style="
            background:#ffffff;
            padding:40px;
            border-radius:16px;
        ">

            <p style="
                margin:0 0 10px;
                font-size:11px;
                font-weight:bold;
                letter-spacing:2px;
                color:#858079;
            ">
                ONE MORE STEP
            </p>

            <h1 style="
                margin:0 0 20px;
                font-family:Georgia,serif;
                font-size:36px;
                font-weight:normal;
            ">
                Never miss a post.
            </h1>

            <p style="
                font-size:16px;
                line-height:1.7;
                color:#5c5852;
            ">
                Thanks for subscribing to
                {name}. Confirm your email
                address to start receiving
                new stories, reels and vlogs.
            </p>

            <p style="margin:30px 0;">

                <a
                    href="{verify_url}"
                    style="
                        display:inline-block;
                        padding:14px 22px;
                        background:#111318;
                        color:#ffffff;
                        text-decoration:none;
                        border-radius:8px;
                        font-weight:bold;
                    "
                >
                    Confirm subscription
                </a>

            </p>

            <p style="
                margin-top:30px;
                font-size:11px;
                line-height:1.6;
                color:#918c85;
            ">
                If you didn't request this,
                simply ignore this email.
            </p>

        </div>

    </div>

</body>
</html>
""".strip()

    try:

        send_email(
            subscriber.email,
            subject,
            text_body,
            html_body,
        )

        create_delivery_log(
            subscriber=subscriber,
            email_type="verification",
            subject=subject,
            status="sent",
        )

        return True

    except Exception as exc:

        current_app.logger.exception(
            "Verification email failed."
        )

        create_delivery_log(
            subscriber=subscriber,
            email_type="verification",
            subject=subject,
            status="failed",
            error_message=str(exc)[:2000],
        )

        return False


# ============================================================
# WELCOME EMAIL
# ============================================================

def send_welcome_email(
    subscriber,
):

    unsubscribe_url = (
        f"{site_url()}"
        f"/newsletter/unsubscribe/"
        f"{subscriber.unsubscribe_token}"
    )

    name = creator_name()

    subject = (
        f"You're subscribed to {name}"
    )

    text_body = f"""
You're in!

Your subscription to {name} is now active.

You'll receive an email whenever new content is published.

Visit the website:
{site_url()}

Unsubscribe:
{unsubscribe_url}
""".strip()

    html_body = f"""
<!doctype html>
<html>
<body style="
    margin:0;
    padding:0;
    background:#f5f1e9;
    font-family:Arial,Helvetica,sans-serif;
    color:#17191d;
">

    <div style="
        max-width:600px;
        margin:0 auto;
        padding:40px 20px;
    ">

        <div style="
            background:#ffffff;
            padding:40px;
            border-radius:16px;
        ">

            <p style="
                font-size:11px;
                font-weight:bold;
                letter-spacing:2px;
                color:#858079;
            ">
                WELCOME
            </p>

            <h1 style="
                font-family:Georgia,serif;
                font-weight:normal;
                font-size:36px;
            ">
                You're in.
            </h1>

            <p style="
                color:#5c5852;
                line-height:1.7;
            ">
                Your subscription to
                {name} is active.
                You'll hear from me whenever
                something new is published.
            </p>

            <p style="margin:30px 0;">

                <a
                    href="{site_url()}"
                    style="
                        display:inline-block;
                        padding:14px 22px;
                        background:#111318;
                        color:#ffffff;
                        text-decoration:none;
                        border-radius:8px;
                        font-weight:bold;
                    "
                >
                    Visit the website
                </a>

            </p>

            <p style="
                margin-top:35px;
                font-size:11px;
                color:#918c85;
            ">

                Don't want these emails?

                <a
                    href="{unsubscribe_url}"
                    style="color:#69645e;"
                >
                    Unsubscribe
                </a>

            </p>

        </div>

    </div>

</body>
</html>
""".strip()

    try:

        send_email(
            subscriber.email,
            subject,
            text_body,
            html_body,
        )

        create_delivery_log(
            subscriber=subscriber,
            email_type="welcome",
            subject=subject,
            status="sent",
        )

        return True

    except Exception as exc:

        current_app.logger.exception(
            "Welcome email failed."
        )

        create_delivery_log(
            subscriber=subscriber,
            email_type="welcome",
            subject=subject,
            status="failed",
            error_message=str(exc)[:2000],
        )

        return False


# ============================================================
# NEW POST EMAIL
# ============================================================

def send_new_post_email(
    subscriber,
    post,
):

    post_url = (
        f"{site_url()}"
        f"/content/{post.slug}"
    )

    unsubscribe_url = (
        f"{site_url()}"
        f"/newsletter/unsubscribe/"
        f"{subscriber.unsubscribe_token}"
    )

    name = creator_name()

    type_name = (
        post.content_type.capitalize()
    )

    subject = (
        f"New {type_name}: {post.title}"
    )

    excerpt = (
        post.excerpt
        or "Something new has just been published."
    )

    text_body = f"""
{name} just published a new {type_name.lower()}.

{post.title}

{excerpt}

Read/watch it here:
{post_url}

Unsubscribe:
{unsubscribe_url}
""".strip()

    cover_html = ""

    if post.cover_image_url:

        cover_html = f"""
        <img
            src="{post.cover_image_url}"
            alt=""
            style="
                display:block;
                width:100%;
                max-height:420px;
                object-fit:cover;
                margin:25px 0;
                border-radius:12px;
            "
        >
        """

    html_body = f"""
<!doctype html>
<html>
<body style="
    margin:0;
    padding:0;
    background:#f5f1e9;
    font-family:Arial,Helvetica,sans-serif;
    color:#17191d;
">

    <div style="
        max-width:620px;
        margin:0 auto;
        padding:40px 20px;
    ">

        <div style="
            background:#ffffff;
            padding:40px;
            border-radius:16px;
        ">

            <p style="
                margin:0 0 12px;
                font-size:10px;
                font-weight:bold;
                letter-spacing:2px;
                color:#858079;
            ">
                NEW {type_name.upper()}
            </p>

            <h1 style="
                margin:0;
                font-family:Georgia,serif;
                font-size:38px;
                line-height:1.1;
                font-weight:normal;
            ">
                {post.title}
            </h1>

            {cover_html}

            <p style="
                color:#5c5852;
                font-size:16px;
                line-height:1.7;
            ">
                {excerpt}
            </p>

            <p style="margin:30px 0;">

                <a
                    href="{post_url}"
                    style="
                        display:inline-block;
                        padding:14px 22px;
                        background:#111318;
                        color:#ffffff;
                        text-decoration:none;
                        border-radius:8px;
                        font-weight:bold;
                    "
                >
                    View {type_name}
                </a>

            </p>

            <hr style="
                margin:35px 0 20px;
                border:0;
                border-top:1px solid #e6e1d9;
            ">

            <p style="
                font-size:11px;
                line-height:1.6;
                color:#918c85;
            ">

                You received this because you
                subscribed to updates from
                {name}.

                <br><br>

                <a
                    href="{unsubscribe_url}"
                    style="color:#69645e;"
                >
                    Unsubscribe
                </a>

            </p>

        </div>

    </div>

</body>
</html>
""".strip()

    try:

        send_email(
            subscriber.email,
            subject,
            text_body,
            html_body,
        )

        create_delivery_log(
            subscriber=subscriber,
            email_type="new_post",
            subject=subject,
            status="sent",
            post=post,
        )

        return True

    except Exception as exc:

        current_app.logger.exception(
            "New post email failed."
        )

        create_delivery_log(
            subscriber=subscriber,
            email_type="new_post",
            subject=subject,
            status="failed",
            post=post,
            error_message=str(exc)[:2000],
        )

        return False


# ============================================================
# NOTIFY ALL ACTIVE SUBSCRIBERS
# ============================================================

def notify_subscribers_about_post(
    post,
):

    # Do not email people about premium content yet.
    # Membership email rules will come later.

    if post.access_level != "public":

        return {
            "sent": 0,
            "failed": 0,
        }

    subscribers = (
        EmailSubscriber.query
        .filter_by(
            status="active"
        )
        .all()
    )

    sent = 0
    failed = 0

    for subscriber in subscribers:

        # ----------------------------------------------------
        # DUPLICATE PROTECTION
        # ----------------------------------------------------

        already_sent = (
            EmailDelivery.query
            .filter_by(
                subscriber_id=subscriber.id,
                post_id=post.id,
                email_type="new_post",
                status="sent",
            )
            .first()
        )

        if already_sent:

            continue

        success = (
            send_new_post_email(
                subscriber,
                post,
            )
        )

        if success:
            sent += 1
        else:
            failed += 1

    return {
        "sent": sent,
        "failed": failed,
    }