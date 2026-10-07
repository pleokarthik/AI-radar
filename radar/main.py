"""One tick: handle your feedback -> collect -> score -> draft. Run every 15 min by GitHub Actions.

Every human decision is logged to state/feedback.jsonl; the weekend learn loop (radar.learn) reads it."""
import json
import time
import traceback

from . import config, feedback as fb, llm, policy as pol, prompts, sources, state, telegram as tg

TIER_RANK = {t: i for i, t in enumerate(config.TIERS)}
TIER_LABEL = {"notable": "Notable", "major": "Major", "turning_point": "Turning point"}
TIER_EMOJI = {"notable": "🔹", "major": "🔶", "turning_point": "🚨"}

P = None  # policy loaded per tick


def _log(event, **kw):
    fb.log(event, P["version"], **kw)


def _send_safe(chat_id, text, **kw):
    try:
        return tg.send(chat_id, text, **kw)
    except RuntimeError as e:
        if "parse" in str(e).lower():  # model produced broken HTML; fall back to escaped text
            return tg.send(chat_id, tg.esc(text), **kw)
        raise


def _draft_for_reply(s, reply):
    for did, d in s["pending"].items():
        if any(p["msg_id"] == reply["message_id"] for p in d["drafts"].values()):
            return did, d
    return None, None


# ---------- your feedback ----------

def handle_updates(s):
    ups = tg.updates(s["tg_offset"] + 1 if s["tg_offset"] else 0)
    admin = str(config.TELEGRAM_ADMIN_CHAT_ID)
    for u in ups:
        s["tg_offset"] = max(s["tg_offset"], u["update_id"])

        rc = u.get("message_reaction_count")
        if rc:
            pub = next((x for x in s["published"] if x.get("channel_msg_id") == rc["message_id"]), None)
            if pub:
                total = sum(r["total_count"] for r in rc.get("reactions", []))
                _log("reactions", key=pub["key"], total=total,
                     detail={r["type"].get("emoji", r["type"]["type"]): r["total_count"] for r in rc.get("reactions", [])})
            continue

        cb = u.get("callback_query")
        if cb:
            if str(cb["from"]["id"]) != admin:
                continue
            action, _, rest = cb.get("data", "").partition(":")
            draft_id, _, provider = rest.partition(":")
            d = s["pending"].get(draft_id)
            if not d:
                tg.answer_callback(cb["id"], "Expired or already handled")
                continue
            decided = int(time.time() - d["created"])
            if action == "pub":
                text = d["drafts"][provider]["text"]
                if d.get("take"):
                    text += f"\n\n💬 <b>{tg.esc(config.AUTHOR_NAME)}'s take:</b> {tg.esc(d['take'])}"
                m = _send_safe(config.TELEGRAM_CHANNEL_ID, text)
                s["published"].append({"key": draft_id, "title": d["title"], "url": d["url"], "tier": d["tier"],
                                       "source": d["source"], "provider": provider,
                                       "channel_msg_id": m.get("message_id"), "ts": int(time.time())})
                state.bump(s, "published")
                tg.answer_callback(cb["id"], f"Posted ({provider})")
            else:
                tg.answer_callback(cb["id"], "Skipped. Reply 'fb <why>' to teach it.")
            _log("decision", key=draft_id, action="publish" if action == "pub" else "skip",
                 provider=provider or None, providers_offered=list(d["drafts"]), tier=d["tier"],
                 source=d["source"], title=d["title"], secs_to_decide=decided, had_take=bool(d.get("take")))
            for p in d["drafts"].values():
                tg.clear_buttons(admin, p["msg_id"])
            # keep a short-lived tombstone so late 'fb' replies still attach to this story
            s.setdefault("recent", {})[draft_id] = {k: d[k] for k in ("title", "tier", "source", "drafts")}
            s["pending"].pop(draft_id, None)
            continue

        msg = u.get("message")
        if not msg or str(msg.get("chat", {}).get("id")) != admin:
            continue
        text = (msg.get("text") or "").strip()
        reply = msg.get("reply_to_message")

        if reply:
            did, d = _draft_for_reply(s, reply)
            if not d:  # maybe already decided
                did, d = next(((k, v) for k, v in s.get("recent", {}).items()
                               if any(p["msg_id"] == reply["message_id"] for p in v["drafts"].values())), (None, None))
            if not d:
                tg.send(admin, "Couldn't match that reply to a draft.")
                continue
            low = text.lower()
            if low.startswith("fb "):
                _log("note", key=did, tier=d["tier"], source=d["source"], title=d["title"], text=text[3:].strip())
                tg.send(admin, "Noted for the weekend review.")
            elif low.startswith("/tier "):
                want = low.split(maxsplit=1)[1].strip()
                if want in TIER_RANK:
                    _log("wrongtier", key=did, given=d["tier"], wanted=want, source=d["source"], title=d["title"])
                    tg.send(admin, f"Logged: should be {want}.")
            elif did in s["pending"]:
                d["take"] = text
                _log("take", key=did, text=text)
                tg.send(admin, f"Take saved for: {tg.esc(d['title'])}. Tap Post when ready.")
            continue

        if text.startswith("/missed"):
            parts = text.split(maxsplit=2)
            if len(parts) >= 2:
                _log("missed", url=parts[1], why=parts[2] if len(parts) > 2 else "")
                tg.send(admin, "Logged as a miss. The learn loop will check why it was filtered.")
            else:
                tg.send(admin, "Usage: /missed <url> [why it mattered]")
        elif text == "/status":
            today = s["daily"].get(state.today(), {})
            tg.send(admin, f"Policy v{P['version']} · Pending {len(s['pending'])} · Queue {len(s['queue'])} · "
                           f"Today drafts {today.get('drafts', 0)}, published {today.get('published', 0)}")
        elif text in ("/help", "/start"):
            tg.send(admin, "Tap Post/Skip on drafts.\nReply to a draft:\n• plain text = your take\n"
                           "• <code>fb why</code> = critique\n• <code>/tier major</code> = correct tier\n"
                           "/missed &lt;url&gt; [why] = story it should have caught\n/status")


