"""
Telegram Bot API wrapper.

Reads config from the Setting table (managed in /admin/settings).
Falls back to .env vars if the DB values are empty.

Usage:
    from app.telegram import send_message, send_photo, send_product, send_post, test_connection
    result = send_message("Hello from The Spice & Roast Co.")
"""
import os
import requests
from app import db
from app.models import Setting

API_ROOT = "https://api.telegram.org"


# ---------- Config ----------

def get_config():
    """Return (token, chat_id). Prefer DB values; fall back to env."""
    token = (Setting.get("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = (Setting.get("TELEGRAM_CHANNEL_ID") or os.getenv("TELEGRAM_CHANNEL_ID", "")).strip()
    return token, chat_id


def is_configured():
    token, chat_id = get_config()
    return bool(token and chat_id)


# ---------- Low-level calls ----------

def _post(method, payload, timeout=15):
    """POST to Bot API. Returns dict {ok, description?, result?}."""
    token, _ = get_config()
    if not token:
        return {"ok": False, "description": "Bot token not configured"}

    url = f"{API_ROOT}/bot{token}/{method}"
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        data = r.json()
        if not data.get("ok"):
            return {"ok": False, "description": data.get("description", f"HTTP {r.status_code}")}
        return data
    except requests.RequestException as e:
        return {"ok": False, "description": f"Network error: {e}"}
    except ValueError:
        return {"ok": False, "description": "Invalid response from Telegram"}


# ---------- High-level helpers ----------

def send_message(text, parse_mode="HTML", disable_preview=True):
    """Send a plain message to the configured channel."""
    _, chat_id = get_config()
    if not chat_id:
        return {"ok": False, "description": "Channel not configured"}
    return _post("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_preview,
    })


def send_photo(photo_url, caption="", parse_mode="HTML"):
    """Send a photo by URL (Telegram fetches it) with optional caption."""
    _, chat_id = get_config()
    if not chat_id:
        return {"ok": False, "description": "Channel not configured"}
    return _post("sendPhoto", {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": parse_mode,
    })


# ---------- Formatters ----------

def _absolute_url(path_or_url, base_url=None):
    """Turn a /static/... path into a full URL if a base is provided."""
    if not path_or_url:
        return None
    if path_or_url.startswith("http"):
        return path_or_url
    if base_url:
        return base_url.rstrip("/") + path_or_url
    return path_or_url  # Telegram may reject relative URLs


def _html_escape(s):
    if not s:
        return ""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))


def send_product(product, base_url=None):
    """Post a product card to Telegram: image + name + price + origin + link."""
    name = _html_escape(product.name)
    origin = _html_escape(product.origin_country or "")
    region = _html_escape(product.origin_region or "")
    desc = _html_escape(product.short_desc or product.description or "")
    if len(desc) > 200:
        desc = desc[:197] + "..."

    lines = [f"<b>{name}</b>"]
    if origin:
        lines.append(f"📍 {origin}" + (f" · {region}" if region else ""))
    if desc:
        lines.append("")
        lines.append(desc)
    lines.append("")
    lines.append(f"💰 <b>${product.price:.2f}</b> · {product.weight_grams}g")

    if base_url:
        lines.append(f'🔗 <a href="{base_url.rstrip("/")}/product/{product.slug}">View in shop</a>')

    caption = "\n".join(lines)
    image_url = _absolute_url(product.image, base_url)

    # Try photo first; fall back to text if image fails
    if image_url and (image_url.startswith("http")):
        # Convert /static/images/foo.jpg to a form Telegram accepts
        if image_url.startswith("http"):
            r = send_photo(image_url, caption=caption)
            if r.get("ok"):
                return r
    return send_message(caption)


def send_post(post, base_url=None):
    """Post a marketing post to Telegram: image + title + body."""
    title = _html_escape(post.title or "New from The Spice & Roast Co.")
    body = post.body or ""

    # If body is HTML, strip tags for Telegram (they only support limited HTML)
    import re
    body_text = re.sub(r"<[^>]+>", "", body).strip()
    if len(body_text) > 800:
        body_text = body_text[:797] + "..."

    caption_lines = [f"<b>{title}</b>", "", _html_escape(body_text)]
    caption = "\n".join(caption_lines)

    image_url = _absolute_url(post.image, base_url)
    if image_url and image_url.startswith("http"):
        r = send_photo(image_url, caption=caption)
        if r.get("ok"):
            return r
    return send_message(caption)


# ---------- Diagnostics ----------

def test_connection():
    """Send a test message. Returns dict with ok + description."""
    if not is_configured():
        return {"ok": False, "description": "Bot token or channel ID missing — set them in /admin/settings"}
    result = send_message("✅ <b>The Spice &amp; Roast Co.</b> bot is online.\nTelegram integration working.")
    if result.get("ok"):
        return {"ok": True, "description": "Test message sent successfully"}
    return result


def test_chat_id():
    """Ask Telegram what it knows about the configured channel."""
    token, chat_id = get_config()
    if not token or not chat_id:
        return {"ok": False, "description": "Not configured"}
    url = f"{API_ROOT}/bot{token}/getChat"
    try:
        r = requests.get(url, params={"chat_id": chat_id}, timeout=10)
        data = r.json()
        if data.get("ok"):
            ch = data["result"]
            return {"ok": True, "description": f"Found: {ch.get('title') or ch.get('username')} (type: {ch.get('type')})"}
        return {"ok": False, "description": data.get("description", "Unknown error")}
    except Exception as e:
        return {"ok": False, "description": f"Network error: {e}"}
