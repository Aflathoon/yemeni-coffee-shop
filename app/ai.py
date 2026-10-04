"""
DeepSeek API client for the shop's AI assistant.

Reads config from Setting table (managed in /admin/settings).
Falls back to .env if the DB value is empty.

Public API:
    is_configured()          → bool
    get_config()             → dict with key, models, temperature
    chat(messages, model=None, temperature=None, max_tokens=None, json_mode=False)
                             → dict {ok, content, model, usage, error, latency_ms}
    test_connection()        → dict {ok, description, model, latency_ms}
    explain_health(results)  → summarised diagnosis string
"""
import os
import time
import json
import requests

from app.models import Setting


API_URL = "https://api.deepseek.com/v1/chat/completions"


# ---------- Config ----------

def get_config():
    return {
        "enabled": (Setting.get("AI_ENABLED") or "1") not in ("0", "false", "no", "off"),
        "api_key": (Setting.get("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")).strip(),
        "model_chat": Setting.get("DEEPSEEK_MODEL_CHAT") or "deepseek-chat",
        "model_reason": Setting.get("DEEPSEEK_MODEL_REASON") or "deepseek-reasoner",
        "temperature": float(Setting.get("AI_TEMPERATURE") or 0.4),
        "watcher_enabled": (Setting.get("AI_WATCHER_ENABLED") or "0") == "1",
        "watcher_interval_min": int(Setting.get("AI_WATCHER_INTERVAL_MIN") or 30),
    }


def is_configured():
    c = get_config()
    return bool(c["enabled"] and c["api_key"])


# ---------- Low-level call ----------

def chat(messages, model=None, temperature=None, max_tokens=2048, json_mode=False, timeout=60):
    """
    Call DeepSeek chat completions API.

    messages: list of dicts [{role: "system"|"user"|"assistant", content: "..."}]
    Returns: {ok, content, model, usage, error, latency_ms}
    """
    c = get_config()
    if not c["enabled"]:
        return {"ok": False, "error": "AI is disabled in settings", "content": ""}
    if not c["api_key"]:
        return {"ok": False, "error": "API key not configured", "content": ""}

    chosen_model = model or c["model_chat"]
    temp = temperature if temperature is not None else c["temperature"]

    payload = {
        "model": chosen_model,
        "messages": messages,
        "temperature": temp,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {c['api_key']}",
        "Content-Type": "application/json",
    }

    start = time.time()
    try:
        r = requests.post(API_URL, json=payload, headers=headers, timeout=timeout)
        latency_ms = int((time.time() - start) * 1000)

        if r.status_code != 200:
            err_body = r.text[:500]
            return {
                "ok": False,
                "error": f"HTTP {r.status_code}: {err_body}",
                "content": "",
                "latency_ms": latency_ms,
                "model": chosen_model,
            }

        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content", "")
        usage = data.get("usage", {})

        return {
            "ok": True,
            "content": content,
            "model": chosen_model,
            "usage": usage,
            "latency_ms": latency_ms,
        }

    except requests.Timeout:
        return {"ok": False, "error": f"Timeout after {timeout}s", "content": "", "latency_ms": timeout * 1000}
    except requests.RequestException as e:
        return {"ok": False, "error": f"Network error: {e}", "content": ""}
    except ValueError:
        return {"ok": False, "error": "Invalid JSON from API", "content": ""}


# ---------- Diagnostics ----------

def test_connection():
    """Send a tiny prompt to verify key + model work."""
    c = get_config()
    if not c["api_key"]:
        return {"ok": False, "description": "API key not set"}

    r = chat(
        messages=[
            {"role": "system", "content": "You are a terse assistant."},
            {"role": "user", "content": "Reply with exactly: OK"},
        ],
        model=c["model_chat"],
        max_tokens=10,
        temperature=0,
    )
    if r["ok"]:
        return {
            "ok": True,
            "description": f"Connected · model {r['model']}",
            "model": r["model"],
            "latency_ms": r.get("latency_ms"),
            "sample": r["content"][:60],
        }
    return {"ok": False, "description": r["error"]}


# ---------- Prompt helpers ----------

def _system_prompt(role_description):
    return {
        "role": "system",
        "content": (
            "You are an assistant embedded in a Flask e-commerce site called "
            "'The Spice & Roast Co.' that sells coffee, tea, spices, herbs, and honey. "
            + role_description + " "
            "Be concise. Prefer plain text. Never invent products or facts about the site."
        ),
    }


def explain_health(check_results):
    """
    Given a list of check results [{name, status, message, detail}], produce
    a short human-readable summary of what's wrong and what to do.
    """
    if not is_configured():
        return {"ok": False, "error": "AI not configured", "summary": ""}

    # Only send failures/warnings to save tokens
    problematic = [r for r in check_results if r.get("status") in ("warn", "fail")]

    if not problematic:
        return {"ok": True, "summary": "All checks passed. Nothing to fix.", "raw": ""}

    lines = []
    for r in problematic:
        lines.append(f"- [{r.get('status','?').upper()}] {r.get('name')}: {r.get('message','')}")
        if r.get("detail"):
            lines.append(f"  detail: {r['detail'][:400]}")

    user_prompt = (
        "A health check ran on the site. Here are the problems detected:\n\n"
        + "\n".join(lines)
        + "\n\nWrite a short summary (2–4 sentences) covering: "
        "what's most urgent, what to do first, and whether the site is usable right now. "
        "Do not produce code."
    )

    r = chat(
        messages=[
            _system_prompt("You explain technical problems in plain language to a shop owner."),
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=400,
    )

    if r["ok"]:
        return {"ok": True, "summary": r["content"].strip(), "raw": r["content"]}
    return {"ok": False, "error": r["error"], "summary": ""}
