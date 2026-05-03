## Context

`CronService` (`mybot/cron/service.py`) is designed as a self-arming async loop: `start()` schedules its next wake, `_on_timer()` fires due jobs by calling the user-supplied `on_job` coroutine, then re-arms. `HeartbeatService` (`mybot/heartbeat/service.py`) is similar: `start()` spawns `_run_loop()` which sleeps `interval_s` and calls `_tick()`, which decides skip/run via an LLM tool call and then invokes `on_execute` + `on_notify` callbacks. Both services are async, both stop cleanly via `stop()`.

`AgentLoop` already exposes `process_direct(content, session_key, channel, chat_id, on_progress)` — the same entry point the cron `run` CLI command uses. So daemon hosting is "wire callbacks, await tasks, handle signals."

The previous nanobot `gateway` command did exactly this, plus chat-channel listeners. We removed channels but threw out the supervisor with them. This change brings the supervisor back, scoped to a single bot.

## Goals / Non-Goals

**Goals**

- A foreground process that fires both timers reliably for one bot.
- Streamed, timestamped output of every cron / heartbeat result, suitable for `tail -f` and journald.
- Clean shutdown on SIGINT/SIGTERM — no zombie agent tasks, MCP connections closed.
- Composable with OS supervisors (systemd `--user`, launchd `LaunchAgents`).
- Same daemon binary supports a `--once` mode for cron-from-OS setups (run every due job, then exit).

**Non-Goals**

- Multi-bot supervision in a single process. Each bot is its own daemon.
- HTTP/RPC control surface or status endpoint.
- Daemonization (forking to background). User's supervisor handles that.
- Live config reload of provider / model / interval (only cron `jobs.json` is hot-reloaded by the existing `CronService` mtime check).

## Decisions

### 1. Single bot per daemon process

Two patterns considered:

- **One daemon, many bots** (orchestrator). Pro: single supervisor entry. Con: failure of one bot affects others, log streams interleave, signal semantics ambiguous.
- **One daemon, one bot.** Pro: trivially isolated, supervised by OS, natural mapping (`mybot work daemon` ↔ `mybot-daemon@work.service`). Con: user has to start N processes for N bots.

Chose one-bot. The orchestration cost (running a few `systemctl --user enable mybot-daemon@<name>` commands) is much smaller than the failure-isolation cost of bundling.

### 2. Foreground only

We don't fork. SIGINT works as expected. `systemd` and `launchd` both want foreground processes (they handle PID tracking themselves). `nohup mybot work daemon &` works for ad-hoc background. Daemonization libraries (`python-daemon`, etc.) add a dependency for nothing.

### 3. Output format: timestamped lines, prefixed by job source

```
2026-05-03 16:42:00 [cron:1a2b3c4d]  ↳ web_search("…")
2026-05-03 16:42:08 [cron:1a2b3c4d]  Today's standup: ...
2026-05-03 17:00:00 [heartbeat]      Reviewing HEARTBEAT.md…
2026-05-03 17:00:09 [heartbeat]      Inbox check: 3 urgent.
```

Reasons:
- Distinguishes cron vs heartbeat at a glance.
- Cron jobs include their ID for cross-reference with `mybot <bot> cron list`.
- Plain text streams to `journald`, `Console.app`, `tail -f` without ceremony.
- Tool-progress lines (`↳ ...`) are dimmed via Rich just like in the interactive agent.

We use `rich.console.Console` so terminal output is colored when attached to a TTY and plain when piped (Rich's auto-detect handles this). No JSON output mode in v1.

### 4. SIGTERM and SIGINT both shut down

We register handlers via `loop.add_signal_handler(signal.SIGINT, ...)` and the same for SIGTERM. Both:
1. Set `_running = False` (shared atomic via asyncio.Event).
2. Stop `cron`, `heartbeat`, then `agent.stop()`.
3. Wait up to 30 s for in-flight `agent.process_direct` to complete or be cancelled.
4. `await agent.close_mcp()`.
5. Exit 0.

If a second signal arrives during shutdown, exit immediately (force quit).

### 5. `--once` runs every currently-due job and exits

Implemented by:
1. Loading the cron store.
2. Scanning for jobs with `next_run_at_ms <= now`.
3. Running them sequentially through the same `on_job` callback.
4. Skipping the heartbeat (since `--once` is for cron-from-OS use cases; the heartbeat check is cheap to skip).

This makes `* * * * * mybot work daemon --once` (in system crontab) a viable alternative to a long-running daemon for users who already have OS cron configured.

### 6. Logging via `rich.console.Console.print` directly, not loguru

`loguru` is project-wide and currently disabled by default in the CLI. The daemon's output is *not* diagnostic logging — it's the bot's actual responses, meant for the user to read. Keeping it on `Console.print` means it's always visible regardless of `--logs`. Diagnostic logs (DEBUG-level loop internals) are still loguru-gated by `--logs`.

### 7. The cron-job session key uses the job ID

`session_key=f"cron:{job.id}"`, matching the existing `cron run` behavior. This keeps each scheduled job's conversation history separate from the user's main session, so a daily standup job and a weekly digest job don't pollute each other's context.

### 8. Heartbeat target

The pre-existing nanobot heartbeat picked the most-recently-active *channel* to deliver to. With no channels, the daemon delivers heartbeat output to its own stdout. The `on_notify` callback collapses to a print.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| User runs two daemons against the same bot data dir → cron jobs may double-fire | Add a PID lockfile at `<data_dir>/daemon.pid` on startup; refuse to start if a live PID owns it. (See task 5.x.) |
| MCP servers can hang on shutdown (the SDK's cancel-scope cleanup is noisy) | Guarded `try/except` around `close_mcp`, and a 30 s overall shutdown deadline before `os._exit`. |
| Long-running cron job exceeds heartbeat interval, leading to overlap | `_processing_lock` in `AgentLoop` already serializes message processing, so the heartbeat will wait. Acceptable. |
| `--once` mode exits before in-flight tool calls complete | We `await` each job sequentially, so it's not actually possible to exit mid-job. The exit happens after the last `on_job` returns. |
| Cron `jobs.json` written by another `mybot cron add` is loaded mid-tick | Existing mtime check in `CronService._load_store` handles this — it reloads on next tick. |
| If the bot has no API key, the daemon starts but every job will fail | Daemon checks for an API key on startup (same `_make_provider` path) and exits 1 with a clear message before entering the loop. |
| Output to journald includes ANSI escapes from Rich | Rich auto-detects non-TTY and disables color when piped. journald sees plain text. |
| Heartbeat fires while `--once` is running (race during shutdown) | `--once` never starts the heartbeat service. |
