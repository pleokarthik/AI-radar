# Learn routine (run in Claude Code, weekend or biweekly)

Paste into Claude Code from the repo root: **"Run LEARN.md"**.

## Contract
- Only files under `policy/` may change. Never edit `radar/` code in this routine; code changes are a separate, normal PR.
- Work on a branch `learn/v<next>` and open a PR. Never push to `main`.
- At most **3 changes** per cycle, so the next report can attribute any effect to them.
- Every change must cite evidence from the report (counts, notes, misses). No change on evidence_n < 5 unless it comes from an explicit note or `/tier` correction by the editor.
- Separate in the PR body: **Observed** (numbers) → **Inferred** (what they suggest) → **Change** (diff) → **How we'll know** (which metric should move next cycle).

## Steps
1. `git pull`, then `python -m radar.learn --days 14`. Read the newest `reports/learn-*.md` and `.json`.
2. Compare `approval_by_policy_version` for the current and previous version. If the last change made approval or engagement worse with n >= 5, the first proposal is a revert.
3. Pick up to 3 changes, in this priority:
   1. Misses diagnosed as **scoring miss** → add to `policy/examples.json` as `approved` with the editor's `why`.
   2. Editor notes and `/tier` corrections → edit `policy/rubric.md` boundaries or `policy/style.md` rules. Quote the note in the PR.
   3. Low-approval sources/tiers → `source_weights` (-1 demotes one tier) or thresholds in `policy/policy.json`.
   4. Collection gaps → list candidate sources in the PR body only (adding a source is a code change).
4. Curate `policy/examples.json`: keep it to at most 12 entries (6 approved, 6 rejected), prefer ones with a `why`. Format: `{"title","tier","label":"approved|rejected","why"}`.
5. Bump `version` in `policy/policy.json` and append a `changelog` entry `{version, date, change}`.
6. Dry check: `python -c "from radar import policy, prompts; p=policy.load(); print(prompts.score_system(p))"` and read the result for contradictions.
7. Commit, push branch, open PR titled `learn: policy v<next>`.

## What not to do
- Don't loosen the "only facts from source text" rule in `style.md` to make drafts read better.
- Don't tune toward reactions alone; with a small channel, a few reactions are noise. Approval rate is the primary signal until the channel has ~500 subscribers.
