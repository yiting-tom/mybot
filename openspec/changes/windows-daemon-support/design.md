## Context

`mybot daemon` is the foreground supervisor that hosts a single bot's `CronService` and `HeartbeatService`. It is implemented in `mybot/cli/commands.py`:

- `_acquire_lockfile()` (around line 970) writes the daemon PID to `<data_dir>/daemon.pid` and refuses to start if a live PID already owns the file. The liveness probe is `os.kill(existing_pid, 0)` — a POSIX idiom that asks the kernel "does this process exist and am I allowed to signal it?" without delivering a signal. On Windows there is no signal 0; this call always raises `OSError`, so the staleness branch fires unconditionally and the lockfile is silently overwritten — the double-start guarantee is broken.
- `_run_daemon_forever()` (around line 1148) registers SIGINT + SIGTERM handlers via `loop.add_signal_handler(...)`. On Windows asyncio (`ProactorEventLoop` and `SelectorEventLoop`) `add_signal_handler` raises `NotImplementedError` because the underlying event loops cannot self-pipe a signal into the loop. The daemon never enters the wait state.

The cron engine, heartbeat ticker, and agent loop are pure asyncio and already work on Windows. Only these two helpers and the README guidance need fixing.

This change introduces no new third-party dependencies. The Windows liveness probe uses `ctypes` (stdlib) to call `OpenProcess` + `WaitForSingleObject` against `kernel32.dll`.

## Goals / Non-Goals

**Goals:**

- `mybot <name> daemon` (long-running mode) starts and runs on Windows 10+ until Ctrl-C is pressed, then exits cleanly with status 0.
- `mybot <name> daemon --once` runs all due cron jobs and exits 0 on Windows.
- The PID lockfile correctly distinguishes live from dead daemons on Windows.
- macOS and Linux behavior is byte-identical to today (same `os.kill(pid, 0)` probe, same `loop.add_signal_handler` registration, same SIGINT + SIGTERM handling).
- The new platform-conditional code lives in one small helper module so it is unit-testable without spawning real processes or registering real signals.

**Non-Goals:**

- SIGTERM-equivalent graceful shutdown from non-console supervisors on Windows. Windows lacks a true SIGTERM in user code; external supervisors that need ordered shutdown must send `CTRL_BREAK_EVENT` (which Python translates to SIGBREAK) — left for a future change if requested.
- Service-installer integration (NSSM, `sc.exe`, custom Windows Service wrapper).
- A `psutil` dependency for the liveness probe.
- Adding Windows CI runners. Verification for this change is unit tests + manual smoke on a Windows VM.
- Reworking the existing daemon supervisor architecture. This change is platform-shimming only.

## Decisions

### Use `signal.signal()` with `loop.call_soon_threadsafe()` instead of `loop.add_signal_handler()`

`signal.signal(SIGINT, handler)` works identically on Windows and POSIX, but the handler runs on the main thread outside the running event loop. To wake the loop's `shutdown.wait()`, the handler SHALL call `loop.call_soon_threadsafe(shutdown.set)`. This is the standard pattern for cross-platform asyncio signal handling.

`loop.add_signal_handler()` is kept as the POSIX path because it integrates cleanly with the running loop and is what the existing spec scenarios assume. The chosen branch is detected via `sys.platform == "win32"`, not via try/except on `add_signal_handler`, so behavior is predictable and grep-able.

SIGTERM is registered only on POSIX. Python on Windows accepts `signal.signal(SIGTERM, ...)` but the signal is never raised by user-mode code (it is converted to a process kill at the OS layer), so wiring a handler is dead code. Recording this explicitly in the spec prevents future "why doesn't SIGTERM work on Windows" confusion.

Alternatives considered:
- **Pure `loop.add_signal_handler` with try/except fallback.** Rejected — silently swallowing `NotImplementedError` is fragile and hides platform branches that the spec needs to capture.
- **`asyncio.WindowsProactorEventLoopPolicy` swap to a SelectorEventLoop.** Rejected — `SelectorEventLoop` on Windows has its own subprocess and pipe limitations and is not a drop-in replacement.

### Implement a `mybot/utils/process.py` module with `pid_is_alive(pid: int) -> bool`

The lockfile probe SHALL be extracted from `_acquire_lockfile()` into a tiny helper so its platform branches can be unit-tested without touching real lockfiles. The helper signature is `pid_is_alive(pid: int) -> bool`.

POSIX implementation: `os.kill(pid, 0)`; treat `ProcessLookupError` as dead, `PermissionError` as alive (we cannot signal it but it exists), other `OSError` as dead.

Windows implementation via `ctypes`:
- Open the process with `OpenProcess(SYNCHRONIZE, False, pid)` from `kernel32.dll`.
- If the handle is `NULL`, the process is dead (or we lack permission — treated as dead, which matches the desired behavior of allowing the lockfile to be reclaimed).
- Otherwise call `WaitForSingleObject(handle, 0)`. Return value `WAIT_TIMEOUT (0x102)` means the process is still running; `WAIT_OBJECT_0 (0)` means it has exited.
- Always call `CloseHandle(handle)` in a `finally` block.

Alternatives considered:
- **`psutil.pid_exists(pid)`.** Rejected — adds a third-party dependency for ~15 lines of stdlib code.
- **Reading `tasklist.exe` output.** Rejected — fork + parse is slower and flakier than a direct API call.

### `_acquire_lockfile()` becomes platform-agnostic

After the helper exists, `_acquire_lockfile()` simply calls `pid_is_alive(existing_pid)` regardless of platform. The function loses its `try: os.kill(...) except OSError` block and becomes shorter.

### README adds a "Windows (Task Scheduler)" subsection parallel to systemd / launchd

The new subsection lives under "Running as a daemon" and provides:
1. A note that long-running `mybot <name> daemon` works under Windows console hosts (PowerShell, Windows Terminal).
2. A sample Task Scheduler XML or `schtasks` invocation that runs `mybot <name> daemon --once` every 5 minutes — analogous to the existing `system cron + --once` snippet.
3. The graceful-shutdown caveat: SIGTERM has no Windows equivalent in user code, so external supervisors should send Ctrl-Break or terminate the process.

## Risks / Trade-offs

- **[Risk] `ctypes` Win32 calls used incorrectly cause crashes or silent wrong answers.** → Mitigation: keep the Windows branch under 30 lines, restrict it to `OpenProcess` + `WaitForSingleObject` + `CloseHandle` (well-known idiomatic combo), unit-test against the current process PID (must return True) and a guaranteed-dead PID like `2**31 - 1` (must return False).
- **[Risk] Signal handler running on the main thread reaches into the loop after the loop has closed.** → Mitigation: the handler captures the loop via closure at registration time and uses `call_soon_threadsafe`; on a closed loop the call raises `RuntimeError`, which the handler catches and ignores (the process is already exiting). This matches the existing double-signal `os._exit(1)` semantics.
- **[Risk] No Windows CI means regressions slip through.** → Mitigation: the helper module is small and pure; unit tests cover the POSIX branch on Linux/macOS CI and use `unittest.mock` to exercise the Windows ctypes branch on every platform. A manual Windows smoke checklist is added to the tasks artifact.
- **[Trade-off] We accept that `PermissionError` from `os.kill(pid, 0)` is treated as "alive" while the Windows path treats permission failures as "dead".** This asymmetry is documented but not fixed — on POSIX a permission failure means the PID belongs to another user (the daemon truly is running and we shouldn't reclaim its lockfile), while on Windows a `NULL` handle from `OpenProcess` is more often a transient "process already exited" case during the close window. The behavior is conservative on each platform.
