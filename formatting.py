"""Convert Claude's Markdown to Telegram formatting (MarkdownV2).

Uses the open-source library telegramify-markdown, version < 1 (pure Python: the newer
version ships a prebuilt native module that Windows Smart App Control may block).

Own adjustments first:
- tables become bullet lists (reads better on a narrow phone screen);
- links to local files become plain text (Telegram cannot open them);
- long text is shortened neatly at a paragraph boundary.
"""
from __future__ import annotations

import re

import telegramify_markdown
from telegram.helpers import escape_markdown

LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _tables_to_bullets(md: str) -> str:
    out: list[str] = []
    lines = md.splitlines()
    in_fence = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        is_table = (
            not in_fence
            and line.lstrip().startswith("|")
            and i + 1 < len(lines)
            and TABLE_SEPARATOR.match(lines[i + 1])
        )
        if not is_table:
            out.append(line)
            i += 1
            continue
        i += 2  # skip the header row and the separator line
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            cells = [c for c in _cells(lines[i]) if c]
            if cells:
                first, rest = cells[0], cells[1:]
                out.append(f"- **{first}**" + (": " + " · ".join(rest) if rest else ""))
            i += 1
    return "\n".join(out)


def _local_links_to_text(md: str) -> str:
    def repl(m: re.Match) -> str:
        label, target = m.group(1), m.group(2)
        return m.group(0) if target.startswith(("http://", "https://")) else label

    return LINK.sub(repl, md)


def shorten(md: str, limit: int, suffix: str = "…") -> str:
    md = (md or "").strip()
    if len(md) <= limit:
        return md
    cut = md.rfind("\n\n", 0, limit)
    if cut < limit // 2:
        cut = limit
    return md[:cut].rstrip() + "\n\n" + suffix


def to_telegram(md: str) -> str:
    """Claude's Markdown -> MarkdownV2 text for Telegram."""
    return telegramify_markdown.markdownify(_local_links_to_text(_tables_to_bullets(md)))


def to_plain(md: str) -> str:
    """Fallback if Telegram rejects the formatting: without formatting characters."""
    text = _local_links_to_text(_tables_to_bullets(md))
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.MULTILINE)
    return text.replace("```", "")


def escape(text: str) -> str:
    """Put plain text safely into a MarkdownV2 message."""
    return escape_markdown(text, version=2)
