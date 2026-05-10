## ADDED Requirements

### Requirement: In-process scope of MessageBus

The `MessageBus` class in `mybot/bus/queue.py` SHALL be in-process only. Each invocation of any `mybot` CLI command SHALL instantiate its own `MessageBus()`; the bus SHALL NOT be shared across processes, MUST NOT be persisted to disk, and MUST NOT be exposed over IPC, sockets, named pipes, or any cross-process transport. The bus instance lifetime SHALL equal the lifetime of the Python process that created it.

The bus SHALL NOT carry traffic between distinct mybot bots. Two daemons or two CLI invocations targeting different bots SHALL each have an independent bus that is invisible to the other.

#### Scenario: Bus instance is per CLI invocation

- **GIVEN** the user runs `mybot work daemon` in one terminal
- **AND** the user runs `mybot work "hello"` in a second terminal at the same time
- **WHEN** both processes start
- **THEN** each process creates its own `MessageBus()` instance
- **AND** messages published in one process are not observable in the other

#### Scenario: Bus does not cross bot boundaries

- **GIVEN** a daemon is running for bot `work`
- **AND** a separate daemon is running for bot `notes`
- **WHEN** the `work` agent publishes any message via its bus
- **THEN** the `notes` daemon's bus does not receive that message
- **AND** the only on-disk state shared between the two bots is what they explicitly write to their workspace folders

---

### Requirement: Two valid publisher patterns

`MessageBus.publish_inbound` SHALL be invoked in exactly two patterns:

1. **REPL stdin push.** The interactive CLI (`mybot <name>` interactive mode) and any single-shot CLI invocation that routes through the bus SHALL construct an `InboundMessage` with `channel="cli"` and publish it.
2. **Subagent fan-in.** When a subagent finishes, the subagent runner SHALL construct an `InboundMessage` with `channel="system"` carrying the announcement payload and publish it so that the main `AgentLoop.run()` picks it up and produces a user-facing summary.

No other publisher pattern SHALL be added without first updating this requirement. Any future caller MUST use one of these two channel values.

`MessageBus.consume_inbound` SHALL have exactly one consumer: `AgentLoop.run()` in `mybot/agent/loop.py`.

#### Scenario: REPL pushes user input as channel="cli"

- **WHEN** the user types a message into the interactive REPL
- **THEN** the REPL constructs `InboundMessage(channel="cli", ...)`
- **AND** publishes it via `bus.publish_inbound(...)`
- **AND** `AgentLoop.run()` consumes it on its next iteration of `consume_inbound`

#### Scenario: Subagent announces result as channel="system"

- **GIVEN** a subagent dispatched from the main agent has just finished
- **WHEN** the subagent runner reports the result
- **THEN** it constructs `InboundMessage(channel="system", sender_id="subagent", ...)` with the announcement payload as `content`
- **AND** publishes it via `bus.publish_inbound(...)`
- **AND** `AgentLoop.run()` consumes it on its next iteration and produces a user-facing summary

#### Scenario: Cron and heartbeat bypass the bus

- **GIVEN** the daemon is running
- **WHEN** a cron job or heartbeat tick fires
- **THEN** the dispatcher calls `agent.process_direct(content, session_key=...)` and awaits the returned string
- **AND** no `InboundMessage` is published to the bus for that dispatch
- **AND** no `OutboundMessage` is consumed from the bus for that dispatch

---

### Requirement: Outbound queue has a single REPL consumer

`MessageBus.publish_outbound` SHALL be invoked by the agent core (`AgentLoop._dispatch`, the `MessageTool` in `mybot/agent/tools/message.py`, and error paths) to surface responses, error messages, and tool-emitted text. `MessageBus.consume_outbound` SHALL have exactly one consumer: the REPL renderer in interactive CLI mode.

`agent.process_direct(...)` callers (cron, heartbeat, single-shot CLI when configured to skip the bus) SHALL NOT consume from the outbound queue, since `process_direct` returns the response string directly.

#### Scenario: REPL renders an outbound message

- **GIVEN** the REPL is running and the agent has produced a response
- **WHEN** `_dispatch` publishes an `OutboundMessage` via `publish_outbound`
- **THEN** the REPL renderer consumes it via `consume_outbound`
- **AND** prints the `content` field to stdout with the configured Rich formatting

#### Scenario: Cron job does not consume outbound

- **GIVEN** a cron job is running via `agent.process_direct(...)`
- **WHEN** the agent produces a response string
- **THEN** the response is returned by `process_direct` directly
- **AND** the outbound queue is not consumed by the cron path

---

### Requirement: Trimmed message data model

`InboundMessage` SHALL carry exactly these fields and no others:

- `channel: Literal["cli", "system"]`
- `sender_id: str`
- `chat_id: str`
- `content: str`
- `timestamp: datetime` (defaulted to `datetime.now()` at construction)
- `session_key_override: str | None` (defaulted to `None`)
- a `session_key` property derived from `session_key_override` or `f"{channel}:{chat_id}"`

