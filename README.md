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

To audit, inspect, or prune session history without entering the REPL, use [`mybot <bot> session`](#sessions).

### Sessions

Each bot persists every conversation as a JSONL file under `<workspace_folder>/sessions/`. A new session is created per channel/chat — the interactive REPL uses `cli:direct`, each cron job gets `cron:<id>`, the heartbeat uses `heartbeat`.

```bash
mybot <name> session list                    # table: key, last updated, message count, size
mybot <name> session show <key>              # render the conversation (role, timestamp, content)
mybot <name> session show <key> --max 20     # only the last 20 messages
mybot <name> session clear <key>             # delete one session (confirms; -y to skip)
mybot <name> session clear --all             # delete every session for this bot
```

`/new` (in the REPL) archives the active session into memory. `mybot <bot> session clear` deletes the file outright. They're complementary — use `/new` when you want the agent to remember what was discussed; use `clear` to wipe history that should never have been kept.

`session show` truncates large `tool` messages to 200 characters in the rendered view. The raw JSONL on disk is unchanged.

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

Cron jobs only fire when a daemon is running — see *Running as a daemon* below. Stored per-bot; isolated from other bots' jobs.

The agent itself can also create cron jobs via the `cron` tool when you ask it to ("remind me at 6pm…").

## Heartbeat (`HEARTBEAT.md`)

Each bot's workspace folder has a `HEARTBEAT.md`. While the daemon is running, the agent reads it on every heartbeat tick (default every 30 minutes) and decides whether there are tasks to run. You can edit it manually or ask the agent to manage it.

```markdown
## Periodic Tasks

- [ ] Check inbox for urgent emails
- [ ] Summarize today's GitHub notifications
```

## Running as a daemon

The cron service and heartbeat both need a host process. `mybot daemon` is that host — a foreground supervisor for one bot.

```bash
mybot <name> daemon                      # foreground; Ctrl-C to stop
mybot <name> daemon --once               # run every currently-due cron job and exit (skips heartbeat)
mybot <name> daemon --log-file ~/log.txt # mirror stdout to a file
```

Output is timestamped, prefixed by source:

```
2026-05-03 16:00:00 [daemon]         Daemon started for bot 'work' (cron jobs: 2, heartbeat: every 1800s)
2026-05-03 16:01:00 [cron:1a2b3c4d]    ↳ web_search("AAPL earnings")
2026-05-03 16:01:08 [cron:1a2b3c4d]  AAPL reported Q2 EPS of $2.18, above consensus.
2026-05-03 16:30:00 [heartbeat]      Reviewing HEARTBEAT.md…
2026-05-03 16:30:09 [heartbeat]      No active tasks.
```

A PID lockfile at `<data_dir>/daemon.pid` prevents two long-running daemons against the same bot. `--once` doesn't lock — safe to combine with system cron.

### systemd (Linux)

Run one service per bot. Replace `BOT_NAME` and the binary path as needed.

`~/.config/systemd/user/mybot-daemon@.service`:

```ini
[Unit]
Description=mybot daemon (%i)
After=network.target

[Service]
Type=simple
ExecStart=%h/.local/bin/mybot %i daemon
Restart=always
RestartSec=10
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=%h

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now mybot-daemon@work
journalctl --user -u mybot-daemon@work -f
```

To survive logout: `loginctl enable-linger $USER`.

### launchd (macOS)

`~/Library/LaunchAgents/com.mybot.work.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>             <string>com.mybot.work</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/USERNAME/.local/bin/mybot</string>
    <string>work</string>
    <string>daemon</string>
  </array>
  <key>RunAtLoad</key>         <true/>
  <key>KeepAlive</key>         <true/>
  <key>StandardOutPath</key>   <string>/Users/USERNAME/Library/Logs/mybot-work.log</string>
  <key>StandardErrorPath</key> <string>/Users/USERNAME/Library/Logs/mybot-work.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.mybot.work.plist
tail -f ~/Library/Logs/mybot-work.log
launchctl unload ~/Library/LaunchAgents/com.mybot.work.plist
```

### Windows (Task Scheduler)

`mybot <name> daemon` runs on Windows 10 / 11 under any console host (PowerShell, Windows Terminal, cmd.exe). Press Ctrl-C to stop.

Caveat: Windows does not deliver SIGTERM to user code, so only Ctrl-C (SIGINT) is wired for graceful shutdown. External supervisors that need an ordered stop must send Ctrl-Break (`CTRL_BREAK_EVENT`) — Python translates it to SIGBREAK — or terminate the process. Send `taskkill /PID <pid>` for an immediate kill.

For periodic execution without a long-running process, use **Task Scheduler** with `--once`:

```powershell
schtasks /Create /SC MINUTE /MO 5 /TN "mybot-work" `
  /TR "C:\Python311\Scripts\mybot.exe work daemon --once" /F
```

Or import a Task Scheduler XML definition:

```xml
<?xml version="1.0" encoding="UTF-16"?>
<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <TimeTrigger>
      <Repetition>
        <Interval>PT5M</Interval>
      </Repetition>
      <StartBoundary>2026-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>C:\Python311\Scripts\mybot.exe</Command>
      <Arguments>work daemon --once</Arguments>
    </Exec>
  </Actions>
</Task>
```

Save as `mybot-work.xml` and import:

```powershell
schtasks /Create /TN "mybot-work" /XML mybot-work.xml
```

### system cron + `--once`

If you already have OS cron and don't want a long-running process:

```cron
*/5 * * * * /Users/me/.local/bin/mybot work daemon --once >> ~/.mybot/work.log 2>&1
```

Related: [`cron list`](#scheduled-tasks-cron) / [`set-folder`](#bot-management).

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
mybot <name> daemon [--once|-l FILE]   run cron + heartbeat host
mybot <name> session list              list sessions
mybot <name> session show <key>        render a session
mybot <name> session clear [<key>|--all] [-y]   delete sessions
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

- [x] `mybot daemon` — long-running process to actually fire cron + heartbeat ticks
- [x] `mybot session list/show/clear` — manage conversation history from the CLI
- [ ] `mybot config get/set` — edit config without opening the JSON
- [ ] `mybot tools list` — show registered tools (incl. MCP-discovered)
- [ ] Smoke tests

## License

MIT — same as upstream nanobot.
