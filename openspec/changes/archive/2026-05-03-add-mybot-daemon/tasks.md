## 1. Daemon command scaffold (single bot per daemon process; foreground only)

- [x] 1.1 Add `RESERVED_COMMANDS.add("daemon")` in mybot/cli/commands.py — implements the modified Chained subcommand passthrough requirement so `mybot work daemon` chains correctly (single bot per daemon process)
- [x] 1.2 Add `@app.command("daemon")` with options `--once/-1` (bool, default False) and `--log-file/-l PATH` (optional). Foreground only — no fork/daemonize
- [x] 1.3 Stub the function body with `console.print("daemon: not yet implemented")` so chained dispatch (`mybot work daemon`) lands here
- [x] 1.4 Verify chat-shortcut chain: `mybot work daemon` reaches the new command (smoke-test by adding a print) — covers the Chained subcommand passthrough scenarios

## 2. PID lockfile (PID lockfile prevents double-start)

- [x] 2.1 Add `_acquire_lockfile(data_dir: Path) -> Path` helper that writes `os.getpid()` to `<data_dir>/daemon.pid` and registers an atexit cleanup — implements the PID lockfile prevents double-start requirement
- [x] 2.2 If the file exists with a live PID (use `os.kill(pid, 0)` probe), exit 1 with `Daemon already running for '<bot>' (pid <N>)`
- [x] 2.3 If the file exists but the PID is dead, overwrite it
- [x] 2.4 Skip lockfile acquisition entirely when `--once` is set
- [x] 2.5 Remove the lockfile in the `finally` block of the daemon's main coroutine

## 3. Service wiring (the cron-job session key uses the job id; heartbeat target)

- [x] 3.1 In the daemon body: load config, call `_make_provider(config)`, build `AgentLoop`, `CronService`, `HeartbeatService` (mirroring the existing `gateway` body that was removed) — implements the Run cron and heartbeat for one bot requirement
- [x] 3.2 Wire `cron.on_job` → coroutine that calls `agent.process_direct(job.payload.message, session_key=f"cron:{job.id}", channel="cli", chat_id="direct")` and returns the response string — the cron-job session key uses the job id
- [x] 3.3 Wire `heartbeat.on_execute` → coroutine that calls `agent.process_direct(tasks, session_key="heartbeat", channel="cli", chat_id="direct")` — heartbeat target is the daemon's stdout
- [x] 3.4 Wire `heartbeat.on_notify` → coroutine that prints the response via the formatter from task 4
- [x] 3.5 Construct `HeartbeatService` with `interval_s=config.gateway.heartbeat.interval_s`, `enabled=config.gateway.heartbeat.enabled`

## 4. Output formatter (Output format: timestamped lines, prefixed by job source; Logging via `rich.console.Console.print` directly, not loguru)

- [x] 4.1 Add `_emit(source: str, content: str, *, dim: bool = False)` helper that prints `<YYYY-MM-DD HH:MM:SS> [<source>] <content>` via `console.print` (rich, not loguru), with `[dim]…[/dim]` markup when `dim=True` — implements the Output format requirement
- [x] 4.2 In the cron `on_job` callback, after the agent call, call `_emit(f"cron:{job.id}", response)` for the final answer; pass an `on_progress` callback to `process_direct` that calls `_emit(f"cron:{job.id}", content, dim=True)` for tool hints
- [x] 4.3 Same pattern for the heartbeat callbacks but with `source="heartbeat"`
- [x] 4.4 Emit `_emit("daemon", f"Daemon started for bot '<name>' (cron jobs: N, heartbeat: every Ns)")` at startup
- [x] 4.5 Emit `_emit("daemon", "Shutting down…")` on signal receipt
- [x] 4.6 If `--log-file` is given, configure a Rich `Console(file=...)` tee so output goes both to stdout and the file (no rotation)

## 5. Signal handling and shutdown (SIGTERM and SIGINT both shut down)

- [x] 5.1 Use `loop.add_signal_handler(SIGINT, …)` and `SIGTERM` to set a shared `asyncio.Event` named `_shutdown` — implements Graceful shutdown / SIGTERM and SIGINT both shut down requirement
- [x] 5.2 Main coroutine: `await asyncio.wait([_shutdown.wait(), agent_run_task, …], return_when=FIRST_COMPLETED)`
- [x] 5.3 On shutdown: stop heartbeat, stop cron, call `agent.stop()`, await active tasks with `asyncio.wait_for(..., timeout=30.0)`
- [x] 5.4 In `finally`: `await agent.close_mcp()` inside try/except for the known SDK cancel-scope BaseExceptionGroup
- [x] 5.5 Track second-signal: if `_shutdown` is already set when another signal fires, call `os._exit(1)` immediately
- [x] 5.6 Remove lockfile in the same `finally` as MCP close

## 6. --once mode (`--once` runs every currently-due job and exits)

- [x] 6.1 Branch early in the daemon body when `once=True` — implements the --once flag requirement
- [x] 6.2 Build cron + agent (no heartbeat, no agent bus consumer) — call `agent._connect_mcp()` directly
- [x] 6.3 Load `cron._load_store()`, filter jobs where `next_run_at_ms <= _now_ms()`
- [x] 6.4 For each due job: invoke the same `on_job` coroutine sequentially
- [x] 6.5 Call `cron._save_store()` to persist advanced next-run times
- [x] 6.6 Close MCP and exit 0 (no signal handlers needed for a one-shot)
- [x] 6.7 If no jobs due, print nothing and exit 0

## 7. API-key preflight

- [x] 7.1 At daemon entry (both regular and `--once`), call `_make_provider(config)` inside a try/except that catches `typer.Exit` and exits 1 with the existing error message before any service is started
- [x] 7.2 Verify behavior: bot with empty `providers.openrouter.apiKey` and no other keys → daemon exits 1 quickly

## 8. README updates

- [x] 8.1 Remove "`mybot daemon`" from the README roadmap section
- [x] 8.2 Add a new top-level `## Running as a daemon` section with the basic invocation, `--once`, and stdout format example
- [x] 8.3 Add subsection: **systemd (Linux)** — copy of the existing nanobot template adapted to `mybot work daemon`, with bot-name templating via `mybot-daemon@<name>.service`
- [x] 8.4 Add subsection: **launchd (macOS)** — `~/Library/LaunchAgents/com.mybot.<name>.plist` example
- [x] 8.5 Cross-link `cron list` / `set-folder` from the daemon section so users discover related commands

## 9. Manual smoke verification

- [x] 9.1 `mybot create scratch --folder /tmp/mybot-scratch` → success
- [x] 9.2 `mybot scratch cron add --name tick --message "hi" --every 60` → success
- [x] 9.3 `mybot scratch daemon` (with API key configured) — observe one cron tick within 70 s, observe shutdown on Ctrl-C in <1 s
- [x] 9.4 `mybot scratch daemon --once` after a fresh `cron add --every 60` — observe the job fires, jobs.json's nextRunAtMs advances, exit 0
- [x] 9.5 Run two daemons against the same bot — second exits 1 with PID message
- [x] 9.6 Tear down: `mybot delete scratch -y`

## 10. Spectra archival

- [x] 10.1 `spectra validate add-mybot-daemon` is clean
- [x] 10.2 `spectra analyze add-mybot-daemon` has no Critical/Warning findings
- [x] 10.3 Commit + push
- [ ] 10.4 `spectra archive add-mybot-daemon`
