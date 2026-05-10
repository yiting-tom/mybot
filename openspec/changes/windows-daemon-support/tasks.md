## 1. Portable PID liveness probe

- [x] 1.1 Create `mybot/utils/process.py` exposing `pid_is_alive(pid: int) -> bool`. Implement the POSIX branch using `os.kill(pid, 0)` with the `ProcessLookupError` / `PermissionError` / generic `OSError` semantics from the design decision "Implement a `mybot/utils/process.py` module with `pid_is_alive(pid: int) -> bool`".
- [x] 1.2 In the same module, add the Windows branch under `if sys.platform == "win32"`: load `kernel32` via `ctypes.windll`, call `OpenProcess(SYNCHRONIZE=0x00100000, False, pid)`, gate on a `NULL` handle, then probe with `WaitForSingleObject(handle, 0)` and release with `CloseHandle` in `finally`.
- [x] 1.3 Make `pid_is_alive(0)` and `pid_is_alive(<negative>)` return `False` on every platform (guard at the top of the function).
- [x] 1.4 Add unit tests in `tests/utils/test_process.py`: (a) `pid_is_alive(os.getpid())` returns `True`; (b) `pid_is_alive(2**31 - 1)` returns `False`; (c) Windows branch covered with `unittest.mock.patch("ctypes.windll")` so the test runs on Linux/macOS CI; (d) zero/negative inputs return `False`.

## 2. Cross-platform signal wiring (Graceful shutdown)

- [x] 2.1 In `mybot/cli/commands.py` `_run_daemon_forever()`, replace the `loop.add_signal_handler(...)` block (around line 1148) with the platform-branched pattern from the design decision "Use `signal.signal()` with `loop.call_soon_threadsafe()` instead of `loop.add_signal_handler()`": POSIX path uses `loop.add_signal_handler` for SIGINT + SIGTERM; Windows path uses `signal.signal(SIGINT, handler)` only, where the handler captures `loop` via closure and calls `loop.call_soon_threadsafe(shutdown.set)`.
- [x] 2.2 Wrap the `call_soon_threadsafe` call in a `try/except RuntimeError` so a signal arriving after loop close is silently absorbed (the Graceful shutdown spec scenario "SIGINT during idle (Windows)").
- [x] 2.3 Preserve the existing double-signal force-exit behavior (`os._exit(1)` on the second signal) on every platform — verify the `forced_exit["flag"]` branch runs before the new `call_soon_threadsafe` path.
- [ ] 2.4 Manually smoke-test on macOS: start `mybot test daemon`, press Ctrl-C, confirm clean exit within 1 second. Repeat on Linux if available.
- [ ] 2.5 Manually smoke-test on Windows 10 or 11 (PowerShell or Windows Terminal): start `mybot test daemon`, press Ctrl-C, confirm clean exit within 1 second; press Ctrl-C twice in quick succession, confirm exit code 1 force-exit.

## 3. Lockfile uses portable probe (PID lockfile prevents double-start)

- [x] 3.1 In `mybot/cli/commands.py` `_acquire_lockfile()` (around line 970), import `pid_is_alive` from `mybot.utils.process` and replace the `try: os.kill(existing_pid, 0) except OSError:` block with `if pid_is_alive(existing_pid): refuse else: overwrite stale lockfile`. This realizes the design decision "`_acquire_lockfile()` becomes platform-agnostic" and satisfies the spec requirement "PID lockfile prevents double-start" on every supported platform.
- [x] 3.2 Add unit tests for `_acquire_lockfile()` covering (a) no existing lockfile → write succeeds, (b) existing lockfile with live PID → exits 1 with the expected message, (c) existing lockfile with dead PID → reclaim succeeds. Mock `pid_is_alive` so tests are platform-agnostic.
- [ ] 3.3 Manually verify on Windows: write a fake `daemon.pid` containing PID `2**31 - 1`, run `mybot test daemon`, confirm the daemon reclaims the stale file and starts.

## 4. Documentation (Windows Task Scheduler)

- [x] 4.1 In `README.md`, add a "Windows (Task Scheduler)" subsection under "Running as a daemon" parallel to the existing systemd and launchd sections — realizing the design decision README adds a "Windows (Task Scheduler)" subsection parallel to systemd / launchd. Include a `schtasks /Create` or Task Scheduler XML snippet that wraps `mybot <name> daemon --once` on a 5-minute trigger.
- [x] 4.2 In the same subsection, document the SIGTERM caveat from the spec: external supervisors must send Ctrl-Break (`CTRL_BREAK_EVENT`) or terminate the process; SIGTERM is not delivered to user code on Windows.
- [x] 4.3 Update the `pyproject.toml` Python version classifiers (or the README "Install" section) to mention Windows alongside macOS and Linux as supported platforms.

## 5. Validation

- [x] 5.1 Run `pytest tests/utils/test_process.py` and the new lockfile tests on macOS / Linux CI; confirm green.
- [x] 5.2 Run `spectra validate windows-daemon-support`; confirm green.
- [ ] 5.3 Verify on a Windows VM that `mybot create test`, configure an API key, `mybot test cron add --name ping --every 60 --message ping`, `mybot test daemon` runs at least one cron tick before being stopped with Ctrl-C.
