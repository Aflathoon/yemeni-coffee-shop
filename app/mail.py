"""
Email sender — uses SMTP configured in Settings.

Required settings (any one of these modes):
  - SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_USE_TLS, MAIL_FROM

If SMTP is not configured, emails are logged to a file and marked as 'sent'
in dry mode so tests don't fail. Set SMTP_ENABLED=0 to force dry mode.
"""
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

from app.models import Setting


log = logging.getLogger("mail")

# Where dry-run emails are written
DRY_RUN_DIR = Path("instance/emails_out")


# ---------- Config ----------

def mail_config():
    return {
        "enabled": (Setting.get("SMTP_ENABLED") or "1") not in ("0", "false", "no", "off"),
        "host": Setting.get("SMTP_HOST") or "",
        "port": int(Setting.get("SMTP_PORT") or 587),
        "user": Setting.get("SMTP_USER") or "",
        "password": Setting.get("SMTP_PASSWORD") or "",
        "use_tls": (Setting.get("SMTP_USE_TLS") or "1") not in ("0", "false", "no", "off"),
        "mail_from": Setting.get("MAIL_FROM") or (Setting.get("STORE_EMAIL") or "noreply@localhost"),
        "from_name": Setting.get("STORE_NAME") or "The Spice & Roast Co.",
    }


def is_configured():
    c = mail_config()
    if not c["enabled"]:
        return False
    return bool(c["host"] and c["user"] and c["password"])


# ---------- Sending ----------

def send_email(to_email, subject, body_text, body_html=None):
    """
    Send an email. Returns dict {ok, description}.

    If SMTP isn't configured, writes to instance/emails_out/ instead.
    """
    if not to_email:
        return {"ok": False, "description": "No recipient"}

    c = mail_config()

    # Dry run: write to file
    if not is_configured():
        DRY_RUN_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
        safe_to = "".join(ch if ch.isalnum() or ch in "@._-" else "_" for ch in to_email)[:60]
        fname = DRY_RUN_DIR / f"{ts}_{safe_to}.eml"
        content = f"To: {to_email}\nSubject: {subject}\nDate: {datetime.utcnow().isoformat()}\n\n{body_text}"
        fname.write_text(content, encoding="utf-8")
        log.info(f"[mail dry-run] {subject} -> {to_email} ({fname.name})")
        return {"ok": True, "description": f"Logged to {fname.name} (SMTP not configured)"}

    # Real send
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f'{c["from_name"]} <{c["mail_from"]}>'
        msg["To"] = to_email

        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        if c["use_tls"]:
            server = smtplib.SMTP(c["host"], c["port"], timeout=15)
            server.ehlo()
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(c["host"], c["port"], timeout=15)

        server.login(c["user"], c["password"])
        server.sendmail(c["mail_from"], [to_email], msg.as_string())
        server.quit()
        log.info(f"[mail sent] {subject} -> {to_email}")
        return {"ok": True, "description": "Sent"}

    except Exception as e:
        log.warning(f"[mail error] {e}")
        return {"ok": False, "description": str(e)}


# ---------- Templates (simple wrappers) ----------

def send_order_status_update(order, new_status):
    """Notify a customer/partner that their order status changed."""
    if not order.email:
        return {"ok": False, "description": "Order has no email"}

    labels = {
        "paid":      "Payment received",
        "shipped":   "Your order has shipped",
        "delivered": "Your order was delivered",
        "cancelled": "Your order was cancelled",
        "pending":   "Order received",
    }
    subject = f"{labels.get(new_status, 'Order update')} — #{order.id}"

    lines = [
        f"Hello {order.full_name},",
        "",
        f"An update on your order #{order.id}:",
        f"  Status: {labels.get(new_status, new_status.title())}",
        "",
    ]

    if new_status == "paid":
        lines += [f"Amount received: ${order.total:.2f}", "", "We'll let you know when it ships."]
    elif new_status == "shipped":
        lines += ["Your package is on its way."]
        if order.courier or order.tracking_number:
            lines += [f"  Courier: {order.courier or '—'}",
                      f"  Tracking: {order.tracking_number or '—'}"]
    elif new_status == "delivered":
        lines += ["We hope you enjoy it. Thanks for your order."]
    elif new_status == "cancelled":
        lines += [f"Reason: {order.cancellation_reason or 'Not specified'}"]
        if order.cancelled_at:
            lines += [f"Cancelled: {order.cancelled_at.strftime('%B %d, %Y')}"]

    lines += ["", "— The Spice & Roast Co."]

    return send_email(order.email, subject, "\n".join(lines))


def send_tier_state_change(account, old_state, new_state):
    """Notify a wholesale partner that their tier status changed."""
    if not account.email:
        return {"ok": False, "description": "Account has no email"}

    state_messages = {
        "warn":      ("Heads up — tier status", "You are one month behind the minimum order level for your tier. No change yet — this is a courtesy notice."),
        "grace":     ("Second month below target", "You've missed the tier minimum for a second consecutive month. Your tier remains for now, but the next miss will trigger a downgrade."),
        "downgrade": ("Tier downgrade pending", "You've missed the tier minimum for three consecutive months. Your account will move down one tier on the next review."),
        "terminate": ("Tier reset pending", "Six months below the minimum. Your account will be reset to the New tier on the next review."),
        "ok":        ("Tier status good", "You're meeting your tier minimums again. Welcome back to healthy status."),
    }
    title, message = state_messages.get(new_state, ("Tier status update", "Your tier status has changed."))

    subject = f"{title} — {account.company_name}"
    lines = [
        f"Hello {account.company_name},",
        "",
        f"Your tier status on the partner portal changed: {old_state or 'ok'} → {new_state}.",
        "",
        message,
        "",
        "If you have any questions, reply to this email.",
        "",
        "— The Spice & Roast Co.",
    ]
    return send_email(account.email, subject, "\n".join(lines))


def send_tier_changed(account, old_tier, new_tier):
    """Notify a partner that their actual tier discount changed."""
    if not account.email:
        return {"ok": False, "description": "Account has no email"}

    direction = "upgraded" if new_tier > old_tier else "downgraded"
    subject = f"Your partner tier was {direction}: {old_tier} → {new_tier}"
    lines = [
        f"Hello {account.company_name},",
        "",
        f"Your wholesale tier on The Spice & Roast Co. has been {direction}:",
        "",
        f"  Previous tier: {old_tier}",
        f"  New tier:      {new_tier}",
        "",
        f"All your pricing and product availability now reflects the {new_tier} tier.",
        "",
        "You can see your current rate on the partner portal at any time.",
        "",
        "— The Spice & Roast Co.",
    ]
    return send_email(account.email, subject, "\n".join(lines))


def send_test_email(to_email):
    """Send a test message to verify SMTP config."""
    subject = "Test email from The Spice & Roast Co."
    body = "This is a test. If you received it, SMTP is configured correctly."
    return send_email(to_email, subject, body)
