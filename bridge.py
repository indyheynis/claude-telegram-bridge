"""Claude Telegram bridge: the "postman" between Claude Code and your Telegram bot.

What it does:
- talks to Telegram (your bot), only with your own Telegram account;
- opens a local "counter" (HTTP on 127.0.0.1 with a shared secret) where the hook
  script (hook.py) drops off events and picks up your answers;
- switch: /away = notifications go to your phone right away, /home = no notifications;
- /status = overview of what is waiting for you; reminder after 30 minutes;
- formatted messages (headings, lists) like in the Claude app;
- the "next step" question under Claude's last message comes along, with buttons;
- if topics are enabled for the bot: every Claude chat gets its own Telegram topic.

Settings and secrets live in ~/.claude-telegram/ (never in the code):
  .env          bot token, your Telegram user id, language, your name (you fill this in)
  bridge.json   port + shared secret of the local counter (created automatically)
  state.json    switch position (home/away) + which topic belongs to which Claude chat
  logs/         log file (the bot token is never written to it)
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import pathlib
import secrets
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    ReplyParameters,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import formatting as fmt
from messages import Messages

CONFIG_DIR = pathlib.Path(os.environ.get("CLAUDE_TELEGRAM_DIR", pathlib.Path.home() / ".claude-telegram"))
ENV_FILE = CONFIG_DIR / ".env"
BRIDGE_FILE = CONFIG_DIR / "bridge.json"
STATE_FILE = CONFIG_DIR / "state.json"
LOG_FILE = CONFIG_DIR / "logs" / "bridge.log"

DEFAULT_PORT = 8765
REMINDER_AFTER_S = 30 * 60  # remind when something has been waiting for 30 minutes
MAX_REMINDERS = 3
SUMMARY_CHARS = 2500  # max length of the "done" summary in Telegram (before formatting)
TRANSCRIPT_TAIL_BYTES = 3_000_000  # only read the last part of the transcript
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

# Buttons that the Claude app draws itself (no label of their own): message key per action.
APP_ACTIONS = {
    "commit", "create_pr", "merge", "fix_ci", "address_comments",
    "resolve_conflicts", "verify", "archive", "new_session",
}

# Stored switch values (kept in Dutch for backwards compatibility with existing state.json files).
AWAY, HOME = "weg", "thuis"

log = logging.getLogger("bridge")


# --------------------------------------------------------------------------- settings


def setup_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.FileHandler(LOG_FILE, encoding="utf-8")]
    if sys.stdout is not None:  # started invisibly (pythonw) = no console to write to
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    # httpx logs every URL, and those contain the bot token. It must never end up in a log file.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


@dataclass
class Settings:
    token: str
    user_id: int
    language: str
    owner: str


def load_settings() -> Settings:
    """Read ~/.claude-telegram/.env (environment variables win). Exits with a clear message if something is missing."""
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USER_ID", "BRIDGE_LANGUAGE", "BRIDGE_OWNER_NAME"):
        if os.environ.get(key):
            values[key] = os.environ[key]

    token = values.get("TELEGRAM_BOT_TOKEN", "")
    user_id = values.get("TELEGRAM_ALLOWED_USER_ID", "")
    if not token or ":" not in token:
        sys.exit(f"No valid TELEGRAM_BOT_TOKEN found in {ENV_FILE}")
    if not user_id.isdigit():
        sys.exit(f"No valid TELEGRAM_ALLOWED_USER_ID (digits only) found in {ENV_FILE}")
    return Settings(
        token=token,
        user_id=int(user_id),
        language=values.get("BRIDGE_LANGUAGE", "en").lower(),
        owner=values.get("BRIDGE_OWNER_NAME", ""),
    )


def load_bridge_conf() -> dict:
    """Port + shared secret of the local counter. Created on first start."""
    try:
        conf = json.loads(BRIDGE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        conf = {}
    changed = False
    if not conf.get("secret"):
        conf["secret"] = secrets.token_urlsafe(32)
        changed = True
    if not conf.get("port"):
        conf["port"] = DEFAULT_PORT
        changed = True
    if changed:
        BRIDGE_FILE.write_text(json.dumps(conf, indent=2), encoding="utf-8")
    return conf


# --------------------------------------------------------------------------- reading the transcript


def transcript_tail(path: str | None) -> list[dict]:
    """The last entries of Claude Code's transcript (JSONL), as a list."""
    if not path:
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - TRANSCRIPT_TAIL_BYTES))
            raw = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = raw.splitlines()
    if len(raw) >= TRANSCRIPT_TAIL_BYTES:
        lines = lines[1:]  # first line is probably cut in half
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return entries


