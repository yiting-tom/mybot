"""Message types for the in-process REPL ↔ agent queue and subagent fan-in.

Channel values are constrained to a small `Literal`:

- `cli`: REPL stdin push, single-shot CLI, cron, heartbeat — anything driven by the user or scheduler.
- `system`: subagent fan-in announcements injected so the main agent loop summarizes them for the user.

Re-introducing chat-platform routing (Telegram, Discord, etc.) is explicitly out of scope.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class InboundMessage:
    """A message arriving at `AgentLoop.run()` — either from REPL stdin or a subagent fan-in."""

    channel: Literal["cli", "system"]
    sender_id: str
    chat_id: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    session_key_override: str | None = None

    @property
    def session_key(self) -> str:
        """Unique key for session identification."""
        return self.session_key_override or f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """A response published by the agent core for the REPL renderer to consume.

    `is_progress` lets the renderer distinguish intermediate progress hints (rendered as
    dimmed `↳ ...` lines) from final responses. `is_tool_hint` differentiates tool-call
    progress notes from free-form progress text.
    """

    channel: Literal["cli", "system"]
    chat_id: str
    content: str
    is_progress: bool = False
    is_tool_hint: bool = False
