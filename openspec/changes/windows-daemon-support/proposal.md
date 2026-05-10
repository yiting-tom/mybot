## Why

`mybot daemon` (the long-running supervisor that hosts cron + heartbeat) does not start on Windows. Two POSIX-only assumptions block it: `loop.add_signal_handler()` raises `NotImplementedError` on Windows asyncio, and the lockfile staleness probe `os.kill(pid, 0)` always raises `OSError` because Windows has no signal 0. The cron engine, heartbeat service, and agent loop are already pure Python and platform-portable — only the supervisor wrapper and the PID-lock helper need fixing. Closing this gap unlocks Windows users without affecting macOS / Linux behavior.

## What Changes

- Replace `loop.add_signal_handler(SIGINT/SIGTERM, ...)` in the daemon supervisor with a cross-platform pattern: `signal.signal(SIGINT, ...)` (always) plus `signal.signal(SIGTERM, ...)` only on POSIX. Windows has no real SIGTERM equivalent in user code, so it is silently skipped.
- The signal handler SHALL set an `asyncio.Event` thread-safely via `loop.call_soon_threadsafe()`, since `signal.signal` callbacks fire on the main thread outside the event loop on Windows. Double-signal force-exit (`os._exit(1)`) behavior is preserved on every platform.
- Replace `os.kill(existing_pid, 0)` in `_acquire_lockfile()` with a portable liveness probe: try `os.kill(pid, 0)` on POSIX, and on Windows use `ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, 0, pid)` + `WaitForSingleObject(handle, 0)` to distinguish live from dead PIDs. No new third-party dependency is added (no `psutil`).
- Add a "Windows Task Scheduler" subsection to README under "Running as a daemon", parallel to the existing systemd / launchd sections, including a sample XML task definition that wraps `mybot <name> daemon --once` on a 5-minute trigger.
- The `daemon` spec is updated: the "Graceful shutdown" requirement records the platform-specific signal-registration rule, and the "PID lockfile prevents double-start" requirement records the portable liveness-probe rule.

## Non-Goals

- Long-running `mybot <name> daemon` on Windows is in scope, but **graceful shutdown via SIGTERM from a non-console source** is not — Windows lacks a true SIGTERM, so external supervisors must use Ctrl-C-equivalent (CTRL_BREAK_EVENT) or process kill. Documented as a known limitation in README.
- Service-installer integration (NSSM, `sc.exe`, Windows Service wrapper) is out of scope. Users wire the daemon into Task Scheduler themselves following the README guide.
- Adding `psutil` as a runtime dependency is rejected — the lockfile probe is small and isolated, ctypes keeps the dependency surface minimal.
- Automated end-to-end CI on Windows runners is out of scope for this change (manual verification + unit tests for the new helpers only). A follow-up change can add Windows CI if needed.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `daemon`: "Graceful shutdown" and "PID lockfile prevents double-start" requirements are updated to specify cross-platform signal registration and liveness probing. New scenarios cover Windows behavior.

## Impact

- Affected specs: `daemon` (modified — see delta spec)
- Affected code:
  - Modified: `mybot/cli/commands.py` (the `_acquire_lockfile()` helper around line 970 and the `_run_daemon_forever()` signal-registration block around line 1148)
  - Modified: `README.md` (new "Windows Task Scheduler" subsection)
  - New: `mybot/utils/process.py` (small helper module exposing a portable `pid_is_alive(pid: int) -> bool` so the platform-conditional code is unit-testable in isolation)
  - Removed: (none)
- Dependencies: no new third-party packages. Uses `ctypes` (stdlib) on Windows.
- Behavior on existing platforms (macOS, Linux): unchanged. The POSIX code paths remain `os.kill(pid, 0)` and `loop.add_signal_handler()` for SIGINT + SIGTERM.