def find_next_step(entries: list[dict]) -> dict | None:
    """The "next step" box (question + buttons) of Claude's last turn, or None.

    Only counts if it was Claude's LAST action in the turn; if we reach a user message
    first, this turn had no question (so you never get an old question).
    """
    for entry in reversed(entries):
        content = (entry.get("message") or {}).get("content")
        if entry.get("type") == "user":
            if isinstance(content, list) and any(c.get("type") == "tool_result" for c in content):
                continue
            return None  # reached the start of the turn
        if entry.get("type") != "assistant" or not isinstance(content, list):
            continue
        for block in reversed(content):
            if block.get("type") == "tool_use":
                if block.get("name", "").endswith("__wrap_up"):
                    return block.get("input") or {}
                return None
    return None


def find_title(entries: list[dict]) -> str | None:
    for entry in reversed(entries):
        if entry.get("type") == "custom-title" and entry.get("customTitle"):
            return entry["customTitle"]
    return None


# --------------------------------------------------------------------------- helpers


def trim(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def describe_tool(t: Messages, name: str, tool_input: dict) -> str:
    """What Claude wants to do, as Markdown."""
    if name in ("Bash", "PowerShell"):
        return f"{t('tool_command')}\n```\n" + trim(tool_input.get("command", ""), 1200) + "\n```"
    if name == "Write":
        return f"{t('tool_write')}\n`" + tool_input.get("file_path", "") + "`"
    if name in ("Edit", "MultiEdit"):
        return f"{t('tool_edit')}\n`" + tool_input.get("file_path", "") + "`"
    if name == "NotebookEdit":
        return f"{t('tool_notebook')}\n`" + tool_input.get("notebook_path", "") + "`"
    if name == "WebFetch":
        return f"{t('tool_fetch')}\n" + tool_input.get("url", "")
    if name == "Read":
        return f"{t('tool_read')}\n`" + tool_input.get("file_path", "") + "`"
    return f"{name}:\n```\n" + trim(json.dumps(tool_input, ensure_ascii=False, indent=1), 800) + "\n```"


def age_text(t: Messages, seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 1:
        return t("age_now")
    if minutes < 60:
        return t("age_min", m=minutes)
    return t("age_hour", h=minutes // 60, m=minutes % 60)


# --------------------------------------------------------------------------- things waiting for you


@dataclass
class Item:
    """Something a Claude chat is waiting on you for."""

    id: str
    kind: str  # "permission" | "question" | "done"
    session_id: str
    title: str
    created: float = field(default_factory=time.time)
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
    questions: list = field(default_factory=list)
    answers: dict = field(default_factory=dict)
    selected: dict = field(default_factory=dict)  # question index -> chosen labels (multi-select)
    summary: str = ""
    ask: str = ""  # question from the "next step" box
    choices: list = field(default_factory=list)  # buttons for that question
    thread_id: int | None = None  # Telegram topic of this Claude chat
    texts: dict = field(default_factory=dict)  # telegram message id -> (text, parse mode)
    question_msgs: dict = field(default_factory=dict)  # telegram message id -> question index
    sent: bool = False
    last_ping: float = 0.0
    reminders: int = 0
    finished: threading.Event = field(default_factory=threading.Event)
    result: dict | None = None

    def accepts_text(self) -> bool:
        return self.sent and (self.kind in ("done", "permission") or self.first_open_question() is not None)

    def first_open_question(self) -> int | None:
        for qi, q in enumerate(self.questions):
            if q.get("question") not in self.answers:
                return qi
        return None


class Bridge:
    def __init__(self, app: Application, settings: Settings):
        self.app = app
        self.user_id = settings.user_id
        self.t = Messages(settings.language, settings.owner)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.lock = threading.RLock()
        self.items: dict[str, Item] = {}
        self.titles: dict[str, str] = {}
        state = self._load_state()
        self.mode: str = state.get("mode", HOME)
        self.topics: dict[str, dict] = state.get("topics", {})  # session id -> {"thread": id, "name": name}
        self._topics_enabled: bool = False
        self._topics_checked: float = 0.0

    # ---- persistence (switch + topics)

    def _load_state(self) -> dict:
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_state(self) -> None:
        with self.lock:
            data = {"mode": self.mode, "topics": self.topics}
        STATE_FILE.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self._save_state()
        log.info("Switch: %s", "away" if mode == AWAY else "home")

    def mode_text(self) -> str:
        return self.t("mode_away") if self.mode == AWAY else self.t("mode_home")

    def kind_label(self, kind: str) -> str:
        return self.t(f"kind_{kind}")

    # ---- across threads

    def spawn(self, coro) -> None:
        """Start a Telegram action in the background (callable from any thread)."""
        if self.loop:
            asyncio.run_coroutine_threadsafe(coro, self.loop)

    def call(self, coro, timeout: float = 30) -> None:
        """Run a Telegram action and wait for it (only from the counter thread, never from Telegram handlers)."""
        if not self.loop:
            return
        try:
            asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=timeout)
        except Exception as exc:
            log.warning("Telegram action failed: %s: %s", type(exc).__name__, exc)

    # ---- chat titles

    def title_for(self, data: dict, entries: list[dict] | None = None) -> str:
        sid = data.get("session_id", "")
        title = data.get("session_title")
        if not title and sid not in self.titles:
            title = find_title(entries if entries is not None else transcript_tail(data.get("transcript_path")))
        if title:
            self.titles[sid] = title
        return self.titles.get(sid) or pathlib.Path(data.get("cwd") or "Claude").name or "Claude"

    # ---- the counter: hook events arrive here

    def handle_hook(self, data: dict) -> dict:
        event = data.get("hook_event_name", "")
        sid = data.get("session_id", "")
        wait_s = float(data.get("_wait_s") or 0)
        t = self.t

        if event in ("UserPromptSubmit", "SessionEnd"):
            if data.get("session_title"):
                self.titles[sid] = data["session_title"]
            self.clear_session(sid, t("note_continued_pc"))
            return {"action": "none"}

        if event in ("PostToolUse", "PostToolUseFailure"):
            self.clear_matching(sid, data.get("tool_name", ""), data.get("tool_input") or {})
            return {"action": "none"}

        if event == "StopFailure":
            if self.mode == AWAY:
                text = t("failure", title=self.title_for(data),
                         text=trim(data.get("last_assistant_message") or data.get("error") or "", 600))
                self.call(self.send_plain(text, thread=self.topics.get(sid, {}).get("thread")))
            return {"action": "none"}

        if event == "Stop":
            self.clear_session(sid, t("note_continued_pc"))
            entries = transcript_tail(data.get("transcript_path"))
            title = self.title_for(data, entries)
            step = find_next_step(entries) or {}
            choices = []
            for action in step.get("actions") or []:
                name = action.get("action")
                label = t(f"act_{name}") if name in APP_ACTIONS else action.get("label")
                if label:
                    choices.append(label)
            item = Item(
                id=secrets.token_hex(3), kind="done", session_id=sid, title=title,
                summary=data.get("last_assistant_message") or step.get("recap") or "",
                ask=step.get("ask") or "", choices=choices,
            )
        elif event == "PermissionRequest":
            title = self.title_for(data)
            tool_name = data.get("tool_name", "")
            tool_input = data.get("tool_input") or {}
            kind = "question" if tool_name == "AskUserQuestion" else "permission"
            item = Item(
                id=secrets.token_hex(3), kind=kind, session_id=sid, title=title,
                tool_name=tool_name, tool_input=tool_input,
                questions=(tool_input.get("questions") or []) if kind == "question" else [],
            )
        else:
            return {"action": "none"}

        return self.add_and_wait(item, wait_s)

    def add_and_wait(self, item: Item, wait_s: float) -> dict:
        with self.lock:
            self.items[item.id] = item
        log.info("Waiting: %s from '%s' (id %s, switch %s)", item.kind, item.title, item.id, self.mode)
        if self.mode == AWAY:
            self.call(self.send_item(item))
        item.finished.wait(timeout=max(0.0, wait_s))
        with self.lock:
            leftover = self.items.pop(item.id, None)
        if leftover is not None:  # nobody answered in time
            self.spawn(self.close_messages(item, self.t("note_expired")))
            return {"action": "none"}
        return item.result or {"action": "none"}

    def resolve(self, item: Item, result: dict, note: str | None) -> bool:
        with self.lock:
            if self.items.pop(item.id, None) is None:
                return False
        item.result = result
        item.finished.set()
        log.info("Handled: %s from '%s' -> %s", item.kind, item.title, result.get("action"))
        if note:
            self.spawn(self.close_messages(item, note))
        return True

    def clear_session(self, sid: str, note: str) -> None:
        with self.lock:
            found = [i for i in self.items.values() if i.session_id == sid]
        for item in found:
            self.resolve(item, {"action": "none"}, note)

    def clear_matching(self, sid: str, tool_name: str, tool_input: dict) -> None:
        """A tool has finished: its question/permission was therefore already answered (e.g. on the computer)."""

        def same(item: Item) -> bool:
            if item.tool_name != tool_name:
                return False
            if tool_name == "AskUserQuestion":  # after answering, 'answers' is added: compare the questions only
                return item.tool_input.get("questions") == tool_input.get("questions")
            return item.tool_input == tool_input

        with self.lock:
            found = [
                i for i in self.items.values()
                if i.session_id == sid and i.kind in ("permission", "question") and same(i)
            ]
        for item in found:
            self.resolve(item, {"action": "none"}, self.t("note_answered_pc"))

    # ---- Telegram: topics

    async def topics_enabled(self, force: bool = False) -> bool:
        """Are topics enabled for the bot? (re-checked at most every 2 minutes, unless forced)"""
        if force or time.time() - self._topics_checked > 120:
            try:
                me = await self.app.bot.get_me()
                enabled = bool(getattr(me, "has_topics_enabled", None) or me.api_kwargs.get("has_topics_enabled"))
                if enabled != self._topics_enabled:
                    log.info("Topics for the bot: %s", "on" if enabled else "off")
                self._topics_enabled = enabled
                self._topics_checked = time.time()
            except Exception as exc:
                log.warning("Could not check whether topics are enabled: %s", type(exc).__name__)
        return self._topics_enabled

    async def thread_for(self, item: Item, fresh: bool = False) -> int | None:
        if not await self.topics_enabled():
            return None
        name = trim(item.title, 120)
        with self.lock:
            known = None if fresh else self.topics.get(item.session_id)
        if known:
            if known.get("name") != name:
                try:
                    await self.app.bot.edit_forum_topic(self.user_id, known["thread"], name=name)
                    known["name"] = name
                    self._save_state()
                except Exception:
                    pass
            return known["thread"]
        try:
            topic = await self.app.bot.create_forum_topic(self.user_id, name=name)
        except Exception as exc:
            log.warning("Could not create a topic for '%s': %s", item.title, exc)
            return None
        with self.lock:
            self.topics[item.session_id] = {"thread": topic.message_thread_id, "name": name}
        self._save_state()
        log.info("New topic for '%s'", item.title)
        return topic.message_thread_id

    def session_for_thread(self, thread_id: int) -> str | None:
        with self.lock:
            for sid, info in self.topics.items():
                if info.get("thread") == thread_id:
                    return sid
        return None

    # ---- Telegram: sending

    async def send_plain(self, text: str, reply_to: int | None = None, thread: int | None = None) -> None:
        await self.app.bot.send_message(
            self.user_id, text, link_preview_options=NO_PREVIEW, message_thread_id=thread,
            reply_parameters=ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None,
        )

    async def _send(self, item: Item, markdown: str, keyboard=None, question_index: int | None = None) -> None:
        """Send formatted, in the chat's topic. Fallbacks: without formatting / with a new topic."""
        item.thread_id = await self.thread_for(item)
        text, mode = fmt.to_telegram(markdown), ParseMode.MARKDOWN_V2
        msg = None
        for attempt in range(3):
            try:
                msg = await self.app.bot.send_message(
                    self.user_id, text, parse_mode=mode, reply_markup=keyboard,
                    link_preview_options=NO_PREVIEW, message_thread_id=item.thread_id,
                )
                break
            except BadRequest as exc:
                error = str(exc).lower()
                if "thread" in error and item.thread_id is not None and attempt == 0:
                    log.info("Topic no longer exists, creating a new one: %s", exc)
                    item.thread_id = await self.thread_for(item, fresh=True)
                elif mode is not None:
                    log.warning("Telegram rejected the formatting (%s), sending without it", exc)
                    text, mode = fmt.shorten(fmt.to_plain(markdown), 3900, self.t("shortened")), None
                else:
                    raise
        if msg is None:
            return
        with self.lock:
            item.texts[msg.message_id] = (text, mode)
            if question_index is not None:
                item.question_msgs[msg.message_id] = question_index

    async def send_item(self, item: Item) -> None:
        t = self.t
        head = f"💬 {item.title}"
        if item.kind == "permission":
            markdown = f"{t('perm_head')}\n{head}\n\n{describe_tool(t, item.tool_name, item.tool_input)}\n\n{t('perm_foot')}"
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(t("btn_allow"), callback_data=f"a:{item.id}"),
                InlineKeyboardButton(t("btn_deny"), callback_data=f"d:{item.id}"),
            ]])
            await self._send(item, markdown, keyboard)
        elif item.kind == "question":
            for qi, q in enumerate(item.questions):
                options = q.get("options") or []
                lines = [f"{t('question_head')}\n{head}\n", q.get("question", ""), ""]
                for opt in options:
                    if opt.get("description"):
                        lines.append(f"- **{opt.get('label')}**: {opt.get('description')}")
                lines.append("\n" + (t("question_foot_multi") if q.get("multiSelect") else t("question_foot")))
                rows = [[InlineKeyboardButton(trim(o.get("label", "?"), 60), callback_data=f"o:{item.id}:{qi}:{oi}")]
                        for oi, o in enumerate(options)]
                if q.get("multiSelect"):
                    rows.append([InlineKeyboardButton(t("btn_send"), callback_data=f"s:{item.id}:{qi}")])
                await self._send(item, "\n".join(lines), InlineKeyboardMarkup(rows) if rows else None, qi)
        else:  # done
            parts = [f"{t('done_head')}\n{head}", fmt.shorten(item.summary, SUMMARY_CHARS, t("shortened"))]
            if item.ask:
                parts.append(f"❓ **{item.ask}**")
            parts.append(t("done_foot_buttons") if item.choices else t("done_foot"))
            keyboard = None
            if item.choices:
                keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton(trim(label, 60), callback_data=f"r:{item.id}:{n}")]
                     for n, label in enumerate(item.choices)]
                )
            await self._send(item, "\n\n".join(parts), keyboard)
        with self.lock:
            item.sent = True
            item.last_ping = time.time()

    async def close_messages(self, item: Item, note: str, only: list[int] | None = None) -> None:
        with self.lock:
            targets = [(mid, txt) for mid, txt in item.texts.items() if only is None or mid in only]
        for mid, (text, mode) in targets:
            extra = fmt.escape(note) if mode else note
            try:
                await self.app.bot.edit_message_text(
                    f"{text}\n\n{extra}", chat_id=self.user_id, message_id=mid,
                    parse_mode=mode, link_preview_options=NO_PREVIEW,
                )
            except Exception:
                pass

    # ---- handling answers

    def set_answer(self, item: Item, qi: int, answer: str) -> None:
        question = item.questions[qi].get("question", "")
        with self.lock:
            item.answers[question] = answer
            msg_ids = [mid for mid, idx in item.question_msgs.items() if idx == qi]
            all_done = item.first_open_question() is None
        self.spawn(self.close_messages(item, self.t("note_answer", answer=trim(answer, 200)), only=msg_ids))
        if all_done:
            self.resolve(item, {"action": "answers", "answers": dict(item.answers)}, None)

    def find_by_message(self, message_id: int) -> tuple[Item | None, int | None]:
        with self.lock:
            for item in self.items.values():
                if message_id in item.texts:
                    return item, item.question_msgs.get(message_id)
        return None, None

    def pending_sorted(self) -> list[Item]:
        with self.lock:
            return sorted(self.items.values(), key=lambda i: i.created)

    # ---- reminders

    def reminder_loop(self) -> None:
        while True:
            time.sleep(60)
            if self.mode != AWAY:
                continue
            now = time.time()
            for item in self.pending_sorted():
                if item.sent and item.reminders < MAX_REMINDERS and now - item.last_ping >= REMINDER_AFTER_S:
                    item.reminders += 1
                    item.last_ping = now
                    first_msg = min(item.texts) if item.texts else None
                    text = self.t("reminder", title=item.title, kind=self.kind_label(item.kind),
                                  age=age_text(self.t, now - item.created))
                    self.spawn(self.send_plain(text, reply_to=first_msg, thread=item.thread_id))


