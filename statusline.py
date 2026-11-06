#!/usr/bin/env python3
"""Claude Code status line: workdir | context vs compaction points | prompt cache | rate limits."""
import json
import os
import re
import sys
import time

RESET = "\033[0m"
DIM = "\033[2m"
BOLD_BLUE = "\033[01;34m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
SEP = f" {DIM}│{RESET} "

# Idle compaction, as Claude Code 2.1.318 runs it: it needs a 1h cache TTL and a context of at least
# max(100k, CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS or 200k), and fires at 90% of the TTL after the last request.
IDLE_MIN_DEFAULT = 200_000
IDLE_MIN_FLOOR = 100_000
IDLE_FIRE_FRACTION = 0.9
TTL_SECONDS = {"5m": 300, "1h": 3600}

# Idle compaction is also skipped while the rate-limit status is not "allowed". 2.1.318 derives that warning
# on the client from these (used fraction, elapsed fraction of the window) pairs when a response arrives,
# and keeps it until the next response. The server can flag a window as well; the status line cannot see
# that flag, so no "?" does not guarantee the compaction runs.
WARN_RULES = {
    "five_hour": (18_000, ((0.90, 0.72),)),
    "seven_day": (604_800, ((0.75, 0.60), (0.50, 0.35), (0.25, 0.15))),
}


def fmt_tokens(n):
    if n is None:
        return "—"
    n = int(n)
    if n < 1000:
        return str(n)
    if n < 10_000:
        return f"{n / 1000:.1f}k"
    if n < 1_000_000:
        return f"{n / 1000:.0f}k"
    return f"{n / 1e6:.2f}M"


