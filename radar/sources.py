"""Collectors. Each returns a list of Item dicts; any failure is logged and returns [] so one dead source never breaks a tick."""
import hashlib
import os
import re
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from . import config

UA = {"User-Agent": "ai-radar/0.1 (+github actions)"}
TIMEOUT = 20


def _item(source, title, url, summary="", signal=""):
    key = hashlib.sha1(_norm_url(url).encode()).hexdigest()[:16]
    return {
        "key": key,
        "source": source,
        "title": (title or "").strip()[:300],
        "url": url,
        "summary": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", summary or "")).strip()[:1500],
        "signal": signal,  # human-readable adoption signal, e.g. "212 HF upvotes"
    }


def _norm_url(u):
    u = (u or "").split("#")[0].split("?")[0].rstrip("/").lower()
    return u.replace("http://", "https://").replace("://www.", "://")


def _safe(fn):
    def wrap():
        try:
            items = fn()
            print(f"[source] {fn.__name__}: {len(items)}")
            return items
        except Exception as e:  # noqa: BLE001
            print(f"[source] {fn.__name__} FAILED: {e!r}")
            return []
    return wrap


@_safe
def github_releases():
    headers = dict(UA)
    tok = os.getenv("GITHUB_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    out = []
    for repo in config.GITHUB_RELEASE_REPOS:
        r = requests.get(f"https://api.github.com/repos/{repo}/releases?per_page=3", headers=headers, timeout=TIMEOUT)
        if r.status_code != 200:
            print(f"  gh {repo}: HTTP {r.status_code}")
            continue
        for rel in r.json():
            if rel.get("draft") or rel.get("prerelease"):
                continue
            pub = rel.get("published_at") or ""
            if pub and datetime.fromisoformat(pub.replace("Z", "+00:00")) < cutoff:
                continue
            out.append(_item(f"GitHub · {repo}", f"{repo} {rel.get('name') or rel.get('tag_name')}",
                             rel["html_url"], rel.get("body") or "", "release"))
    return out


@_safe
def hf_daily_papers():
    r = requests.get("https://huggingface.co/api/daily_papers", headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for p in r.json():
        paper = p.get("paper", {})
        up = paper.get("upvotes", 0) or 0
        if up < config.HF_MIN_UPVOTES:
            continue
        pid = paper.get("id")
        out.append(_item("HF Daily Papers", paper.get("title") or p.get("title"),
                         f"https://huggingface.co/papers/{pid}", paper.get("summary", ""), f"{up} HF upvotes"))
    return out


@_safe
def hacker_news():
    since = int((datetime.now(timezone.utc) - timedelta(days=2)).timestamp())
    seen, out = set(), []
    for kw in config.HN_KEYWORDS:
        r = requests.get("https://hn.algolia.com/api/v1/search_by_date", headers=UA, timeout=TIMEOUT, params={
            "query": kw, "tags": "story",
            "numericFilters": f"points>{config.HN_MIN_POINTS},created_at_i>{since}",
            "hitsPerPage": 10,
        })
        r.raise_for_status()
        for h in r.json().get("hits", []):
            if h["objectID"] in seen:
                continue
            seen.add(h["objectID"])
            url = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
            out.append(_item("Hacker News", h.get("title"), url, "", f"{h.get('points')} HN points"))
    return out


@_safe
def rss():
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    out = []
    for name, url in config.RSS_FEEDS.items():
        try:
            f = feedparser.parse(requests.get(url, headers=UA, timeout=TIMEOUT).content)
        except Exception as e:  # noqa: BLE001
            print(f"  rss {name} failed: {e!r}")
            continue
        for e in f.entries[:10]:
            t = e.get("published_parsed") or e.get("updated_parsed")
            if t and datetime(*t[:6], tzinfo=timezone.utc) < cutoff:
                continue
            out.append(_item(name, e.get("title"), e.get("link"), e.get("summary", ""), "official blog"))
    return out


def collect_all():
    items = []
    for fn in (github_releases, hf_daily_papers, hacker_news, rss):
        items.extend(fn())
    return items


def fetch_page_text(url, limit=8000):
    """Best-effort grounding text for drafting. Falls back to '' on failure."""
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        if "html" not in r.headers.get("content-type", ""):
            return ""
        html = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", r.text)
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
        return text[:limit]
    except Exception:  # noqa: BLE001
        return ""
