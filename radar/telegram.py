"""Thin Telegram Bot API wrapper (polling, no webhook, so it works from a cron runner)."""
import requests

from . import config

TIMEOUT = 30


def _api(method, **params):
    if config.DRY_RUN:
        print(f"[tg dry-run] {method}: {str(params)[:300]}")
        return {"message_id": 0} if method == "sendMessage" else []
    r = requests.post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}", json=params, timeout=TIMEOUT)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"telegram {method} failed: {data}")
    return data["result"]


def send(chat_id, text, buttons=None, reply_to=None, preview=False):
    params = {
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": not preview},
    }
    if buttons:
        params["reply_markup"] = {"inline_keyboard": buttons}
    if reply_to:
        params["reply_parameters"] = {"message_id": reply_to}
    return _api("sendMessage", **params)


def updates(offset):
    return _api("getUpdates", offset=offset, timeout=0, allowed_updates=["message", "callback_query", "message_reaction_count"])


def answer_callback(cb_id, text):
    try:
        _api("answerCallbackQuery", callback_query_id=cb_id, text=text)
    except Exception as e:  # noqa: BLE001  (callback may have expired; not fatal)
        print(f"[tg] answerCallbackQuery: {e!r}")


def clear_buttons(chat_id, message_id):
    try:
        _api("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id, reply_markup={"inline_keyboard": []})
    except Exception as e:  # noqa: BLE001
        print(f"[tg] clear_buttons: {e!r}")


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
