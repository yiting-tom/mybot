## Why

We want a CLI-only personal AI assistant. nanobot is the right starting point — small, readable, complete agent core — but it carries ten chat-platform integrations (Telegram / Discord / Slack / WhatsApp / Feishu / DingTalk / QQ / Email / Matrix / Mochat) and the Node.js bridge that supports them. Those bring large dependency surfaces, schema noise, and conceptual weight (`ChannelsConfig`, gateway, message routing) that we don't need.

Stripping the channels lets us focus on what we actually use: a terminal agent that can be pointed at any folder, with persistent sessions, scheduled tasks, memory, skills, and MCP. We also want **multiple bots** — one per project — because a single global workspace doesn't scale across coding / writing / ops contexts.

## What Changes

- **Fork nanobot's core into `mybot/`**, renaming the package and rebranding strings (`~/.nanobot/` → `~/.mybot/`, `NANOBOT_*` env → `MYBOT_*`).
- **Remove all channel integrations** (`channels/`, `bridge/`) and their config schemas (`ChannelsConfig`, `WhatsAppConfig`, `TelegramConfig`, etc.).
- **Remove the `gateway` and `channels` CLI subcommands** plus the channel-only deps (`python-telegram-bot`, `slack-sdk`, `lark-oapi`, `qq-botpy`, `dingtalk-stream`, `python-socketio`, `msgpack`, `slackify-markdown`, `socksio`, `websockets`, `websocket-client`).
- **Keep the `channel:chat_id` plumbing string** inside the bus / session layer so the agent loop, MessageBus, and SessionManager don't need rewriting — it's just pinned to `"cli"` / `"system"`.
- **Add multi-bot support**: `mybot create / list / delete / set-folder` plus a `-w` global option resolving to either a named workspace under `~/.mybot/workspaces/<name>/` or an explicit path.
- **Add a chat shortcut**: `mybot <bot_name> [message]` rewrites to `mybot -w <bot_name> agent [-m message]`. Reserved subcommands (e.g. `cron`) chain through naturally — `mybot work cron list`.
- **Decouple the agent's working folder from its data dir**: `mybot create <name> --folder <path>` (or `set-folder` later) writes the path into `agents.defaults.workspace` so config / sessions / cron live in `~/.mybot/workspaces/<name>/` while the agent reads / writes files in any directory.
- Update `pyproject.toml` (rename, slim deps, drop bridge force-include).
- Write `README.md` covering the new mental model (data dir vs workspace folder), bot management commands, and the chat shortcut.

## Non-Goals

- **No `mybot daemon` yet** — the cron service and HEARTBEAT.md tick exist but nothing currently runs the loop in the background. Tracked as roadmap.
- **Not adding new channels in a different form** (web UI, REST gateway). If a non-CLI surface comes back, it'll be a separate change.
- **Not introducing a plugin system** for channels / transports. The bus stays internal.
- **Not migrating an existing nanobot install** automatically. Users start fresh.
- **No tests in this change.** Smoke testing was manual (CLI invocations after install). Test coverage is a follow-up.

## Capabilities

### New Capabilities

- `bot-management`: Multi-bot lifecycle — create, list, delete, switch active bot, set workspace folder.
- `chat-shortcut`: First-positional-arg dispatch so `mybot <name>` enters chat without an explicit subcommand.
- `workspace-resolution`: Dual-path resolver mapping `-w NAME` → `~/.mybot/workspaces/NAME/` and `-w PATH` → explicit dir, with `MYBOT_WORKSPACE` env fallback.
- `agent-folder-override`: Per-bot persistent agent workspace path (`agents.defaults.workspace`), set at create time or via `set-folder`.

### Modified Capabilities

(No prior specs — this is the first change in a fresh repo.)

## Impact

**Code removed**

- `mybot/channels/` — entire directory (was Telegram / Discord / Slack / WhatsApp / Feishu / DingTalk / QQ / Email / Matrix / Mochat clients).
- `bridge/` — Node.js WhatsApp bridge.
- `ChannelsConfig` and all per-channel pydantic models in `config/schema.py`.
- `gateway`, `channels status`, `channels login`, `_get_bridge_dir` from `cli/commands.py`.
- `channels_config` parameter on `AgentLoop`.

**Code added / changed**

- `mybot/utils/helpers.py` — `resolve_data_dir`, `set_active_data_dir`, `list_named_workspaces`, module-level active dir.
- `mybot/cli/commands.py` — `create`, `list`, `delete`, `set-folder` top-level commands; `RESERVED_COMMANDS` set; `_parse_chat_shortcut` argv intercept; `run()` entry point.
- `mybot/config/schema.py` — `agents.defaults.workspace` defaults to `""` and `Config.workspace_path` falls back to `<data_dir>/workspace`.
- `mybot/config/loader.py` — `get_config_path()` resolves to active data dir.
- `mybot/agent/loop.py` — `channels_config` parameter dropped; rest unchanged.
- `mybot/agent/tools/message.py` — schema simplified (removed `channel`/`chat_id` from public tool surface; routing context still set internally).
- `pyproject.toml` — package name `mybot`, slim deps, script entry `mybot.cli.commands:run`.

**Dependencies removed**: `python-telegram-bot[socks]`, `slack-sdk`, `slackify-markdown`, `lark-oapi`, `qq-botpy`, `dingtalk-stream`, `python-socketio`, `msgpack`, `python-socks[asyncio]`, `socksio`, `websockets`, `websocket-client`, plus the `matrix` extras.

**External**: First push to `git@github.com:yiting-tom/mybot.git` (`main`).

**LOC change**: nanobot core reference was ~3,935 lines; mybot is ~2,400 lines after stripping channels (≈40% reduction in surface area).
