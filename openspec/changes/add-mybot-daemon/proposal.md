## Why

`mybot` already has a `CronService` and `HeartbeatService` — both fully wired into the agent loop and config — but nothing actually keeps them running. After dropping nanobot's `gateway` command (which used to host them alongside chat channels), the only way to trigger a scheduled job is `mybot <bot> cron run <id>` by hand. The `HEARTBEAT.md` file is silent.

This is the single biggest functional gap noted in the README roadmap. We need a long-running process per bot that:
- Fires due cron jobs at their scheduled time.
- Runs the heartbeat tick on its configured interval (default every 30 minutes).
- Streams the agent's responses to stdout (timestamped) so the user can `tail -f` a log or run under systemd / launchd.
- Shuts down cleanly on SIGINT/SIGTERM, including any in-flight agent task.

Without it, two of the agent's "core" capabilities (scheduled tasks, periodic self-prompted work) ship as dead code.

## What Changes

- **New CLI command `mybot daemon`** (or `mybot <bot> daemon` via the chat-shortcut chain) that:
  - Loads the active bot's config and constructs an `AgentLoop`, `CronService`, `HeartbeatService`.
  - Wires the cron `on_job` callback to call `agent.process_direct(...)` and prints results.
  - Wires the heartbeat `on_execute` and `on_notify` callbacks similarly.
  - Awaits `agent.run()` (the bus consumer) alongside `cron.start()` and `heartbeat.start()`.
  - On SIGINT/SIGTERM: stops the agent, awaits in-flight tasks, closes MCP, exits 0.
- **Add `daemon` to `RESERVED_COMMANDS`** so `mybot work daemon` chains correctly.
- **Add a `--once` flag** that runs every due job once and exits — useful for dry-running, cron-driven setups (system cron + `mybot work daemon --once`), and tests.
- **Add a `--log-file PATH` flag** (optional) that mirrors stdout to a file with rotation off (user can rotate via OS tools).
- **Update `README.md`**: replace the roadmap entry with usage docs, add a "Running as a service" section with both systemd (Linux) and launchd (macOS) examples scoped per-bot.
- **No changes to** `CronService`, `HeartbeatService`, or `AgentLoop` — they're already designed for this; we're just hosting them.

## Non-Goals

- **Multi-bot single process.** Each bot still runs its own daemon. We don't introduce orchestration; that belongs in OS-level supervisors.
- **Background / daemonized fork.** The command runs in the foreground. Daemonization is the OS's job (systemd, launchd, `nohup`).
- **HTTP / IPC control surface.** No `mybot daemon stop` or status server. Users send signals; introspection is via `mybot <bot> cron list` from another shell.
- **Hot config reload.** A config change requires restart. (`CronService` already detects `jobs.json` mtime changes for cron edits, so cron list mutations are picked up live, but provider / model / heartbeat-interval changes are not.)
- **Log rotation, syslog forwarding, structured logging.** Out of scope; OS tools handle this.

## Capabilities

### New Capabilities

- `daemon`: long-running supervisor that hosts `CronService` + `HeartbeatService` for one bot, dispatches scheduled work into the agent, and prints responses.

### Modified Capabilities

- `chat-shortcut`: `daemon` joins the `RESERVED_COMMANDS` set so `mybot <bot> daemon` chains rather than being rewritten as a chat message.

## Impact

- Affected specs: `daemon` (new), `chat-shortcut` (modified — reserved word list grows by one).
- Affected code:
  - Modified: mybot/cli/commands.py (new `daemon` command, update `RESERVED_COMMANDS`)
  - Modified: README.md (usage + service templates, remove daemon from roadmap)
- External: no new dependencies. Uses `asyncio`, `signal`, and the existing `CronService` / `HeartbeatService` / `AgentLoop`.
