## MODIFIED Requirements

### Requirement: Graceful shutdown

The daemon SHALL register a handler for SIGINT on every supported platform. On POSIX (`sys.platform != "win32"`) the daemon SHALL additionally register a handler for SIGTERM. Registration MUST use the platform-appropriate API:

- POSIX: `loop.add_signal_handler(SIGINT | SIGTERM, ...)` — handlers are dispatched directly by the running event loop.
- Windows (`sys.platform == "win32"`): `signal.signal(SIGINT, ...)` — the handler runs on the main thread and MUST call `loop.call_soon_threadsafe(shutdown.set)` to wake the supervisor's `asyncio.Event`. SIGTERM SHALL NOT be registered on Windows because Python on Windows does not deliver SIGTERM to user code.

When the registered signal is received the daemon SHALL:

1. Stop accepting new cron / heartbeat dispatches.
2. Cancel `cron` and `heartbeat` services (`stop()`).
3. Stop the agent loop (`agent.stop()`).
4. Await any in-flight `process_direct` task for up to 30 seconds.
5. Close MCP connections (`agent.close_mcp()`), tolerating SDK cleanup noise.
6. Exit with status 0.

A second signal received during shutdown SHALL force-exit immediately (`os._exit(1)`). This force-exit behavior MUST be available on every supported platform.

If the signal handler is invoked after the event loop has been closed, it SHALL catch `RuntimeError` from `call_soon_threadsafe` and return without raising — the process is already exiting.

#### Scenario: SIGINT during idle (POSIX)

- **GIVEN** the daemon runs on macOS or Linux
- **WHEN** the daemon is running and idle and the user presses Ctrl-C
- **THEN** the daemon prints `Shutting down...`, stops services, and exits 0 within 1 second

#### Scenario: SIGINT during idle (Windows)

- **GIVEN** the daemon runs on Windows 10 or later under a console host (PowerShell, Windows Terminal, cmd.exe)
- **WHEN** the daemon is running and idle and the user presses Ctrl-C
- **THEN** the `signal.signal` SIGINT handler fires on the main thread, schedules `shutdown.set()` via `loop.call_soon_threadsafe`, the supervisor wakes, services stop, and the daemon exits 0 within 1 second

#### Scenario: SIGTERM during in-flight job (POSIX only)

- **GIVEN** the daemon runs on POSIX and is processing a cron job
- **WHEN** SIGTERM is delivered
- **THEN** the daemon waits up to 30 s for the job to complete and then exits 0
- **AND** if the job has not finished within 30 s, the task is cancelled and the daemon exits 0 anyway

#### Scenario: SIGTERM not registered on Windows

- **GIVEN** the daemon runs on Windows
- **WHEN** the daemon enters its run loop
- **THEN** no SIGTERM handler is registered (the platform does not deliver SIGTERM to user code)
- **AND** external supervisors that need ordered shutdown MUST send Ctrl-Break (`CTRL_BREAK_EVENT`) or terminate the process

#### Scenario: Double-signal force-exit

- **GIVEN** the daemon runs on any supported platform
- **WHEN** the user presses Ctrl-C twice in quick succession
- **THEN** the daemon force-exits with status 1 without waiting for cleanup

### Requirement: PID lockfile prevents double-start

On startup the daemon SHALL acquire an exclusive lock at `<data_dir>/daemon.pid` containing its PID. If the file exists and the named PID is alive according to a portable liveness probe, the daemon SHALL exit 1 with a message naming the existing PID. The lockfile SHALL be removed on clean shutdown.

The portable liveness probe SHALL be exposed as `pid_is_alive(pid: int) -> bool` and SHALL behave as follows:

- POSIX: call `os.kill(pid, 0)`. Treat `ProcessLookupError` (or `OSError(ESRCH)`) as dead. Treat `PermissionError` (or `OSError(EPERM)`) as alive — the process exists, the current user merely cannot signal it. Other `OSError` instances SHALL be treated as dead so the lockfile can be reclaimed.
- Windows (`sys.platform == "win32"`): call `kernel32.OpenProcess(SYNCHRONIZE, False, pid)` via `ctypes`. A `NULL` handle SHALL be treated as dead. A non-NULL handle SHALL be probed with `WaitForSingleObject(handle, 0)`: a return value of `WAIT_TIMEOUT` (`0x102`) means the process is still running; `WAIT_OBJECT_0` (`0x0`) means it has exited. The handle SHALL always be released with `CloseHandle` in a `finally` block.

`pid_is_alive(0)` and `pid_is_alive(<negative>)` SHALL return `False` on every platform.

#### Scenario: Refuse to start if another daemon is running

- **GIVEN** a daemon is running for bot `work` with PID 12345 on any supported platform
- **WHEN** the user runs `mybot work daemon` a second time
- **THEN** `pid_is_alive(12345)` returns `True`
- **AND** the second invocation exits 1 and prints `Daemon already running for 'work' (pid 12345)`

#### Scenario: Stale lockfile is reclaimed (POSIX)

- **GIVEN** the daemon runs on macOS or Linux
- **AND** `~/.mybot/workspaces/work/daemon.pid` exists but contains a PID that has been recycled or is no longer running
- **WHEN** `mybot work daemon` is run
- **THEN** `os.kill(pid, 0)` raises `ProcessLookupError`, `pid_is_alive(pid)` returns `False`
- **AND** the daemon overwrites the stale lockfile and starts normally

#### Scenario: Stale lockfile is reclaimed (Windows)

- **GIVEN** the daemon runs on Windows
- **AND** `<data_dir>\daemon.pid` contains a PID whose process has exited
- **WHEN** `mybot work daemon` is run
- **THEN** `OpenProcess` returns `NULL` (or `WaitForSingleObject` returns `WAIT_OBJECT_0`), `pid_is_alive(pid)` returns `False`
- **AND** the daemon overwrites the stale lockfile and starts normally

#### Scenario: --once does not lock

- **WHEN** `mybot work daemon --once` is run while a long-running daemon is active for the same bot
- **THEN** the `--once` invocation runs through the cron jobs anyway (it shares the cron store via mtime reload)

> Rationale: `--once` is a transient scan; locking it would make OS-cron-driven scheduling impossible to combine with an interactive daemon.
