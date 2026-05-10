"""Cross-platform PID liveness probe used by the daemon lockfile."""

from __future__ import annotations

import os
import sys

# Win32 constants used by `_pid_is_alive_windows`. Names match the official kernel32 API
# so they stay greppable against Microsoft documentation.
_WIN32_SYNCHRONIZE = 0x00100000
_WIN32_WAIT_OBJECT_0 = 0x00000000
_WIN32_WAIT_TIMEOUT = 0x00000102


def pid_is_alive(pid: int) -> bool:
    """Return True if `pid` names a running process on this host."""
    if pid <= 0:
        return False

    if sys.platform == "win32":
        return _pid_is_alive_windows(pid)
    return _pid_is_alive_posix(pid)


def _pid_is_alive_posix(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but belongs to another user — still "alive" for lockfile purposes.
        return True
    except OSError:
        return False
    return True


def _pid_is_alive_windows(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(_WIN32_SYNCHRONIZE, False, pid)
    if not handle:
        return False
    try:
        status = kernel32.WaitForSingleObject(handle, 0)
    finally:
        kernel32.CloseHandle(handle)

    if status == _WIN32_WAIT_TIMEOUT:
        return True
    if status == _WIN32_WAIT_OBJECT_0:
        return False
    return False