# ---------- collect + score ----------

def collect_and_score(s):
    fresh = [i for i in sources.collect_all() if i["key"] not in s["seen"]]
    fresh = list({i["key"]: i for i in fresh}.values())[: config.MAX_ITEMS_TO_SCORE]
    print(f"[tick] {len(fresh)} new items")
    if not fresh:
        return

    listing = "\n".join(json.dumps({"key": i["key"], "source": i["source"], "title": i["title"],
                                    "signal": i["signal"], "summary": i["summary"][:300]}) for i in fresh)
    reply = llm.call(config.SCORER, prompts.score_system(P), prompts.SCORE_USER.format(items=listing),
                     purpose="score", max_tokens=3000)
    scores = {r["key"]: r for r in llm.extract_json(reply)}

    now = time.time()
    min_rank = TIER_RANK[P["min_tier"]]
    weights = P.get("source_weights", {})
    for i in fresh:
        s["seen"][i["key"]] = now  # mark seen only after a successful score
        sc = scores.get(i["key"], {"tier": "skip", "reason": "not returned by scorer"})
        tier = sc.get("tier", "skip") if sc.get("tier") in TIER_RANK else "skip"
        if sc.get("dup_of"):
            tier = "skip"
        _log("scored", key=i["key"], source=i["source"], title=i["title"], url=i["url"],
             signal=i["signal"], tier=tier, reason=sc.get("reason", ""), dup_of=sc.get("dup_of"))
        # a learned source weight of e.g. -1 demotes a noisy source by one tier
        rank = TIER_RANK[tier] + int(weights.get(i["source"].split(" · ")[0], 0)) if tier != "skip" else 0
        if rank >= min_rank:
            eff = config.TIERS[min(max(rank, 1), 3)]
            s["queue"].append({**i, "tier": eff, "reason": sc.get("reason", ""), "queued": now})
            print(f"  + [{eff}] {i['title']}")


# ---------- draft ----------

def draft_next(s):
    s["queue"] = [q for q in s["queue"] if q["queued"] > time.time() - 2 * 86400]
    s["queue"].sort(key=lambda q: -TIER_RANK[q["tier"]])
    budget = min(config.MAX_DRAFTS_PER_TICK, P["max_drafts_per_day"] - state.count(s, "drafts"))
    admin = config.TELEGRAM_ADMIN_CHAT_ID

    while budget > 0 and s["queue"]:
        q = s["queue"].pop(0)
        text = sources.fetch_page_text(q["url"]) or q["summary"]
        system = prompts.draft_system(P, q["tier"])
        user = prompts.DRAFT_USER.format(title=q["title"], source=q["source"], url=q["url"],
                                         signal=q["signal"], tier=TIER_LABEL[q["tier"]], text=text)
        drafts = {}
        for p in config.DRAFTERS:
            try:
                t0 = time.time()
                out = llm.call(p, system, user, purpose="draft").strip()
                drafts[p] = {"text": out, "secs": round(time.time() - t0, 1)}
            except Exception as e:  # noqa: BLE001
                print(f"  draft via {p} failed: {e!r}")
        if not drafts:
            continue

        tg.send(admin, f"{TIER_EMOJI[q['tier']]} <b>{TIER_LABEL[q['tier']]}</b> · {tg.esc(q['source'])} · "
                       f"{tg.esc(q['signal'])}\n<i>{tg.esc(q['reason'])}</i>\n"
                       f"<a href=\"{q['url']}\">source</a> · {len(drafts)} draft(s) below.")
        for p, d in drafts.items():
            m = _send_safe(admin, d["text"], buttons=[[
                {"text": f"✅ Post ({p})", "callback_data": f"pub:{q['key']}:{p}"},
                {"text": "⏭ Skip", "callback_data": f"skip:{q['key']}:"},
            ]])
            d["msg_id"] = m["message_id"]

        s["pending"][q["key"]] = {"title": q["title"], "url": q["url"], "tier": q["tier"], "source": q["source"],
                                  "drafts": drafts, "take": None, "created": time.time()}
        _log("drafted", key=q["key"], tier=q["tier"], source=q["source"],
             providers={p: {"chars": len(d["text"]), "secs": d["secs"]} for p, d in drafts.items()})
        state.bump(s, "drafts")
        budget -= 1


def main():
    global P
    P = pol.load()
    config.HF_MIN_UPVOTES = P["hf_min_upvotes"]
    config.HN_MIN_POINTS = P["hn_min_points"]
    s = state.load()
    for step in (handle_updates, collect_and_score, draft_next):
        try:
            step(s)
        except Exception:  # noqa: BLE001  (one failing step must not lose state from the others)
            traceback.print_exc()
        finally:
            state.save(s)


if __name__ == "__main__":
    main()
