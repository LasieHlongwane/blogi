"""SMTP magic-link delivery; uses existing SMTP_* environment/config values."""
import smtplib
import ssl
from email.message import EmailMessage
from flask import current_app


def send_membership_login_email(email, creator_name, login_url):
    config = current_app.config
    host = config.get('SMTP_HOST')
    port = int(config.get('SMTP_PORT') or 587)
    username = config.get('SMTP_USERNAME')
    password = config.get('SMTP_PASSWORD')
    sender = config.get('SMTP_FROM_EMAIL') or username
    if not host or not sender:
        raise RuntimeError('SMTP_HOST and SMTP_FROM_EMAIL/SMTP_USERNAME must be configured')
    message = EmailMessage()
    message['Subject'] = f'Sign in to {creator_name} exclusive membership'
    message['From'] = sender
    message['To'] = email
    message.set_content(
        f'Your one-time sign-in link for {creator_name}:\n\n{login_url}\n\n'
        'This link expires in 15 minutes. If you did not request it, ignore this email.\n'
    )
    use_ssl = str(config.get('SMTP_USE_SSL', '')).lower() in ('1', 'true', 'yes')
    use_tls = str(config.get('SMTP_USE_TLS', 'true')).lower() in ('1', 'true', 'yes')
    if use_ssl:
        connection = smtplib.SMTP_SSL(host, port, timeout=15, context=ssl.create_default_context())
    else:
        connection = smtplib.SMTP(host, port, timeout=15)
    with connection as smtp:
        if use_tls and not use_ssl:
            smtp.starttls(context=ssl.create_default_context())
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)
