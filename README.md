# Claude Telegram Bridge

**English** · [Nederlands](README.nl.md)

Get a Telegram message when **Claude Code** needs you, and answer from your phone.
Claude then continues in the same chat, on your own computer.

Built for **Claude Desktop (Code tab) on Windows**, on top of the official
[Claude Code hooks](https://code.claude.com/docs/en/hooks). No second AI, no paid services,
no cloud server: a small Python program on your own PC and a Telegram bot.

![License: MIT](https://img.shields.io/badge/license-MIT-blue) ![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue) ![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey)

---

## Features

- **Permission requests** with ✅ Allow / ❌ Deny buttons (or type a reason to deny).
- **Questions from Claude** with the choices as buttons, or type your own answer.
- **"Claude is done"** with a formatted summary, plus the *next step* question from the Claude app as buttons.
- **Continue from Telegram:** reply to a "done" message and the idle chat wakes up and carries on.
- **One Telegram topic per Claude chat**, named after the chat, so replies always reach the right one.
- **Home / away switch:** `/home` = no notifications, `/away` = everything comes to your phone, including what was already waiting.
- **`/status`** overview and **reminders** after 30 minutes.
- **Answer wherever you are:** whoever answers first (computer or phone) wins; the Telegram message updates itself.
- **Safe by design:** only your Telegram account is accepted, the bot token never leaves your PC or its log, and if the bridge is down Claude simply behaves as normal.
- **Survives reboots:** starts at logon, with a watchdog that restarts it within 3 minutes.
- English and Dutch messages.

## How it works

```
Claude Code (your PC)  <->  hook.py  <->  bridge.py  <->  Telegram Bot API  <->  you (phone)
```

1. **`hook.py`** is started by Claude Code at fixed moments (official hook events:
   `PermissionRequest`, `Stop`, `StopFailure`, `UserPromptSubmit`, `PostToolUse`,
   `PostToolUseFailure`, `SessionEnd`).
2. **`bridge.py`** runs in the background. It has a local endpoint on `127.0.0.1:8765`
   (protected by a shared secret) and talks to Telegram via long polling, so no open ports are needed.
3. The hook hands the event to the bridge and waits (up to 8 hours) for your answer.
4. After "done", the chat keeps listening: a `Stop` hook with `asyncRewake` wakes Claude up
   when you reply.

## Requirements

- Windows 10/11
- [Claude Desktop](https://claude.ai/download) with Claude Code
- [uv](https://docs.astral.sh/uv/) (Python 3.10+ is installed by uv if needed)
- A Telegram account

## Installation

1. **Create a bot:** send `/newbot` to [@BotFather](https://t.me/BotFather) and keep the token secret.
2. **Find your user id:** send any message to [@userinfobot](https://t.me/userinfobot).
3. **Optional, topics per chat:** @BotFather → *Open* (mini app) → your bot → enable **Threaded Mode**.
4. **Configure:** copy [`.env.example`](.env.example) to `%USERPROFILE%\.claude-telegram\.env` and fill it in.
5. **Install dependencies** in this folder:
   ```powershell
   uv sync
   ```
6. **Start the bridge at logon** (Windows Task Scheduler) and start it once now:
   ```powershell
   powershell -ExecutionPolicy Bypass -File autostart.ps1
   Start-ScheduledTask -TaskName "Claude Telegram Bridge"
   ```
7. **Install the hooks** into `~/.claude/settings.json` (a backup is made first):
   ```powershell
   uv run python install.py
   ```
8. **Test:** press *Start* in your bot chat, send `/status`, then `/away`, and let Claude ask you something.

## Usage

| In Telegram | What happens |
|---|---|
| `/away` (or `/weg`) | Notifications on. Everything waiting for you is sent right away. |
| `/home` (or `/thuis`) | Notifications off, for when you're at your computer. |
| `/status` | What is waiting for you, and the current switch position. |
| Tap a button | Answer a question, allow/deny, or pick the next step. |
| Type a message | Your own answer. Inside a topic it always goes to that Claude chat. |

## Configuration

All settings live in `%USERPROFILE%\.claude-telegram\` (never in the repository):

| File | Contents |
|---|---|
| `.env` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_ID`, `BRIDGE_LANGUAGE` (`en`/`nl`), `BRIDGE_OWNER_NAME` |
| `bridge.json` | Port and shared secret of the local endpoint (created automatically) |
| `state.json` | Home/away switch and which topic belongs to which Claude chat |
| `logs\bridge.log` | Log file (the bot token is deliberately never logged) |

Set `CLAUDE_TELEGRAM_DIR` to use a different folder.

## Troubleshooting

| Symptom | Fix |
|---|---|
| The bot doesn't answer `/status` | The bridge isn't running. Wait up to 3 minutes for the watchdog, or run `Start-ScheduledTask -TaskName "Claude Telegram Bridge"`. Check `logs\bridge.log`. |
| No notifications | Is the switch on `/away`? Check with `/status`. |
| "Port 8765 is in use" in the log | A bridge is already running; nothing to do. |
| "This has already been handled" on a button | It was answered on the computer, or it expired. |
| A message arrives without formatting | Telegram rejected the formatting, so the bridge sent plain text instead. |
| Bot token leaked | Send `/revoke` to @BotFather, put the new token in `.env`, restart the bridge. |

Restart the bridge (e.g. after changing the code):

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'bridge\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-ScheduledTask -TaskName "Claude Telegram Bridge"
```

## Uninstall

```powershell
uv run python install.py --uninstall
powershell -ExecutionPolicy Bypass -File autostart.ps1 -Uninstall
```

Claude then works exactly as before. Backups of your Claude settings are next to
`%USERPROFILE%\.claude\settings.json` (`settings.json.backup-...`).

## Limitations

- Your PC has to be **on, awake and logged in**. Disable sleep while plugged in. After a reboot
  (e.g. Windows Update) nothing runs until you log in.
- Claude chats don't resume by themselves after a reboot.
- A free-text Telegram reply after "done" reaches Claude as a *message via the bot*, not as text
  you typed in the chat yourself. Normal requests are carried out; for risky actions Claude
  asks for permission first (which you can grant with a button). An answer to a *question* from
  Claude counts as your real answer.
- While a question is waiting, any text you type in that topic is taken as the answer.
- Windows only for now (paths, Task Scheduler). macOS/Linux would need a different autostart and venv path.

## Security

- Only messages from `TELEGRAM_ALLOWED_USER_ID` are processed; everyone else is ignored silently.
- The local endpoint only listens on `127.0.0.1` and requires a shared secret.
- Telegram cannot run commands on your PC: it can only answer questions, allow/deny permission
  requests, and send text to a chat that is waiting for you. Claude's own permission rules still apply.
- Messages travel through Telegram's servers (bot chats are not end-to-end encrypted): don't send secrets.
- Anyone with access to your Telegram account can steer Claude: enable two-step verification in Telegram.

## Background: why hooks?

Anthropic offers an official Telegram plugin via [channels](https://code.claude.com/docs/en/channels),
but it requires starting Claude Code with `claude --channels`, which the Claude Desktop app does
not do. Hooks do run in Desktop sessions. Before building, a spike ([`spike/`](spike/)) verified in
a real Desktop session that:

- `PermissionRequest` also fires for `AskUserQuestion`, and a hook's answer wins from the on-screen
  dialog (and answering on screen does not wait for the hook);
- a hook can answer `AskUserQuestion` with free text via `updatedInput.answers`, and Claude sees it
  as the user's answer;
- a `Stop` hook with `asyncRewake` wakes an idle session immediately on exit code 2, also after
  more than the default 10-minute timeout.

Markdown is converted with [telegramify-markdown](https://github.com/sudoskys/telegramify-markdown)
0.5.x (pure Python). Telegram integration uses [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot).

## Project structure

| File | Purpose |
|---|---|
| `bridge.py` | The bridge: Telegram bot + local endpoint |
| `hook.py` | Hook script started by Claude Code (standard library only) |
| `messages.py` | All bot texts, English and Dutch |
| `formatting.py` | Markdown → Telegram formatting |
| `install.py` | Adds/removes the hooks in `~/.claude/settings.json` |
| `autostart.ps1` | Windows Task Scheduler task + watchdog |
| `spike/` | The experiment that proved the approach |

## License

[MIT](LICENSE) © 2026 Indy Heynis
