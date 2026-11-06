# claude-code-config

My Claude Code status line and compaction settings. [中文](README.zh-CN.md)

Files:

- `statusline.py` — status line script (Python 3, standard library only).
- `settings.example.json` — the relevant parts of `~/.claude/settings.json`.

## Install

```bash
cp statusline.py ~/.claude/statusline.py
# then merge settings.example.json into ~/.claude/settings.json
```

Developed against Claude Code 2.1.318–2.1.319. The script reads the JSON that Claude Code pipes to a status line command on stdin, and prints one line. If anything fails it falls back to printing the current directory.

## What the status line shows

```
/path/to/project │ Opus 5.5 high │ ctx 142k/300k +8.2k ic:100k │ cache 97% warm 54m ic 3m │ 5h 31% 2h10m · 7d 12% 5d3h
```

| Segment | Meaning |
|---|---|
| workdir | The directory the session started in (`project_dir`); a `cd` in Bash does not change it. |
| model + effort | Display name and live effort level. |
| `ctx A/B` | Context size `A` against the **auto-compact point** `B`, not the 1M window. Green < 50%, yellow < 80%, red above. `+N` is the cache-creation tokens of the last request. |
| `ic:100k` | Idle-compaction threshold. Dim = context too small for it to fire; **green** = context is large enough. `ic:off` = disabled. |
| `cache N%` | Prompt-cache hit ratio of the last request. |
| `TTL5m` | The cache TTL is 5 minutes, not 1 hour (idle compaction needs 1h). |
| `warm 54m` | Time until the prompt cache expires. |
| `ic 3m` | Time until idle compaction fires (only shown when it will). `ic due` = about to fire. |
| `cmp` | Just compacted; the cached prefix is stale, so countdowns are hidden. |
| `COLD next +Nk` | Cache expired; the next message re-caches N tokens. |
| `miss N` | Number of cache misses so far. |
| `5h` / `7d` | Subscription rate-limit usage and time to reset. |
| `?` / `!` | Rate-limit warning is active: Claude Code skips idle compaction while a window is flagged near its limit. `!` marks the window, `?` marks the ic countdown. |

## Compaction settings

**Auto-compact point** (where the `/B` in `ctx` comes from). Precedence:

1. env `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (clamped to ≥ 100k)
2. `modelSettings["<model-id>"].autoCompactWindow`
3. top-level `autoCompactWindow`
4. default — about 967k on a 1M window, otherwise the window size

I set it to 300k for Opus and Sonnet: a long context is slow and costly, so I would rather compact early.

**Idle compaction** — as implemented in 2.1.318 (observed behaviour, not official documentation):

- needs a 1h prompt-cache TTL;
- needs context ≥ `max(100k, CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS)`; the default is 200k;
- fires at 90% of the TTL after the last request (≈ 54 min of a 1h TTL);
- is skipped while the rate-limit status is not "allowed". The client derives this from (used fraction, elapsed fraction of window) pairs:
  - 5h window: ≥ 90% used within the first 72% of the window;
  - 7d window: ≥ 75% used in the first 60%, ≥ 50% in the first 35%, or ≥ 25% in the first 15%.

  The server can also flag a window, which the status line cannot see — so no `?` does not guarantee the compaction runs.

I lower `CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS` to 100k (the floor) so smaller sessions are also compacted while idle. The status line reads this from the environment Claude Code passes it, so a settings change shows up only after the session picks it up.

## Per-model settings

`modelSettings` also takes `effortLevel` per model; `settings.example.json` sets Opus to `high`.

Not included on purpose: permission mode, sandbox flags and other personal environment choices.
