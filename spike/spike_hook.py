"""Spike: prove which Claude Code hooks fire in Claude Desktop sessions and whether their answers are honoured.

This was the first step of the project, before writing the real bridge. It:
- only acts for session ids listed in spike_config.json (other sessions: one short line in
  logs/skipped.jsonl, nothing else);
- logs every hook call to logs/events.jsonl;
- only intervenes on test input containing the word SPIKE;
- wakes a finished session only if rewake_armed.json exists (one-shot: the file is deleted).

No network, no Telegram: measuring only. Results are summarised in README.md ("Background").
"""
import datetime as dt
import json
import pathlib
import sys
import time

BASE = pathlib.Path(__file__).resolve().parent
LOGS = BASE / "logs"
CONFIG = BASE / "spike_config.json"
ARM = BASE / "rewake_armed.json"


def now() -> str:
    return dt.datetime.now().isoformat(timespec="milliseconds")


def append(name: str, record: dict) -> None:
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / name, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def emit(obj: dict) -> None:
    # ensure_ascii (default) keeps stdout safe regardless of the Windows code page.
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def first_option_answers(questions: list) -> dict:
    return {
        q["question"]: q["options"][0]["label"]
        for q in questions
        if q.get("question") and q.get("options")
    }


def has_marker(questions: list, marker: str) -> bool:
    return any(marker in q.get("question", "") for q in questions)


def main() -> int:
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        append("errors.jsonl", {"t": now(), "raw": raw[:2000]})
        return 0

    event = data.get("hook_event_name", "?")
    session_id = data.get("session_id")
    config = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    if session_id not in config.get("session_ids", []):
        append("skipped.jsonl", {"t": now(), "event": event, "session_id": session_id})
        return 0

    append("events.jsonl", {"t": now(), "event": event, "payload": data})
    tool = data.get("tool_name")
    tool_input = data.get("tool_input") or {}

    # Test: can a PreToolUse hook answer Claude's question (AskUserQuestion)?
    if event == "PreToolUse" and tool == "AskUserQuestion":
        questions = tool_input.get("questions") or []
        answers = None
        if has_marker(questions, "SPIKE-FREE"):
            # Free text that is NOT one of the options (like a Telegram reply).
            answers = {
                q["question"]: "Free text from the user via Telegram: explain it with an example please 🙂"
                for q in questions
                if q.get("question")
            }
        elif has_marker(questions, "SPIKE-PRE"):
            answers = first_option_answers(questions)
        if answers:
            time.sleep(5)
            out = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "updatedInput": {**tool_input, "answers": answers},
                }
            }
            append("decisions.jsonl", {"t": now(), "event": event, "output": out})
            emit(out)
        return 0

    # Test: does a PermissionRequest answer win from the dialog in the Desktop app?
    if event == "PermissionRequest":
        decision = None
        if tool == "Bash" and "SPIKE-PERMISSION-TEST" in tool_input.get("command", ""):
            decision = {"behavior": "allow"}
        elif tool == "AskUserQuestion":
            questions = tool_input.get("questions") or []
            if has_marker(questions, "SPIKE-PERM"):
                decision = {
                    "behavior": "allow",
                    "updatedInput": {**tool_input, "answers": first_option_answers(questions)},
                }
        if decision:
            time.sleep(8)
            out = {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}
            append("decisions.jsonl", {"t": now(), "event": event, "output": out})
            emit(out)
        return 0

    # Test: does a Stop hook with asyncRewake wake up an idle session?
    if event == "Stop" and ARM.exists():
        arm = json.loads(ARM.read_text(encoding="utf-8"))
        ARM.unlink()
        delay = int(arm.get("delay", 20))
        append("decisions.jsonl", {"t": now(), "event": event, "rewake_in_seconds": delay})
        time.sleep(delay)
        message = arm.get("message", "SPIKE-REWAKE")
        append("decisions.jsonl", {"t": now(), "event": event, "rewake_fired": message})
        sys.stderr.buffer.write(message.encode("utf-8"))
        sys.stderr.flush()
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
