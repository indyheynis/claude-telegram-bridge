"""The hook: Claude Code starts this script at fixed moments (hooks).

It passes the event to the bridge (bridge.py) via the local counter, waits for your
answer from Telegram if needed, and hands that answer back to Claude.

Safety net: if the bridge is not running or anything goes wrong, this script does
NOTHING (exit 0, no output). Claude then behaves exactly as without the bridge.

Usage (by Claude Code, configured by install.py):
    python hook.py            -> only pass the event on, don't wait
    python hook.py --wait N   -> wait at most N seconds for an answer
    python hook.py --set-mode weg|thuis|away|home
                              -> flip the home/away switch (fallback of the /weg and /thuis commands)
Standard library only (plus messages.py from this folder), so it starts fast.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.request

from messages import Messages, mode_for_command

CONFIG_DIR = pathlib.Path(os.environ.get("CLAUDE_TELEGRAM_DIR", pathlib.Path.home() / ".claude-telegram"))
BRIDGE_FILE = CONFIG_DIR / "bridge.json"


def wait_seconds() -> float:
    if "--wait" in sys.argv:
        try:
            return float(sys.argv[sys.argv.index("--wait") + 1])
        except (IndexError, ValueError):
            pass
    return 0.0


def messages() -> Messages:
    language = os.environ.get("BRIDGE_LANGUAGE", "")
    try:
        for line in (CONFIG_DIR / ".env").read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("BRIDGE_LANGUAGE=") and not language:
                language = line.split("=", 1)[1].strip()
    except OSError:
        pass
    return Messages(language.lower() or "en")


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def ask_bridge(data: dict, wait_s: float) -> dict:
    conf = json.loads(BRIDGE_FILE.read_text(encoding="utf-8"))
    data["_wait_s"] = wait_s
    request = urllib.request.Request(
        f"http://127.0.0.1:{conf['port']}/hook",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Bridge-Secret": conf["secret"]},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never via a proxy
    with opener.open(request, timeout=wait_s + 30 if wait_s else 5) as response:
        return json.loads(response.read().decode("utf-8"))


def set_mode(name: str) -> int:
    """Fallback for the /weg and /thuis command files: same as the hook, but prints plain text."""
    try:
        result = ask_bridge({"hook_event_name": "UserPromptExpansion", "command_name": name}, 0)
        print(result.get("reason") or "?")
    except Exception:
        print(messages()("bridge_down"))
    return 0


def main() -> int:
    if "--set-mode" in sys.argv:
        return set_mode(sys.argv[-1])
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return 0
    event = data.get("hook_event_name", "")
    switch = event == "UserPromptExpansion" and mode_for_command(data.get("command_name"))

    try:
        result = ask_bridge(data, wait_seconds())
    except Exception:
        if switch:  # our own /weg or /thuis: say so instead of sending it to Claude
            emit({"decision": "block", "reason": messages()("bridge_down")})
        return 0  # bridge not running or not responding: do nothing

    action = result.get("action")

    if switch:
        if action == "block":  # switch flipped; the command never reaches Claude (costs nothing)
            emit({"decision": "block", "reason": result.get("reason", "")})
        return 0

    if event == "PermissionRequest":
        if action == "allow":
            emit({"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}})
        elif action == "answers":
            updated = {**(data.get("tool_input") or {}), "answers": result.get("answers") or {}}
            emit({"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                         "decision": {"behavior": "allow", "updatedInput": updated}}})
        elif action == "deny":
            emit({"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                         "decision": {"behavior": "deny", "message": result.get("message", "")}}})
        return 0

    if event == "Stop" and action == "message":
        # asyncRewake: exit code 2 wakes up the idle chat; Claude sees this text.
        sys.stderr.buffer.write(result.get("text", "").encode("utf-8"))
        sys.stderr.flush()
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