`OutboundMessage` SHALL carry exactly these fields and no others:

- `channel: Literal["cli", "system"]`
- `chat_id: str`
- `content: str`
- `is_progress: bool` (defaulted to `False`) — set to `True` on intermediate progress / tool-call hint messages so the REPL renderer can dim them with the `↳ ...` prefix instead of rendering them as a final response.
- `is_tool_hint: bool` (defaulted to `False`) — set to `True` when `is_progress` is `True` AND the underlying event is a tool-call hint (vs. a free-form progress note). Reserved for renderer differentiation; consumers MAY treat it as a sub-flag of `is_progress`.

The fields `media`, `reply_to`, and a generic `metadata: dict[str, Any]` SHALL NOT exist on either class. Any future need to attach auxiliary data MUST go through a deliberate spec change that adds explicit typed fields, rather than re-introducing an open `dict[str, Any]` extension point.

#### Scenario: Vestigial nanobot fields are absent

- **WHEN** a developer inspects the dataclass definitions in `mybot/bus/events.py`
- **THEN** `InboundMessage` exposes only the fields listed in this requirement
- **AND** `OutboundMessage` exposes only the fields listed in this requirement
- **AND** there is no `media`, `reply_to`, or generic `metadata` attribute on either class

#### Scenario: Progress messages are flagged via typed fields

- **GIVEN** the agent core publishes an intermediate progress message via the bus
- **WHEN** the message is constructed
- **THEN** `OutboundMessage(channel=..., chat_id=..., content=..., is_progress=True, is_tool_hint=<bool>)` is used
- **AND** the REPL renderer reads `msg.is_progress` (not `msg.metadata.get("_progress")`) to decide whether to dim the line with `↳ ...`
- **AND** final response messages omit both flags (defaulting to `False`)

##### Example: progress vs final outbound shapes

| Use case             | Construction                                                                                | Renderer treats as     |
| -------------------- | ------------------------------------------------------------------------------------------- | ---------------------- |
| Final response       | `OutboundMessage(channel="cli", chat_id="direct", content="Done.")`                         | full response, normal  |
| Progress note        | `OutboundMessage(channel="cli", chat_id="direct", content="thinking…", is_progress=True)`   | dimmed `↳ thinking…`   |
| Tool-hint progress   | `OutboundMessage(channel="cli", chat_id="direct", content="web_search(...)", is_progress=True, is_tool_hint=True)` | dimmed `↳ web_search(...)` |

#### Scenario: Channel field rejects unknown values at type-check time

- **GIVEN** a developer attempts to construct `InboundMessage(channel="telegram", ...)` or `OutboundMessage(channel="discord", ...)`
- **WHEN** the project is type-checked with a static checker that respects `typing.Literal`
- **THEN** the type checker reports an error
- **AND** runtime construction also raises if a runtime validation layer is present (no runtime validation is required by this requirement, but the type-level constraint MUST be in place)

##### Example: allowed and rejected channel values

| `channel` value | Allowed? | Notes                                  |
| --------------- | -------- | -------------------------------------- |
| `"cli"`         | yes      | REPL / single-shot / cron / heartbeat  |
| `"system"`      | yes      | Subagent fan-in announcements          |
| `"telegram"`    | no       | Removed when nanobot channels were cut |
| `"discord"`     | no       | Same                                   |
| `""`            | no       | Empty string is not a `Literal` member |

---

### Requirement: Documented contract on MessageBus

`mybot/bus/queue.py` SHALL define a `MessageBus` class whose docstring states: (a) the bus is in-process only and per-CLI-invocation, (b) the bus never crosses bot boundaries, (c) the two valid `publish_inbound` patterns described in "Two valid publisher patterns", (d) the single consumer of `consume_inbound` is `AgentLoop.run()`, and (e) the outbound queue is consumed only by the REPL renderer while `agent.process_direct(...)` bypasses the bus.

The module-level docstrings on `mybot/bus/__init__.py`, `mybot/bus/events.py`, and `mybot/bus/queue.py` SHALL describe the actual scope (REPL ↔ agent + subagent fan-in) rather than the legacy phrasing "decoupled channel-agent communication".

The README's project-layout block SHALL describe the `bus/` directory as the REPL ↔ agent queue plus subagent fan-in, NOT as generic "in-process message routing".

#### Scenario: Reader can determine bus scope from docstrings alone

- **GIVEN** a developer who has not seen this spec opens `mybot/bus/queue.py`
- **WHEN** they read the `MessageBus` class docstring
- **THEN** they can answer without reading further code: where the bus lives in process scope, who publishes to it, who consumes from it, and which paths bypass it

#### Scenario: README describes bus accurately

- **WHEN** a reader looks up `bus/` in the README "Project layout" block
- **THEN** the description identifies the bus as the REPL ↔ agent queue plus subagent fan-in
- **AND** does not use the generic phrase "in-process message routing" that suggests broader scope
