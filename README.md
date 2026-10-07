# ai-radar

Technical AI advancements, curated into a Telegram channel: mechanism, features, use cases, what it could replace, domains, where to learn, and a sample project for turning points. Runs on GitHub Actions every 15 minutes, human-approved, with a biweekly self-learn loop.

```
every 15 min (tick.yml)                                   biweekly (learn.yml + you)
┌──────────────────────────────────────────────┐          ┌─────────────────────────────────┐
│ your Telegram replies/taps ──► feedback.jsonl │─────────►│ radar.learn: metrics + misses + │
│ collect (GitHub, HF papers, HN, lab blogs)    │          │ rule-based suggestions (report) │
│ score (policy/rubric.md + examples) ─► log    │          │            │                    │
│ draft (policy/style.md) via Claude + Jev      │          │ Claude Code runs LEARN.md ──►   │
│ DM you both drafts ─► Post / Skip / fb / take │          │ PR editing policy/ only         │
└──────────────────────────────────────────────┘          └────────────┬────────────────────┘
                     ▲                                                  │ you merge
                     └──────────── next tick reads new policy/ ◄────────┘
```

**What learns:** only `policy/` (rubric, style, few-shot examples, thresholds, source weights). Code never rewrites itself; every change is a reviewable PR with a version bump, and every log line carries the policy version so the next report shows whether the change helped.

## Setup (~20 min)

1. **Repo:** create a public GitHub repo, push this folder. (Public = unlimited Actions minutes.)
2. **Bot:** in Telegram, message @BotFather → `/newbot` → copy the token.
3. **Channel:** create a public channel. Add the bot as **admin** with "Post messages". Reactions on the channel must be enabled for engagement signals.
4. **Your chat id:** message your bot anything, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `message.chat.id`. Do this before step 6 starts consuming updates.
5. **Repo settings → Secrets and variables → Actions:**
   - Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`, `ANTHROPIC_API_KEY`, `JEV_API_KEY`
   - Variables: `TELEGRAM_CHANNEL_ID` (e.g. `@your_channel`), `JEV_BASE_URL`, `JEV_MODEL`, optional `DRAFTERS` (`claude,jev` default), `AUTHOR_NAME`, `LEARN_EVERY_WEEKS` (`2` default, `1` for weekly)
   - Settings → Actions → General → Workflow permissions: **Read and write**.
6. **Test:** Actions → tick → Run workflow with *dry run* ticked. Check logs. Then run once without dry run; you should get a DM.

Jev is called as an OpenAI-compatible `/chat/completions` endpoint. If Typesafe's API differs, edit `_jev` in `radar/llm.py` (one function).

## Your controls (in the bot DM)

| Action | Signal it creates |
|---|---|
| ✅ Post (claude) / ✅ Post (jev) | approval + provider A/B win |
| ⏭ Skip | rejection |
| Reply to a draft with text | your take (appended to the post) |
| Reply `fb <why>` | critique note → rubric/style edits |
| Reply `/tier major` | tier correction → rubric boundaries |
| `/missed <url> [why]` | false negative → classified as collection gap or scoring miss |
| `/status` | policy version, queue, today's counts |

Taps are processed on the next tick, so expect up to ~15 min (plus GitHub's start delay) before a post appears.

## Learn loop
- `learn.yml` runs Saturday 08:00 IST on even weeks, writes `reports/learn-<date>.md/.json`, and DMs you a summary.
- Then in Claude Code: **"Run LEARN.md"**. It proposes at most 3 policy changes as a PR, each tied to evidence.
- Local: `python -m radar.learn --days 14`.

## Notes
- **Public repo = public logs.** `state/feedback.jsonl` (including your `fb` notes) and `reports/` are visible. Keep notes professional, or move state to a private store later.
- Costs: one cheap scoring call per tick with new items, two drafts per story, capped by `max_drafts_per_day` (policy).
- RSS URLs in `radar/config.py` should be checked once; a dead feed is skipped, never fatal.
