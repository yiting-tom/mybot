## Why

`mybot/bus/events.py` carries data fields that were inherited from the upstream nanobot project but have no live consumers in the stripped-down mybot codebase: `InboundMessage.media`, `InboundMessage.metadata`, `OutboundMessage.media`, `OutboundMessage.reply_to`, and most of `OutboundMessage.metadata`. They were originally for chat-platform routing (Telegram media URLs, reply-threading IDs, per-channel metadata) — that integration layer was already removed when mybot was forked from nanobot, so the fields are dead weight that misleads readers about the bus's actual scope.

There is one exception: `OutboundMessage.metadata["_progress"]` and `OutboundMessage.metadata["_tool_hint"]` ARE actively read by the REPL outbound consumer in `mybot/cli/commands.py` to distinguish progress hints (dimmed `↳ ...` lines) from final responses. That signal is load-bearing and must be preserved across this change. Discovered during apply — this proposal corrects the earlier "metadata is never read" claim.

A preceding `/spectra-discuss` session established that mybot only needs CLI ↔ agent communication and explicitly rejected re-introducing chat-platform channels. The bus is genuinely required for two in-process patterns — REPL message flow and subagent fan-in — but its current data model and documentation suggest a much broader contract than reality. This change aligns the data model and docs with what the bus actually does so future readers do not mistake the vestigial fields for live extension points, while replacing the magic-string `metadata` flags with explicit typed fields.

## What Changes

- Drop `InboundMessage.media: list[str]` and `InboundMessage.metadata: dict[str, Any]` from the `InboundMessage` dataclass. Replace the two read sites that currently call `msg.metadata.get("message_id")` (in `_process_message`) with the literal `None` they already returned in practice (the field has never been populated for `InboundMessage`). Replace the `loop.py` read of `msg.media` with `None` for the same reason.
- Drop `OutboundMessage.media: list[str]` and `OutboundMessage.reply_to: str | None` from the `OutboundMessage` dataclass — neither is read anywhere.
- Replace `OutboundMessage.metadata: dict[str, Any]` with two explicit typed fields on `OutboundMessage`: `is_progress: bool = False` and `is_tool_hint: bool = False`. These are the only two metadata keys actually consumed (by the REPL renderer at `mybot/cli/commands.py`). The replacement preserves behavior while removing the open-ended `dict[str, Any]` extension point.
- Tighten `channel` on both message classes from `str` to `typing.Literal["cli", "system"]`. These are the only two values currently emitted: `"cli"` for REPL / single-shot / cron / heartbeat traffic, and `"system"` for subagent fan-in announcements.
- Update every `InboundMessage(...)` / `OutboundMessage(...)` constructor and read site in `mybot/agent/loop.py`, `mybot/agent/subagent.py`, `mybot/agent/tools/message.py`, and `mybot/cli/commands.py`:
  - Remove kwargs targeting the deleted fields (`media=...`, `reply_to=...`, generic `metadata=...`).
  - Replace the `_bus_progress` callback's `metadata={"_progress": True, "_tool_hint": tool_hint}` pattern with `is_progress=True, is_tool_hint=tool_hint` direct kwargs.
  - Update the REPL outbound consumer in `mybot/cli/commands.py` from `if msg.metadata.get("_progress"):` to `if msg.is_progress:`.
- Add a `MessageBus` class docstring that pins down the contract: in-process only, per-CLI-invocation, never crosses bot boundaries, two valid `publish_inbound` publishers (REPL stdin, subagent fan-in), one consumer (`AgentLoop.run()` via `consume_inbound`), the outbound queue is consumed only by the REPL renderer, and cron / heartbeat bypass the bus entirely via `agent.process_direct(...)`.
- Refresh module-level docstrings on `mybot/bus/__init__.py`, `mybot/bus/events.py`, and `mybot/bus/queue.py` so they describe the actual scope rather than "decoupled channel-agent communication".
- Update the README project-layout entry from `bus/  🚌 In-process message routing` to `bus/  🚌 REPL ↔ agent queue + subagent fan-in`.

## Non-Goals

- **Multi-bot messaging / bot-to-bot routing across processes.** Out of scope. The bus stays per-process and per-CLI-invocation.
- **Re-introducing chat-platform channels.** Telegram / Discord / Slack / WhatsApp integrations are not coming back; that is the entire point of mybot vs. nanobot.
- **Persistent or cross-process bus.** No IPC, no Redis, no Unix socket, no shared file. The `MessageBus` instance lives only as long as the Python process.
- **Replacing the bus with plain callbacks.** Considered and rejected: subagent fan-in legitimately needs queue semantics so multiple subagents finishing in parallel do not race against the main agent's processing. Keeping `asyncio.Queue` is correct.
- **Adding new tests.** The existing pytest suite plus the bus's small surface area means a constructor-signature mistake fails at import time, not at runtime. No new tests are warranted; manual verification (REPL chat, subagent dispatch, cron tick) is enough for this change.
- **Renaming `MessageBus`, `InboundMessage`, or `OutboundMessage`.** The names still describe what they do; renaming would churn callers without value.

## Capabilities

### New Capabilities

- `bus-messaging`: Captures the contract of `mybot/bus/` — the in-process-only invariant, the two valid publisher patterns (REPL stdin, subagent fan-in), the single-consumer rule (`AgentLoop.run()`), the trimmed message data model, and the explicit non-extension to cross-bot or cross-platform routing.

### Modified Capabilities

(none)

## Impact

- Affected specs: `bus-messaging` (new — see `openspec/changes/trim-bus-data-model/specs/bus-messaging/spec.md`).
- Affected code:
  - Modified: `mybot/bus/events.py` (drop fields, tighten `channel` to `Literal`, refresh module docstring)
  - Modified: `mybot/bus/queue.py` (add `MessageBus` class docstring, refresh module docstring)
  - Modified: `mybot/bus/__init__.py` (refresh module docstring)
  - Modified: `mybot/agent/loop.py` (remove kwargs targeting deleted fields, e.g. `metadata=msg.metadata or {}`)
  - Modified: `mybot/agent/subagent.py` (remove kwargs targeting deleted fields)
  - Modified: `mybot/agent/tools/message.py` (remove kwargs targeting deleted fields)
  - Modified: `mybot/cli/commands.py` (remove kwargs targeting deleted fields)
  - Modified: `README.md` (project-layout entry)
  - New: (none)
  - Removed: (none)
- Dependencies: no new third-party packages. Uses `typing.Literal` (stdlib).
- Backwards compatibility: there is no public API outside `mybot.bus`; `InboundMessage` and `OutboundMessage` are not exported as a stable contract. Internal callers all live in this repo and are updated in the same change.
- Behavior: no observable change at the CLI level. REPL chat, single-shot mode, cron, heartbeat, and subagent fan-in all continue to work exactly as today.
