"""In-process REPL ↔ agent queue plus subagent fan-in. Per-CLI-invocation, never crosses bots."""

from mybot.bus.events import InboundMessage, OutboundMessage
from mybot.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
