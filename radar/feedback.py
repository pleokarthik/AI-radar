"""Append-only signal log (state/feedback.jsonl). The learn loop reads only this file + policy/.
Every event carries policy_version so before/after comparisons are possible.

Events:
  scored      every item the scorer saw, incl. skips (key, source, title, tier, reason)
  drafted     story sent to you for review (key, tier, providers, chars per provider)
  decision    you tapped Post or Skip (key, action, provider, secs_to_decide, had_take)
  take        you replied with your take
  note        you replied "fb ..." to a draft: free-text critique of the draft or tier
  missed      /missed <url> [why]: a story the system should have caught (false negative)
  wrongtier   /tier <tier> as a reply to a draft: what the tier should have been
  reactions   channel reaction counts for a published post
"""
import json
import os
import time

PATH = os.getenv("FEEDBACK_PATH", "state/feedback.jsonl")


def log(event, policy_version, **fields):
    rec = {"ts": int(time.time()), "event": event, "pv": policy_version, **fields}
    os.makedirs(os.path.dirname(PATH) or ".", exist_ok=True)
    with open(PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read(since_ts=0):
    if not os.path.exists(PATH):
        return []
    out = []
    with open(PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                if r["ts"] >= since_ts:
                    out.append(r)
    return out
