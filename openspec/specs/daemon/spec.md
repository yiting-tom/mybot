# daemon Specification

## Purpose

TBD - created by archiving change 'add-mybot-daemon'. Update Purpose after archive.

## Requirements

### Requirement: Run cron and heartbeat for one bot

The `mybot daemon` command (or its chained form `mybot <bot_name> daemon`) SHALL start a foreground supervisor that hosts the active bot's `CronService` and `HeartbeatService` until terminated. The command SHALL block until shutdown.

The supervisor SHALL:

1. Load the active bot's config and instantiate `AgentLoop`, `CronService`, `HeartbeatService`.
2. Wire `cron.on_job` to dispatch jobs through `agent.process_direct(...)` with `session_key=f"cron:{job.id}"`.
3. Wire `heartbeat.on_execute` and `heartbeat.on_notify` to dispatch via `agent.process_direct(...)` with `session_key="heartbeat"` and print results to stdout.
4. Start `agent.run()`, `cron.start()`, and `heartbeat.start()` concurrently.
5. Print every cron / heartbeat result to stdout (see "Output format" requirement).

If no API key is configured for the active bot, the daemon SHALL exit with status 1 and a message pointing at the bot's `config.json` BEFORE entering the loop.

#### Scenario: Daemon fires a due cron job

- **GIVEN** bot `work` exists with API key configured
- **AND** a cron job with `every_seconds=60` and `message="ping"` is enabled
- **WHEN** the user runs `mybot work daemon`
- **THEN** within 60 seconds the agent processes the message "ping"
- **AND** the response is printed to stdout prefixed with the timestamp and job source

#### Scenario: Heartbeat tick reads HEARTBEAT.md

- **GIVEN** `HEARTBEAT.md` contains a non-empty task list
- **AND** `gateway.heartbeat.intervalS` is set to a small value (e.g., 60)
- **WHEN** `mybot work daemon` has been running for one tick
- **THEN** the agent runs the heartbeat tasks and prints results to stdout
- **AND** the heartbeat session uses `session_key="heartbeat"`

#### Scenario: Missing API key blocks startup

- **GIVEN** `agents.defaults.model` is set but no provider has an API key
- **WHEN** the user runs `mybot work daemon`
- **THEN** the command exits with status 1
- **AND** prints `Error: No API key configured.` and the path to `config.json`
- **AND** never starts the cron / heartbeat services

---
### Requirement: Output format

The daemon SHALL emit one line per event in the form:

```
<YYYY-MM-DD HH:MM:SS> [<source>] <content>
```

where `<source>` is one of:

- `cron:<job_id>` — cron-driven message (job id matches `mybot <bot> cron list`)
- `heartbeat` — heartbeat-driven message
- `daemon` — supervisor-level lifecycle messages (start, stop, errors)

Tool-progress hints SHALL be prefixed by `↳ ` and dimmed when stdout is a TTY. Output SHALL be plain text (no ANSI escapes) when stdout is not a TTY.

#### Scenario: Tool progress dimmed on TTY

- **WHEN** the daemon runs in a terminal and a cron job invokes a tool
- **THEN** progress lines like `↳ web_search("foo")` appear dimmed
- **AND** when the daemon's stdout is piped to `tee`, the same lines appear without ANSI codes

##### Example: stdout sample

```
2026-05-03 16:00:00 [daemon]         Daemon started for bot 'work' (cron jobs: 2, heartbeat: every 1800s)
2026-05-03 16:01:00 [cron:1a2b3c4d]  ↳ web_search("AAPL earnings")
2026-05-03 16:01:08 [cron:1a2b3c4d]  AAPL reported Q2 EPS of $2.18, above consensus.
2026-05-03 16:30:00 [heartbeat]      Reviewing HEARTBEAT.md…
2026-05-03 16:30:09 [heartbeat]      No active tasks.
```

---
### Requirement: Graceful shutdown

The daemon SHALL register handlers for SIGINT and SIGTERM. When either is received the daemon SHALL:

1. Stop accepting new cron / heartbeat dispatches.
2. Cancel `cron` and `heartbeat` services (`stop()`).
3. Stop the agent loop (`agent.stop()`).
4. Await any in-flight `process_direct` task for up to 30 seconds.
5. Close MCP connections (`agent.close_mcp()`), tolerating SDK cleanup noise.
6. Exit with status 0.

A second signal received during shutdown SHALL force-exit immediately (`os._exit(1)`).

#### Scenario: SIGINT during idle

- **WHEN** the daemon is running and idle
- **AND** the user presses Ctrl-C
- **THEN** the daemon prints `Shutting down...`, stops services, exits 0 within 1 second

#### Scenario: SIGTERM during in-flight job

- **GIVEN** the daemon is processing a cron job
- **WHEN** SIGTERM is delivered
- **THEN** the daemon waits up to 30 s for the job to complete
- **AND** then exits 0
- **AND** if the job has not finished within 30 s, the task is cancelled and the daemon exits 0 anyway

#### Scenario: Double-signal force-exit

- **WHEN** the user presses Ctrl-C twice in quick succession
- **THEN** the daemon force-exits with status 1 without waiting for cleanup

---
### Requirement: --once flag

The daemon SHALL support `--once`. In this mode the daemon SHALL:

1. NOT start the heartbeat service.
2. Load cron jobs and identify all jobs with `next_run_at_ms <= now`.
3. Execute them sequentially via `on_job`.
4. Persist the updated `jobs.json` (next-run times advanced).
5. Exit with status 0 when the last job returns.

If no jobs are due, the daemon SHALL exit 0 immediately without printing.

#### Scenario: --once with one due job

- **GIVEN** one cron job is due
- **WHEN** `mybot work daemon --once` is run
- **THEN** the job runs through the agent
- **AND** its response is printed
- **AND** `jobs.json` has its `next_run_at_ms` advanced
- **AND** the process exits 0

#### Scenario: --once with no due jobs

- **GIVEN** no cron jobs are currently due
- **WHEN** `mybot work daemon --once` is run
- **THEN** the process exits 0 within 1 second with no output

---
### Requirement: PID lockfile prevents double-start

On startup the daemon SHALL acquire an exclusive lock at `<data_dir>/daemon.pid` containing its PID. If the file exists and the named PID is alive, the daemon SHALL exit 1 with a message naming the existing PID. The lockfile SHALL be removed on clean shutdown.

#### Scenario: Refuse to start if another daemon is running

- **GIVEN** a daemon is running for bot `work` with PID 12345
- **WHEN** the user runs `mybot work daemon` a second time
- **THEN** the second invocation exits 1
- **AND** prints `Daemon already running for 'work' (pid 12345)`

#### Scenario: Stale lockfile is reclaimed

- **GIVEN** `~/.mybot/workspaces/work/daemon.pid` exists but contains a dead PID
- **WHEN** `mybot work daemon` is run
- **THEN** the daemon overwrites the stale lockfile and starts normally

#### Scenario: --once does not lock

- **WHEN** `mybot work daemon --once` is run while a long-running daemon is active for the same bot
- **THEN** the `--once` invocation runs through the cron jobs anyway (it shares the cron store via mtime reload)

> Rationale: `--once` is a transient scan; locking it would make OS-cron-driven scheduling impossible to combine with an interactive daemon.