# --------------------------------------------------------------------------- the local counter (HTTP)


def make_handler(bridge: Bridge, secret: str):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 (name required by http.server)
            if self.path != "/hook":
                self.send_error(404)
                return
            if not hmac.compare_digest(self.headers.get("X-Bridge-Secret", ""), secret):
                log.warning("Counter: request with wrong secret refused")
                self.send_error(403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                result = bridge.handle_hook(data)
                if result.get("action") == "message":  # what Claude sees when woken up
                    result["text"] = bridge.t("to_claude_wake", text=result.get("text", ""))
            except Exception:
                log.exception("Counter: error while handling a request")
                result = {"action": "none"}
            body = json.dumps(result).encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                pass  # the hook has already stopped

        def log_message(self, *args):  # quiet: we log ourselves
            pass

    return Handler


# --------------------------------------------------------------------------- Telegram commands


def build_app(settings: Settings, server: ThreadingHTTPServer) -> tuple[Application, Bridge]:
    async def post_init(app: Application) -> None:
        bridge.loop = asyncio.get_running_loop()
        threading.Thread(target=server.serve_forever, name="counter", daemon=True).start()
        threading.Thread(target=bridge.reminder_loop, name="reminders", daemon=True).start()
        me = await app.bot.get_me()
        topics = await bridge.topics_enabled()
        log.info("Connected to Telegram as @%s, counter on 127.0.0.1:%s, topics %s",
                 me.username, server.server_address[1], "on" if topics else "off")
        try:
            await bridge.send_plain(bridge.t("started", mode=bridge.mode_text()))
        except Exception as exc:
            log.warning("Could not send the start message (%s). Press Start in your bot chat.", type(exc).__name__)

    app = Application.builder().token(settings.token).post_init(post_init).build()
    bridge = Bridge(app, settings)
    t = bridge.t
    only_owner = filters.User(user_id=settings.user_id) & filters.ChatType.PRIVATE

    async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(t("help", mode=bridge.mode_text()))

    async def cmd_away(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        bridge.set_mode(AWAY)
        waiting = [i for i in bridge.pending_sorted() if not i.sent]
        if waiting:
            await update.effective_message.reply_text(t("away_waiting", count=len(waiting)))
            for item in waiting:
                await bridge.send_item(item)
        else:
            await update.effective_message.reply_text(t("away_nothing"))

    async def cmd_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        bridge.set_mode(HOME)
        await update.effective_message.reply_text(t("home"))

    async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        items = bridge.pending_sorted()
        topics = await bridge.topics_enabled(force=True)
        lines = [t("status_switch", mode=bridge.mode_text()),
                 t("status_topics", state=t("on") if topics else t("off")), ""]
        if not items:
            lines.append(t("status_nothing"))
        else:
            now = time.time()
            for n, item in enumerate(items, 1):
                lines.append(t("status_line", n=n, title=item.title, kind=bridge.kind_label(item.kind),
                               age=age_text(t, now - item.created)))
            if bridge.mode == HOME:
                lines.append(t("status_hint_away"))
        await update.effective_message.reply_text("\n".join(lines))

    async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.from_user or query.from_user.id != settings.user_id:
            if query:
                await query.answer()
            return
        parts = (query.data or "").split(":")
        with bridge.lock:
            item = bridge.items.get(parts[1]) if len(parts) > 1 else None
        if item is None:
            await query.answer(t("already_handled"))
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            return
        action = parts[0]
        if action == "a":
            bridge.resolve(item, {"action": "allow"}, t("note_allowed"))
        elif action == "d":
            bridge.resolve(item, {"action": "deny", "message": t("to_claude_denied")}, t("note_denied"))
        elif action == "r":  # button under the "done" message
            label = item.choices[int(parts[2])]
            bridge.resolve(item, {"action": "message", "text": label}, t("note_chosen", label=label))
        elif action in ("o", "s"):
            qi = int(parts[2])
            q = item.questions[qi]
            options = q.get("options") or []
            if action == "o" and not q.get("multiSelect"):
                bridge.set_answer(item, qi, options[int(parts[3])].get("label", ""))
            elif action == "o":  # multi-select: toggle
                label = options[int(parts[3])].get("label", "")
                chosen = item.selected.setdefault(qi, set())
                chosen.symmetric_difference_update({label})
                rows = [[InlineKeyboardButton(("☑️ " if o.get("label") in chosen else "") + trim(o.get("label", "?"), 56),
                                              callback_data=f"o:{item.id}:{qi}:{oi}")] for oi, o in enumerate(options)]
                rows.append([InlineKeyboardButton(t("btn_send"), callback_data=f"s:{item.id}:{qi}")])
                await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(rows))
            else:  # send
                chosen = item.selected.get(qi, set())
                if not chosen:
                    await query.answer(t("pick_one"))
                    return
                bridge.set_answer(item, qi, ", ".join(o.get("label") for o in options if o.get("label") in chosen))
        await query.answer()

    async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        text = msg.text or ""
        thread_sid = bridge.session_for_thread(msg.message_thread_id) if msg.is_topic_message else None
        item, qi = (None, None)

        # 1. Explicit reply to a message (swipe / Reply)?
        reply = msg.reply_to_message
        if reply and not reply.forum_topic_created:
            item, qi = bridge.find_by_message(reply.message_id)

        # 2. Otherwise: what is waiting in this topic (or, without topics, overall)?
        if item is None:
            candidates = [i for i in bridge.pending_sorted() if i.accepts_text()
                          and (thread_sid is None or i.session_id == thread_sid)]
            if not candidates:
                await msg.reply_text(t("nothing_waiting_here") if thread_sid else t("nothing_waiting"))
                return
            if len(candidates) > 1 and thread_sid is None:
                await msg.reply_text(t("several_waiting"))
                return
            item = candidates[-1] if thread_sid else candidates[0]

        if item.kind == "question":
            qi = qi if qi is not None else item.first_open_question()
            if qi is None:
                await msg.reply_text(t("question_answered"))
                return
            bridge.set_answer(item, qi, text)
        elif item.kind == "done":
            bridge.resolve(item, {"action": "message", "text": text}, t("note_sent"))
        else:  # permission + text = deny with an explanation
            bridge.resolve(item, {"action": "deny", "message": t("to_claude_denied_text", text=text)},
                           t("note_denied_text"))
        await msg.reply_text(t("forwarded"))

    async def ignore_stranger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user and user.is_bot:
            return  # service messages from the bot itself (e.g. "topic created"): not a stranger
        log.warning("Ignored a message from an unknown user: id=%s", user.id if user else "?")

    app.add_handler(CommandHandler(["start", "help"], cmd_help, filters=only_owner))
    app.add_handler(CommandHandler(["away", "weg"], cmd_away, filters=only_owner))
    app.add_handler(CommandHandler(["home", "thuis"], cmd_home, filters=only_owner))
    app.add_handler(CommandHandler("status", cmd_status, filters=only_owner))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(only_owner & filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(~only_owner, ignore_stranger))
    return app, bridge


def main() -> None:
    setup_logging()
    settings = load_settings()
    conf = load_bridge_conf()

    # Open the counter first: if that fails, a bridge is most likely already running.
    try:
        server = ThreadingHTTPServer(("127.0.0.1", int(conf["port"])), BaseHTTPRequestHandler)
    except OSError:
        sys.exit(f"Port {conf['port']} is in use. Is the bridge already running? (see {LOG_FILE})")
    server.daemon_threads = True

    app, bridge = build_app(settings, server)
    server.RequestHandlerClass = make_handler(bridge, conf["secret"])

    log.info("Bridge starting (log: %s)", LOG_FILE)
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
