"""JSON state committed back to the repo each tick. Public repo: never store secrets here."""
import json
import os
import time
from datetime import datetime, timezone

from . import config


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load():
    if os.path.exists(config.STATE_PATH):
        with open(config.STATE_PATH, encoding="utf-8") as f:
            s = json.load(f)
    else:
        s = {}
    s.setdefault("seen", {})          # item_key -> unix ts first seen
    s.setdefault("pending", {})       # draft_id -> draft record awaiting approval
    s.setdefault("published", [])     # recent published summaries (capped)
    s.setdefault("tg_offset", 0)      # Telegram getUpdates offset
    s.setdefault("daily", {})         # date -> {"drafts": n, "published": n}
    s.setdefault("queue", [])         # scored stories waiting for a drafting slot
    return s


def prune(s):
    cutoff = time.time() - config.SEEN_TTL_DAYS * 86400
    s["seen"] = {k: v for k, v in s["seen"].items() if v >= cutoff}
    s["published"] = s["published"][-200:]
    # drop pending drafts older than 3 days
    s["pending"] = {k: v for k, v in s["pending"].items() if v.get("created", 0) >= time.time() - 3 * 86400}
    s["recent"] = dict(list(s.get("recent", {}).items())[-30:])
    keep = sorted(s["daily"].keys())[-14:]
    s["daily"] = {k: s["daily"][k] for k in keep}


def bump(s, field):
    d = s["daily"].setdefault(today(), {"drafts": 0, "published": 0})
    d[field] = d.get(field, 0) + 1


def count(s, field):
    return s["daily"].get(today(), {}).get(field, 0)


def save(s):
    prune(s)
    os.makedirs(os.path.dirname(config.STATE_PATH) or ".", exist_ok=True)
    tmp = config.STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1, ensure_ascii=False, sort_keys=True)
    os.replace(tmp, config.STATE_PATH)