def fmt_minutes(sec):
    m = max(0, int(sec // 60))
    return f"{m // 60}h{m % 60:02d}m" if m >= 60 else f"{m}m"


def fmt_duration(sec):
    if sec >= 86_400:
        h = int(sec // 3600)
        return f"{h // 24}d{h % 24}h"
    return fmt_minutes(sec)


def near_limit(window, key, at):
    """True when Claude Code's own rule marks this rate-limit window as near its limit, judged at time `at`."""
    span, rules = WARN_RULES[key]
    pct, resets = window.get("used_percentage"), window.get("resets_at")
    if pct is None or not resets:
        return False
    elapsed = min(1.0, max(0.0, (at - (resets - span)) / span))
    return any(pct / 100 >= used and elapsed <= time_frac for used, time_frac in rules)


def parse_window(value):
    if value is None or value == "auto":
        return None
    try:
        if isinstance(value, str):
            s = value.strip().lower()
            if s.endswith("k"):
                return int(float(s[:-1]) * 1000)
            if s.endswith("m"):
                return int(float(s[:-1]) * 1_000_000)
            return int(s)
        return int(value)
    except (TypeError, ValueError):
        return None


def truthy(value):
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def load_settings():
    try:
        with open(os.path.expanduser("~/.claude/settings.json")) as f:
            return json.load(f)
    except Exception:
        return {}


def compact_window(settings, model_id, window_size):
    """Auto-compact point: env var > per-model setting > top-level setting > default."""
    env = parse_window(os.environ.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW"))
    if env:
        return min(max(env, 100_000), window_size or env)
    canon = re.sub(r"-\d{8}$", "", (model_id or "").split("[")[0])
    per_model = (settings.get("modelSettings") or {})
    for key in (model_id, canon):
        w = parse_window((per_model.get(key) or {}).get("autoCompactWindow"))
        if w:
            return min(w, window_size or w)
    w = parse_window(settings.get("autoCompactWindow"))
    if w:
        return min(w, window_size or w)
    if window_size == 1_000_000:
        return 967_000
    return window_size


def idle_compact_min(settings):
    """Context size idle compaction needs, or None when it is turned off.

    Reads the environment Claude Code passed to this script, which is the one Claude Code itself uses,
    so a settings.json change shows here only once the running session has picked it up.
    """
    if truthy(os.environ.get("DISABLE_COMPACT")) or truthy(os.environ.get("DISABLE_AUTO_COMPACT")):
        return None
    if settings.get("autoCompactEnabled") is False or settings.get("idleCompaction") is False:
        return None
    configured = parse_window(os.environ.get("CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS"))
    return max(IDLE_MIN_FLOOR, configured or IDLE_MIN_DEFAULT)


def level_color(ratio, warn=0.5, alert=0.8):
    return GREEN if ratio < warn else (YELLOW if ratio < alert else RED)


def countdown_color(left):
    return GREEN if left > 15 * 60 else YELLOW


def main():
    raw = sys.stdin.read()
    try:
        d = json.loads(raw) if raw.strip() else {}
    except Exception:
        d = {}
    settings = load_settings()
    now = time.time()
    parts = []

    # The directory the session was started in (project_dir), which a `cd` in Bash does not change.
    ws = d.get("workspace") or {}
    workdir = ws.get("project_dir") or ws.get("current_dir") or d.get("cwd") or os.getcwd()
    parts.append(f"{BOLD_BLUE}{workdir}{RESET}")

    # Model and its live effort level (effort is absent when the model does not support it).
    model = d.get("model") or {}
    name = model.get("display_name") or model.get("id")
    if name:
        effort = (d.get("effort") or {}).get("level")
        parts.append(f"{name} {DIM}{effort}{RESET}" if effort else name)

    # Context size against the auto-compact point (used_percentage is against the full 1M window),
    # plus the idle-compaction (ic) threshold: green once the context is big enough for it to fire.
    cw = d.get("context_window") or {}
    cu = cw.get("current_usage")
    model_id = (d.get("model") or {}).get("id")
    window = compact_window(settings, model_id, cw.get("context_window_size"))
    idle_min = idle_compact_min(settings)
    ctx = None
    if cu:
        ctx = (cu.get("input_tokens") or 0) + (cu.get("cache_creation_input_tokens") or 0) + (
            cu.get("cache_read_input_tokens") or 0)
        written = cu.get("cache_creation_input_tokens") or 0
        color = level_color(ctx / window) if window else ""
        seg = f"ctx {color}{fmt_tokens(ctx)}{RESET}/{fmt_tokens(window)}"
        if written >= 1000:
            seg += f" {DIM}+{fmt_tokens(written)}{RESET}"
    else:
        seg = f"ctx {DIM}—{RESET}/{fmt_tokens(window)}"
    if idle_min is None:
        seg += f" {DIM}ic:off{RESET}"
    elif ctx is not None and ctx >= idle_min:
        seg += f" {GREEN}ic:{fmt_tokens(idle_min)}{RESET}"
    else:
        seg += f" {DIM}ic:{fmt_tokens(idle_min)}{RESET}"
    parts.append(seg)

    # Prompt cache: hit ratio, then one of: just compacted (cmp) / warm countdown (+ idle-compaction (ic)
    # countdown when it will fire) / what the next message re-caches when cold.
    pc = d.get("prompt_cache")
    rl = d.get("rate_limits") or {}
    # The warning is judged when a response arrives; expires_at minus the TTL is about when the last one did.
    judged_at = now
    if pc and pc.get("expires_at") and TTL_SECONDS.get(pc.get("ttl")):
        judged_at = pc["expires_at"] - TTL_SECONDS[pc["ttl"]]
    near = {k for k in WARN_RULES if rl.get(k) and near_limit(rl[k], k, judged_at)}
    mark = "?" if near else ""
    if pc:
        hit = pc.get("hit_ratio")
        seg = "cache " + (f"{hit * 100:.0f}%" if hit is not None else "—")
        ttl = pc.get("ttl")
        if ttl == "5m":
            seg += f" {YELLOW}TTL5m{RESET}"
        expires = pc.get("expires_at")
        left = (expires - now) if expires else None
        warm = bool(pc.get("warm")) and left is not None and left > 0
        if pc.get("requests") and pc.get("recache_tokens_if_cold") is None:
            # Right after a compaction: the cached prefix is stale and the next request writes the
            # compacted context, so the old countdown no longer means anything.
            seg += f" {GREEN}cmp{RESET}"
        elif warm:
            seg += f" {countdown_color(left)}warm {fmt_minutes(left)}{RESET}"
            ttl_s = TTL_SECONDS.get(ttl)
            if ttl == "1h" and idle_min is not None and ctx is not None and ctx >= idle_min:
                idle_left = left - ttl_s * (1 - IDLE_FIRE_FRACTION)
                if idle_left > 0:
                    color = YELLOW if near else countdown_color(idle_left)
                    seg += f" {color}ic {fmt_minutes(idle_left)}{mark}{RESET}"
                else:
                    seg += f" {YELLOW}ic due{mark}{RESET}"
        else:
            recache = pc.get("recache_tokens_if_cold")
            seg += f" {RED}COLD{RESET}"
            if recache:
                seg += f" {RED}next +{fmt_tokens(recache)}{RESET}"
        misses = pc.get("misses") or 0
        if misses:
            seg += f" {YELLOW}miss {misses}{RESET}"
        parts.append(seg)

    # Subscription rate limits; "!" marks the window that makes Claude Code skip idle compaction.
    limits = []
    for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
        w = rl.get(key)
        if not w or w.get("used_percentage") is None:
            continue
        pct = w["used_percentage"]
        if key in near:
            seg = f"{label} {RED}{pct:.0f}%!{RESET}"
        else:
            seg = f"{label} {level_color(pct / 100)}{pct:.0f}%{RESET}"
        if w.get("resets_at"):
            seg += f" {DIM}{fmt_duration(w['resets_at'] - now)}{RESET}"
        limits.append(seg)
    if limits:
        parts.append(" · ".join(limits))

    sys.stdout.write(SEP.join(parts))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stdout.write(os.getcwd())
