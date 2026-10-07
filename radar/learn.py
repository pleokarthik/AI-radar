"""Weekend learn loop, step 1: deterministic analysis of state/feedback.jsonl.

    python -m radar.learn [--days 14]

Writes reports/learn-<date>.md (for you) and reports/learn-<date>.json (for Claude Code).
It never edits policy/. Step 2 (LEARN.md) has Claude Code propose a policy PR from this report.

Observation vs inference: the report's "Metrics" sections are counts from the log.
"Suggestions" are rule-based hypotheses with their evidence count; low-n ones are flagged."""
import argparse
import json
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

from . import feedback as fb, policy as pol

MIN_N = 5  # below this, a suggestion is marked low-evidence


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "n/a"


def analyse(days):
    since = time.time() - days * 86400
    ev = fb.read(int(since))
    by = defaultdict(list)
    for e in ev:
        by[e["event"]].append(e)

    scored = by["scored"]
    decisions = by["decision"]
    pub_keys = {d["key"] for d in decisions if d["action"] == "publish"}
    skip_keys = {d["key"] for d in decisions if d["action"] == "skip"}

    r = {"window_days": days, "events": len(ev), "generated": datetime.now(timezone.utc).isoformat()}

    # funnel
    r["funnel"] = {
        "scored": len(scored),
        "scored_by_tier": dict(Counter(s["tier"] for s in scored)),
        "drafted": len(by["drafted"]),
        "published": len(pub_keys),
        "skipped": len(skip_keys),
        "undecided": len(by["drafted"]) - len(decisions),
    }

    # approval rate per tier and per source (precision of the scorer, judged by you)
    def rate(field):
        t = defaultdict(lambda: [0, 0])
        for d in decisions:
            k = d.get(field) or "?"
            if field == "source":
                k = k.split(" · ")[0]  # same key source_weights uses
            t[k][1] += 1
            t[k][0] += d["action"] == "publish"
        return {k: {"published": v[0], "decided": v[1], "rate": pct(*v)} for k, v in t.items()}
    r["approval_by_tier"] = rate("tier")
    r["approval_by_source"] = rate("source")

    # source yield: how much each source feeds vs how much survives
    src_scored = Counter(s["source"].split(" · ")[0] for s in scored)
    src_pub = Counter(d["source"].split(" · ")[0] for d in decisions if d["action"] == "publish")
    r["source_yield"] = {k: {"scored": n, "published": src_pub.get(k, 0)} for k, n in src_scored.most_common()}

    # provider A/B: only count decisions where >1 provider was offered
    ab = Counter(d["provider"] for d in decisions
                 if d["action"] == "publish" and len(d.get("providers_offered", [])) > 1)
    r["provider_wins"] = dict(ab)

    # tier corrections
    r["tier_corrections"] = dict(Counter(f"{w['given']}->{w['wanted']}" for w in by["wrongtier"]))

    # engagement: keep the latest reaction count per post
    react = {}
    for x in by["reactions"]:
        react[x["key"]] = x["total"]
    tier_of = {d["key"]: d["tier"] for d in decisions}
    prov_of = {d["key"]: d.get("provider") for d in decisions}
    def mean_by(m):
        g = defaultdict(list)
        for k, v in react.items():
            g[m.get(k, "?")].append(v)
        return {k: {"posts": len(v), "mean_reactions": round(sum(v) / len(v), 1)} for k, v in g.items()}
    r["reactions_by_tier"] = mean_by(tier_of)
    r["reactions_by_provider"] = mean_by(prov_of)

    # behaviour signals
    lat = sorted(d["secs_to_decide"] for d in decisions)
    r["median_minutes_to_decide"] = round(lat[len(lat) // 2] / 60) if lat else None
    r["take_rate"] = pct(sum(d["had_take"] for d in decisions if d["action"] == "publish"), len(pub_keys))

    # misses: classify each as a collection gap or a scoring miss
    scored_by_url = {s["url"].rstrip("/").lower(): s for s in scored if s.get("url")}
    misses = []
    for m in by["missed"]:
        hit = scored_by_url.get(m["url"].rstrip("/").lower())
        misses.append({
            "url": m["url"], "why": m.get("why", ""),
            "diagnosis": f"scoring miss: scored '{hit['tier']}' ({hit['reason']})" if hit
            else "collection gap: no source picked it up",
        })
    r["misses"] = misses

    r["notes"] = [{"title": n["title"], "tier": n["tier"], "source": n["source"], "note": n["text"]}
                  for n in by["note"]]

    # per policy version: did the last change help?
    pv = defaultdict(lambda: [0, 0])
    for d in decisions:
        pv[d["pv"]][1] += 1
        pv[d["pv"]][0] += d["action"] == "publish"
    r["approval_by_policy_version"] = {str(k): {"published": v[0], "decided": v[1], "rate": pct(*v)}
                                       for k, v in sorted(pv.items())}

    # candidate few-shot examples for policy/examples.json (Claude Code picks the best)
    title_of = {s["key"]: s for s in scored}
    note_of = {n["key"]: n["text"] for n in by["note"]}
    cands = []
    for d in decisions:
        if d["key"] in note_of or d["action"] == "publish" and react.get(d["key"], 0) > 0:
            cands.append({"title": d["title"], "tier": d["tier"],
                          "label": "approved" if d["action"] == "publish" else "rejected",
                          "why": note_of.get(d["key"], ""), "reactions": react.get(d["key"])})
    r["example_candidates"] = cands

    r["suggestions"] = suggest(r)
    return r


def suggest(r):
    out = []
    def add(text, n, kind):
        out.append({"kind": kind, "suggestion": text, "evidence_n": n, "low_evidence": n < MIN_N})

    for src, v in r["approval_by_source"].items():
        if v["decided"] >= 3 and v["published"] / v["decided"] < 0.25:
            add(f"Demote source '{src}' (source_weights -1) or raise its threshold: "
                f"{v['published']}/{v['decided']} approved.", v["decided"], "sources")
    for tier, v in r["approval_by_tier"].items():
        if v["decided"] >= 3 and v["published"] / v["decided"] < 0.3:
            add(f"Rubric too loose at '{tier}': {v['published']}/{v['decided']} approved. "
                f"Tighten its definition using the notes.", v["decided"], "rubric")
    for k, n in r["tier_corrections"].items():
        add(f"Tier corrections {k} x{n}: adjust rubric boundary.", n, "rubric")
    gaps = [m for m in r["misses"] if m["diagnosis"].startswith("collection")]
    if gaps:
        add(f"{len(gaps)} missed stories never collected: consider a new source.", len(gaps), "sources")
    smiss = [m for m in r["misses"] if m["diagnosis"].startswith("scoring")]
    if smiss:
        add(f"{len(smiss)} missed stories were scored too low: add them as approved examples.", len(smiss), "examples")
    if r["funnel"]["undecided"] > r["funnel"]["drafted"] * 0.4 and r["funnel"]["drafted"] >= 5:
        add("Over 40% of drafts left undecided: lower max_drafts_per_day.", r["funnel"]["drafted"], "volume")
    w = r["provider_wins"]
    if sum(w.values()) >= MIN_N:
        best = max(w, key=w.get)
        add(f"Provider '{best}' wins {w[best]}/{sum(w.values())} A/B picks: consider making it the only drafter "
            f"to halve draft cost.", sum(w.values()), "providers")
    if r["notes"]:
        add(f"{len(r['notes'])} free-text notes: read them for style.md and rubric.md edits.", len(r["notes"]), "style")
    return out


def to_markdown(r, p):
    L = [f"# Learn report · {r['generated'][:10]} · policy v{p['version']} · last {r['window_days']} days", ""]
    f = r["funnel"]
    L += ["## Funnel (observed)",
          f"Scored {f['scored']} → drafted {f['drafted']} → published {f['published']} "
          f"(skipped {f['skipped']}, undecided {f['undecided']})",
          f"Scored by tier: {f['scored_by_tier']}", ""]
    for title, key in (("Approval by tier", "approval_by_tier"), ("Approval by source", "approval_by_source"),
                       ("Approval by policy version", "approval_by_policy_version")):
        L.append(f"## {title} (observed)")
        L += [f"- {k}: {v['published']}/{v['decided']} ({v['rate']})" for k, v in r[key].items()] or ["- none yet"]
        L.append("")
    L += ["## Engagement (observed)",
          f"- by tier: {r['reactions_by_tier'] or 'no reaction data'}",
          f"- by provider: {r['reactions_by_provider'] or 'no reaction data'}",
          f"- provider A/B wins: {r['provider_wins'] or 'none'}",
          f"- median minutes to decide: {r['median_minutes_to_decide']}, take rate: {r['take_rate']}", ""]
    L.append("## Misses")
    L += [f"- {m['url']}: {m['diagnosis']}" + (f" · you said: {m['why']}" if m["why"] else "") for m in r["misses"]] \
        or ["- none logged"]
    L += ["", "## Your notes"]
    L += [f"- [{n['tier']}] {n['title']}: {n['note']}" for n in r["notes"]] or ["- none"]
    L += ["", "## Suggestions (inferred, rule-based; not applied)"]
    L += [f"- {'⚠️ low evidence · ' if s['low_evidence'] else ''}[{s['kind']}] {s['suggestion']} (n={s['evidence_n']})"
          for s in r["suggestions"]] or ["- nothing actionable yet"]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--notify", action="store_true", help="DM a summary to the admin chat")
    a = ap.parse_args()
    p = pol.load()
    r = analyse(a.days)
    os.makedirs("reports", exist_ok=True)
    stem = f"reports/learn-{r['generated'][:10]}"
    with open(stem + ".json", "w", encoding="utf-8") as f:
        json.dump(r, f, indent=1, ensure_ascii=False)
    md = to_markdown(r, p)
    with open(stem + ".md", "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    print(f"wrote {stem}.md and {stem}.json")
    if a.notify:
        from . import config, telegram as tg
        f = r["funnel"]
        tg.send(config.TELEGRAM_ADMIN_CHAT_ID,
                f"🧠 <b>Learn report ready</b> (policy v{p['version']}, {a.days}d)\n"
                f"Scored {f['scored']} → drafted {f['drafted']} → published {f['published']}\n"
                f"{len(r['suggestions'])} suggestion(s), {len(r['misses'])} miss(es), {len(r['notes'])} note(s).\n"
                f"Run the LEARN.md routine in Claude Code to turn it into a policy PR.")


if __name__ == "__main__":
    main()
