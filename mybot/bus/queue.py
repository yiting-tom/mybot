"""In-process REPL ↔ agent queue and subagent fan-in for a single mybot CLI invocation.

This module is deliberately minimal. Cron and heartbeat dispatches do NOT use this bus —
they call `agent.process_direct(...)` directly and receive the response as a return value.
"""

import asyncio

from mybot.bus.events import InboundMessage, OutboundMessage


class MessageBus:
    """Two `asyncio.Queue`s wiring a single CLI process's REPL to its agent loop.

    Scope guarantees (treat as invariants):

    - **In-process only.** Each `mybot` CLI invocation creates its own `MessageBus()`.
      The bus is never persisted, never exposed over IPC / sockets / pipes, and never
      crosses bot boundaries. Two daemons targeting different bots have independent buses.

    - **Two valid `publish_inbound` patterns** (and only these two):
        1. REPL stdin push — interactive REPL constructs `InboundMessage(channel="cli", ...)`
           when the user types a line.
        2. Subagent fan-in — when a subagent finishes, the runner publishes
           `InboundMessage(channel="system", sender_id="subagent", ...)` so the main
           agent loop produces a user-facing summary.

    - **Single `consume_inbound` consumer**: `AgentLoop.run()` in `mybot.agent.loop`.

    - **Outbound queue has one consumer**: the REPL renderer in interactive CLI mode.
      `agent.process_direct(...)` callers (cron, heartbeat, single-shot CLI) bypass
      the outbound queue — they receive the response as a return value instead.
    """

    def __init__(self):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """Publish a message to the agent loop. Caller must use one of the two valid patterns above."""
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available). Sole caller: AgentLoop.run()."""
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent for the REPL renderer to consume."""
        await self.outbound.put(msg)

    async def consume_outbound(self) -> OutboundMessage:
        """Consume the next outbound message (blocks until available). Sole caller: REPL renderer."""
        return await self.outbound.get()

    @property
    def inbound_size(self) -> int:
        """Number of pending inbound messages."""
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        """Number of pending outbound messages."""
        return self.outbound.qsize()
