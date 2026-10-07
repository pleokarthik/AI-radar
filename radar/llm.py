"""Provider-agnostic LLM calls. Add a provider by adding one function to PROVIDERS."""
import json
import re

import requests

from . import config

TIMEOUT = 120


def _claude(system, user, model, max_tokens):
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=TIMEOUT, headers={
        "x-api-key": config.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }, json={
        "model": model, "max_tokens": max_tokens, "system": system,
        "messages": [{"role": "user", "content": user}],
    })
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")


def _jev(system, user, model, max_tokens):
    # Assumes an OpenAI-compatible /chat/completions endpoint. Adjust here if Typesafe's API differs.
    if not (config.JEV_API_KEY and config.JEV_BASE_URL and config.JEV_MODEL):
        raise RuntimeError("JEV_API_KEY / JEV_BASE_URL / JEV_MODEL not set")
    r = requests.post(config.JEV_BASE_URL.rstrip("/") + "/chat/completions", timeout=TIMEOUT, headers={
        "Authorization": f"Bearer {config.JEV_API_KEY}", "content-type": "application/json",
    }, json={
        "model": config.JEV_MODEL, "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    })
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


PROVIDERS = {"claude": _claude, "jev": _jev}


def call(provider, system, user, purpose="draft", max_tokens=1500):
    fn = PROVIDERS[provider]
    model = None
    if provider == "claude":
        model = config.CLAUDE_SCORE_MODEL if purpose == "score" else config.CLAUDE_DRAFT_MODEL
    return fn(system, user, model, max_tokens)


def extract_json(text):
    """Pull the first JSON object/array out of a model reply."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i != -1], default=-1)
    if start == -1:
        raise ValueError("no JSON in reply")
    return json.loads(text[start:text.rfind("]" if text[start] == "[" else "}") + 1])
