"""Add the hooks to your Claude Code settings, or remove them again.

    uv run python install.py              -> install (makes a backup first)
    uv run python install.py --uninstall  -> remove the hooks (also with a backup)
    uv run python install.py --wait 90    -> test with a short wait (seconds) instead of 8 hours

Everything already in ~/.claude/settings.json stays. Only entries containing
"claude-telegram-bridge/hook.py" are added or removed.
(Dutch aliases still work: --verwijder, --wacht.)
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import shutil
import sys

PROJECT = pathlib.Path(__file__).resolve().parent
PYTHON = (PROJECT / ".venv" / "Scripts" / "python.exe").as_posix()  # Windows virtualenv layout
HOOK = (PROJECT / "hook.py").as_posix()
MARKER = "/hook.py"
SETTINGS = pathlib.Path.home() / ".claude" / "settings.json"

LONG_WAIT_S = 8 * 60 * 60  # 8 hours: how long a chat can wait for your answer via Telegram


def command(wait_s: int | None = None) -> str:
    base = f"{PYTHON} {HOOK}"
    return f"{base} --wait {wait_s}" if wait_s else base


def our_hooks(limit_s: int = LONG_WAIT_S) -> dict:
    wait = max(10, limit_s - 100)  # the hook stops just before Claude Code would cut it off
    return {
        # Permission and questions: wait for your button or text (first answer wins, computer or Telegram).
        "PermissionRequest": [{"hooks": [{"type": "command", "command": command(wait), "timeout": limit_s}]}],
        # Done: wait in the background for a message; exit code 2 wakes the chat up again.
        "Stop": [{"hooks": [{"type": "command", "command": command(wait), "asyncRewake": True, "timeout": limit_s}]}],
        # Only pass on (in the background, Claude doesn't wait for these):
        "StopFailure": [{"hooks": [{"type": "command", "command": command(), "async": True, "timeout": 30}]}],
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": command(), "async": True, "timeout": 30}]}],
        "PostToolUse": [{"hooks": [{"type": "command", "command": command(), "async": True, "timeout": 30}]}],
        "PostToolUseFailure": [{"hooks": [{"type": "command", "command": command(), "async": True, "timeout": 30}]}],
        "SessionEnd": [{"hooks": [{"type": "command", "command": command()}]}],
    }


def is_ours(hook: dict) -> bool:
    cmd = hook.get("command", "")
    return HOOK in cmd or ("claude-telegram-bridge" in cmd and MARKER in cmd)


def without_ours(groups: list) -> list:
    """Remove only our hooks, keep everything else."""
    cleaned = []
    for group in groups:
        hooks = [h for h in group.get("hooks", []) if not is_ours(h)]
        if hooks:
            cleaned.append({**group, "hooks": hooks})
    return cleaned


def main() -> int:
    args = sys.argv[1:]
    remove = "--uninstall" in args or "--verwijder" in args
    limit_s = LONG_WAIT_S
    for flag in ("--wait", "--wacht"):
        if flag in args:
            limit_s = int(args[args.index(flag) + 1]) + 100
    if not pathlib.Path(PYTHON).exists():
        print(f"Project Python not found ({PYTHON}). Run 'uv sync' first.")
        return 1

    settings = json.loads(SETTINGS.read_text(encoding="utf-8")) if SETTINGS.exists() else {}
    if SETTINGS.exists():
        backup = SETTINGS.with_name(f"settings.json.backup-{dt.datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(SETTINGS, backup)
        print(f"Backup made: {backup}")

    hooks = settings.get("hooks", {})
    for event in list(hooks):
        hooks[event] = without_ours(hooks[event])
        if not hooks[event]:
            del hooks[event]
    if not remove:
        for event, groups in our_hooks(limit_s).items():
            hooks.setdefault(event, []).extend(groups)
    if hooks:
        settings["hooks"] = hooks
    else:
        settings.pop("hooks", None)

    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if remove:
        print("Hooks removed.")
    else:
        print(f"Hooks installed for: {', '.join(our_hooks())} (max wait {limit_s - 100} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
