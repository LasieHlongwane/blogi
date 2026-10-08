"""Host-based creator resolution. Never trust forwarded host headers directly."""
import ipaddress
import re
from flask import abort, current_app, g, request
from models import CreatorAccount, CreatorDomain
from extensions import db

HOST_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")


def normalize_host(value):
    """Canonicalize an HTTP Host header, rejecting malformed/unsafe hosts."""
    value = (value or "").strip().lower()
    if not value or any(c in value for c in "/\\@#? \t\r\n"):
        return None
    if value.startswith("["):
        end = value.find("]")
        if end < 0:
            return None
        hostname = value[1:end]
        rest = value[end + 1:]
        if rest and not re.fullmatch(r":\d{1,5}", rest):
            return None
        try:
            ipaddress.IPv6Address(hostname)
        except ValueError:
            return None
        return hostname
    if value.count(":") > 1:
        return None
    if ":" in value:
        value, port = value.rsplit(":", 1)
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            return None
    value = value.rstrip(".")
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    if len(value) > 253 or not HOST_PATTERN.fullmatch(value):
        return None
    if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in value.split(".")):
        return None
    return value


def resolve_creator_host():
    """Return account for an active verified hostname, or None for platform hosts."""
    hostname = normalize_host(request.host)
    if hostname is None:
        abort(400)

    configured = current_app.config.get("KALXA_PLATFORM_HOSTS", "localhost,127.0.0.1,creators.kalxa.co.za,blog-creator-e5pz.onrender.com")
    if isinstance(configured, str):
        platform_hosts = {normalize_host(h) for h in configured.split(",")}
    else:
        platform_hosts = {normalize_host(h) for h in configured}
    if hostname in platform_hosts:
        return None

    domain = CreatorDomain.query.filter_by(hostname=hostname, is_active=True, verification_status="verified").first()
    if domain is None:
        abort(404)
    account = db.session.get(CreatorAccount, domain.creator_account_id)
    if account is None or account.account_status != "active":
        abort(404)
    if domain.domain_type == "custom" and account.plan != "premium":
        abort(404)
    if domain.domain_type not in {"custom", "subdomain"}:
        abort(404)
    if domain.domain_type == "subdomain":
        suffix = ".creators.kalxa.co.za"
        if not hostname.endswith(suffix) or hostname == suffix[1:]:
            abort(404)
    # IMPORTANT: Published content remains accessible when a subscription expires,
    # consistent with existing public.py behavior. Plan restrictions still apply.
    return account


def install_hostname_resolver(app):
    @app.before_request
    def _resolve_host():
        g.creator_domain_account = resolve_creator_host()
        if g.creator_domain_account is None:
            return
        # A hosted creator domain is a public website, not a way to reach
        # platform admin/studio/auth or another creator's public pages.
        if request.endpoint == "static":
            return
        if request.blueprint != "public":
            abort(404)
        username = (request.view_args or {}).get("username")
        if username and username.lower() != g.creator_domain_account.username.lower():
            abort(404)
