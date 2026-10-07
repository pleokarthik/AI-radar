"""Fixed output contracts live here (code depends on them). Learnable judgment lives in policy/."""
from . import policy as pol

SCORE_CONTRACT = """
Return ONLY a JSON array: [{"key": "...", "tier": "skip|notable|major|turning_point", "reason": "<=15 words", "dup_of": null}]"""

DRAFT_FORMAT = """
Format exactly:
<b>{emoji} {title}</b>
<i>{source} · {tier_label}</i>

<b>Mechanism:</b> 2-3 lines on how it works.
<b>Features:</b>
• ...
• ...
• ...
<b>Use cases:</b> 2-3 concrete ones, one line.
<b>Could replace:</b> one line.
<b>Domains:</b> comma-separated industries.
<b>Learn:</b> <a href="{url}">primary source</a>
"""

SAMPLE_PROJECT = "<b>Sample project:</b> a weekend-sized build that exercises the core mechanism, 2 lines.\n"

SCORE_USER = "Items:\n{items}"

DRAFT_USER = """TITLE: {title}
SOURCE: {source}
URL: {url}
SIGNAL: {signal}
TIER: {tier}

SOURCE TEXT:
{text}"""


def score_system(p):
    return p["rubric"] + pol.few_shot(p) + SCORE_CONTRACT


def draft_system(p, tier):
    return p["style"] + DRAFT_FORMAT + (SAMPLE_PROJECT if tier == "turning_point" else "")
