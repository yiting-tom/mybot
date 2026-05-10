"""Tests for `_acquire_lockfile` (daemon double-start guard)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from mybot.cli.commands import _acquire_lockfile


def test_no_existing_lockfile_writes_pid(tmp_path: Path):
    lockfile = _acquire_lockfile(tmp_path, "test-bot")
    assert lockfile == tmp_path / "daemon.pid"
    assert lockfile.read_text().strip() == str(os.getpid())


def test_existing_lockfile_with_live_pid_refuses(tmp_path: Path):
    lockfile = tmp_path / "daemon.pid"
    lockfile.write_text("99999")
    with patch("mybot.utils.process.pid_is_alive", return_value=True):
        with pytest.raises(typer.Exit) as excinfo:
            _acquire_lockfile(tmp_path, "test-bot")
    assert excinfo.value.exit_code == 1
    assert lockfile.read_text().strip() == "99999"


def test_existing_lockfile_with_dead_pid_reclaims(tmp_path: Path):
    lockfile = tmp_path / "daemon.pid"
    lockfile.write_text("99999")
    with patch("mybot.utils.process.pid_is_alive", return_value=False):
        result = _acquire_lockfile(tmp_path, "test-bot")
    assert result == lockfile
    assert lockfile.read_text().strip() == str(os.getpid())


def test_lockfile_with_garbage_pid_reclaims(tmp_path: Path):
    lockfile = tmp_path / "daemon.pid"
    lockfile.write_text("not-a-number")
    result = _acquire_lockfile(tmp_path, "test-bot")
    assert result == lockfile
    assert lockfile.read_text().strip() == str(os.getpid())


def test_lockfile_with_zero_pid_reclaims(tmp_path: Path):
    lockfile = tmp_path / "daemon.pid"
    lockfile.write_text("0")
    result = _acquire_lockfile(tmp_path, "test-bot")
    assert result == lockfile
    assert lockfile.read_text().strip() == str(os.getpid())
