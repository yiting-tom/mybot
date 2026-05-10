"""Tests for mybot.utils.process.pid_is_alive."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from mybot.utils.process import pid_is_alive


def test_current_process_is_alive():
    assert pid_is_alive(os.getpid()) is True


def test_huge_pid_is_dead():
    assert pid_is_alive(2**31 - 1) is False


@pytest.mark.parametrize("pid", [0, -1, -100, -2**31])
def test_zero_or_negative_returns_false(pid):
    assert pid_is_alive(pid) is False


def _windll_mock(open_process_return: int, wait_return: int = 0x102) -> MagicMock:
    fake_kernel32 = MagicMock()
    fake_kernel32.OpenProcess.return_value = open_process_return
    fake_kernel32.WaitForSingleObject.return_value = wait_return
    fake_kernel32.CloseHandle.return_value = 1
    fake_windll = MagicMock()
    fake_windll.kernel32 = fake_kernel32
    return fake_windll


def test_windows_branch_alive():
    fake_windll = _windll_mock(open_process_return=0xDEADBEEF, wait_return=0x102)
    with patch("sys.platform", "win32"), patch("ctypes.windll", fake_windll, create=True):
        assert pid_is_alive(12345) is True
    fake_windll.kernel32.CloseHandle.assert_called_once_with(0xDEADBEEF)


def test_windows_branch_dead_null_handle():
    fake_windll = _windll_mock(open_process_return=0)
    with patch("sys.platform", "win32"), patch("ctypes.windll", fake_windll, create=True):
        assert pid_is_alive(12345) is False
    fake_windll.kernel32.WaitForSingleObject.assert_not_called()
    fake_windll.kernel32.CloseHandle.assert_not_called()


def test_windows_branch_dead_via_wait_object_0():
    fake_windll = _windll_mock(open_process_return=0xDEADBEEF, wait_return=0)
    with patch("sys.platform", "win32"), patch("ctypes.windll", fake_windll, create=True):
        assert pid_is_alive(12345) is False
    fake_windll.kernel32.CloseHandle.assert_called_once_with(0xDEADBEEF)


def test_windows_branch_unknown_wait_status_treated_as_dead():
    fake_windll = _windll_mock(open_process_return=0xDEADBEEF, wait_return=0xFFFFFFFF)
    with patch("sys.platform", "win32"), patch("ctypes.windll", fake_windll, create=True):
        assert pid_is_alive(12345) is False


def test_posix_permission_error_treated_as_alive():
    with patch("sys.platform", "linux"), patch("os.kill", side_effect=PermissionError):
        assert pid_is_alive(12345) is True


def test_posix_process_lookup_error_treated_as_dead():
    with patch("sys.platform", "linux"), patch("os.kill", side_effect=ProcessLookupError):
        assert pid_is_alive(12345) is False
