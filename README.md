# 🐈 mybot

Personal CLI AI assistant. Stripped-down fork of [nanobot](https://github.com/HKUDS/nanobot) — **core agent only, no chat-platform integrations**.

You get the agent loop, providers, sessions, cron, heartbeat, memory, skills, and MCP — driven from your terminal. No Telegram, Discord, Slack, WhatsApp, etc.

## Why mybot?

- **One bot per project.** Each "bot" has its own config, sessions, cron jobs, and working folder.
- **`mybot <bot_name>` opens a chat.** No subcommand needed for the common case.
- **Point a bot at any folder.** The agent reads/writes files there — your repo, your notes, your scratch dir.
- **Lightweight.** ~3000 lines after stripping channels.

## Install

```bash
pip install -e .
```

Requires Python ≥ 3.11.

## Quick start

```bash
# 1. Create a bot pointed at the folder you want the agent to work in
mybot create coding --folder ~/projects/myrepo

# 2. Add your API key
$EDITOR ~/.mybot/workspaces/coding/config.json
# → providers.openrouter.apiKey = "sk-or-v1-..."

# 3. Chat
mybot coding                    # interactive
mybot coding "summarize main.py"   # single-shot
```

Get an API key: [OpenRouter](https://openrouter.ai/keys) (recommended), or any provider listed below.

## Bot management

```bash
mybot create <name>                    # create a bot under ~/.mybot/workspaces/<name>/
mybot create <name> --folder <path>    # ...with a custom agent workspace folder
mybot create                           # create the default bot at ~/.mybot/
mybot list                             # show all bots and their folders
mybot delete <name>                    # remove bot (confirms first; -y to skip)
mybot <name> set-folder <path>         # change a bot's workspace folder
mybot <name> set-folder -              # reset folder to default
```

`mybot list` example:

```
                              Bots
┌───────────┬──────────────────────────────┬───────────────────────────┬────────┐
│ Name      │ Data Dir                     │ Workspace Folder          │ Active │
├───────────┼──────────────────────────────┼───────────────────────────┼────────┤
│ (default) │ ~/.mybot                     │ ~/.mybot/workspace        │ ✓      │
│ coding    │ ~/.mybot/workspaces/coding   │ ~/projects/myrepo         │        │
│ notes     │ ~/.mybot/workspaces/notes    │ ~/Documents/notes         │        │
└───────────┴──────────────────────────────┴───────────────────────────┴────────┘
```

**Data Dir** holds config, sessions, cron jobs, CLI history.
**Workspace Folder** is what the agent reads/writes — files, memory, skills.

## Chatting with a bot

```bash
mybot <name>                  # interactive REPL
mybot <name> "<message>"      # single shot, prints reply, exits
mybot <name> hello world      # multi-word message also works
```

In interactive mode:

| Command | Effect |
|---------|--------|
| `/new`  | Archive the current session and start fresh |
| `/stop` | Cancel an in-flight task |
| `/help` | Show available commands |
| `exit`, `quit`, `:q`, Ctrl-D | Quit |

## Workspace folders

Each bot has two distinct directories:

| Directory | Contents | Where |
|-----------|----------|-------|
| **Data dir** | `config.json`, `sessions/`, `cron/jobs.json`, `history/cli_history` | `~/.mybot/workspaces/<name>/` (or `~/.mybot/` for default) |
| **Workspace folder** | `HEARTBEAT.md`, `memory/MEMORY.md`, `memory/HISTORY.md`, `skills/`, `USER.md`, `AGENTS.md`, `SOUL.md`, `TOOLS.md` | `<data_dir>/workspace` by default, or any folder you set with `--folder` |

This split lets you point one bot at a code repo while keeping its chat history private:

```bash
mybot create work-bot --folder ~/work/projectA
# → bot's data lives in ~/.mybot/workspaces/work-bot/
# → agent edits files in ~/work/projectA/
```

## Workspace selection

There are three ways to pick which bot a command targets:

```bash
mybot <name> ...                       # bot-name shortcut (preferred)
mybot -w <name> ...                    # explicit flag
MYBOT_WORKSPACE=<name> mybot ...       # environment variable
```

`-w` also accepts a path (`-w /tmp/sandbox`) for one-off ephemeral bots.

## Scheduled tasks (cron)

```bash
mybot <name> cron add --name daily --message "Good morning!" --cron "0 9 * * *"
mybot <name> cron add --name ping --message "Check status" --every 3600
mybot <name> cron list
mybot <name> cron run <id>             # run once now
mybot <name> cron remove <id>
mybot <name> cron enable <id> --disable
```

Cron jobs are stored per-bot. They only fire when something is actively running them — see *Heartbeat* below.

The agent itself can also create cron jobs via the `cron` tool when you ask it to ("remind me at 6pm…").

## Heartbeat (`HEARTBEAT.md`)

Each bot's workspace folder has a `HEARTBEAT.md`. The agent reads it on every heartbeat tick and decides whether there are tasks to run. You can edit it manually or ask the agent to manage it.

```markdown
## Periodic Tasks

- [ ] Check inbox for urgent emails
- [ ] Summarize today's GitHub notifications
```

> [!NOTE]
> The standalone heartbeat/cron daemon (`mybot gateway` in nanobot) is not yet wired up — see roadmap below.

## Configuration

`~/.mybot/workspaces/<name>/config.json`:

```json
{
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5",
      "provider": "auto",
      "workspace": "/Users/me/projects/myrepo",
      "maxTokens": 8192,
      "temperature": 0.1,
      "memoryWindow": 100
    }
  },
  "providers": {
    "openrouter": { "apiKey": "sk-or-v1-..." }
  },
  "tools": {
    "web": { "search": { "apiKey": "<brave-api-key>" } },
    "exec": { "timeout": 60 },
    "restrictToWorkspace": false,
    "mcpServers": {}
  }
}
```

### Providers

Supported: `custom`, `openrouter`, `anthropic`, `openai`, `deepseek`, `groq`, `gemini`, `minimax`, `aihubmix`, `siliconflow`, `volcengine`, `dashscope` (Qwen), `moonshot` (Kimi), `zhipu`, `vllm` (local), `openai_codex` (OAuth), `github_copilot` (OAuth).

Set the model and the matching API key:

```json
{
  "providers": { "openrouter": { "apiKey": "sk-or-v1-..." } },
  "agents": { "defaults": { "model": "anthropic/claude-opus-4-5" } }
}
```

OAuth providers:

```bash
mybot provider login openai-codex
mybot provider login github-copilot
```

### MCP (Model Context Protocol)

Wire external tool servers into the agent — same config format as Claude Desktop / Cursor:

```json
{
  "tools": {
    "mcpServers": {
      "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
      },
      "remote": {
        "url": "https://example.com/mcp/",
        "headers": { "Authorization": "Bearer xxx" }
      }
    }
  }
}
```

### Sandboxing

Set `tools.restrictToWorkspace: true` to lock all file/shell tools inside the bot's workspace folder.

## CLI reference

```
mybot                                  show help
mybot <name>                           chat with bot
mybot <name> "<msg>"                   one-shot message
mybot create [name] [--folder PATH]    create / refresh a bot
mybot list                             list bots
mybot delete <name> [-y]               delete a bot
mybot <name> set-folder <path|->       change workspace folder
mybot <name> cron …                    cron management
mybot <name> agent --logs              chat with debug logs
mybot status                           show config status
mybot provider login <name>            OAuth login
mybot --version
```

## Project layout

```
mybot/
├── agent/          🧠 Core agent loop (loop, context, memory, subagent, tools)
├── providers/      🤖 LLM providers (LiteLLM + custom + Codex)
├── session/        💬 Per-bot conversation persistence
├── cron/           ⏰ Scheduled jobs
├── heartbeat/      💓 Periodic wake-up
├── bus/            🚌 In-process message routing
├── config/         ⚙️  Pydantic schema + loader
├── skills/         🎯 Bundled skills (github, weather, tmux, …)
├── templates/      📄 Workspace bootstrap files
├── utils/          🔧 Shared helpers (workspace resolution, fs, etc.)
└── cli/            🖥️  Typer commands
```

## What was removed (vs. nanobot)

- All chat-platform channels: Telegram, Discord, Slack, WhatsApp, Feishu, DingTalk, QQ, Email, Matrix, Mochat
- The `gateway` command, `bridge/` (Node.js WhatsApp bridge), and channel-related dependencies (`python-telegram-bot`, `slack-sdk`, `lark-oapi`, `qq-botpy`, `dingtalk-stream`, `python-socketio`, `msgpack`, `websockets`, `slackify-markdown`, `socksio`, etc.)
- The `ChannelsConfig` schema

What's kept: the entire agent core (loop, tools, MCP, memory, subagents, skills), all providers, sessions, cron/heartbeat services.

## Roadmap

- [ ] `mybot daemon` — long-running process to actually fire cron + heartbeat ticks
- [ ] `mybot session list/show/clear` — manage conversation history from the CLI
- [ ] `mybot config get/set` — edit config without opening the JSON
- [ ] `mybot tools list` — show registered tools (incl. MCP-discovered)
- [ ] Smoke tests

## License

MIT — same as upstream nanobot.
