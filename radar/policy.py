"""Learnable policy: everything the weekend learn loop is allowed to change lives in policy/.
Code reads it at runtime, so a merged policy PR takes effect on the next tick."""
import json
import os

ROOT = os.getenv("POLICY_DIR", "policy")


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def load():
    p = json.loads(_read("policy.json"))
    p["rubric"] = _read("rubric.md").strip()
    p["style"] = _read("style.md").strip()
    p["examples"] = json.loads(_read("examples.json"))  # curated by the learn loop
    return p


def few_shot(p):
    """Approved/rejected examples injected into the scorer so taste carries over."""
    pos = [e for e in p["examples"] if e.get("label") == "approved"][-p.get("few_shot_positive", 3):]
    neg = [e for e in p["examples"] if e.get("label") == "rejected"][-p.get("few_shot_negative", 3):]
    if not (pos or neg):
        return ""
    lines = ["\nCalibration from the editor's past decisions:"]
    for e in pos:
        lines.append(f"- APPROVED as {e.get('tier')}: {e['title']} ({e.get('why', '')})")
    for e in neg:
        lines.append(f"- REJECTED: {e['title']} ({e.get('why', '')})")
    return "\n".join(lines)
