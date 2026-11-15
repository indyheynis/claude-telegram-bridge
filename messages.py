"""All texts the bot sends, in English and Dutch.

Pick the language with BRIDGE_LANGUAGE=en|nl in ~/.claude-telegram/.env (default: en).
{owner} is replaced by BRIDGE_OWNER_NAME (default: "you"/"je").
"""
from __future__ import annotations

TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "owner_default": "the user",
        "mode_away": "🚶 away (notifications on)",
        "mode_home": "🏠 home (no notifications)",
        "started": "✅ Bridge started. Switch is set to: {mode}",
        "help": (
            "Hi {owner} 👋 I'm your Claude Code bridge.\n\n"
            "/away: notifications on. Everything that waits for you comes here right away.\n"
            "/home: notifications off (you're at your computer).\n"
            "/status: what is waiting for you right now?\n\n"
            "To answer: tap a button, or type your own reply.\n\n"
            "Switch is set to: {mode}"
        ),
        "away_waiting": "🚶 Away mode on. {count} thing(s) waiting for you, sending them now.",
        "away_nothing": "🚶 Away mode on. Nothing is waiting for you; I'll let you know when something is.",
        "home": "🏠 Home mode: no more notifications. Messages that are still open can still be answered.",
        "status_switch": "Switch: {mode}",
        "status_topics": "Topic per chat: {state}",
        "on": "on",
        "off": "off",
        "status_nothing": "Nothing is waiting for you. 🎉",
        "status_line": "{n}. '{title}' {kind} ({age})",
        "status_hint_away": "\nSend /away to get them here.",
        "kind_permission": "🔐 is waiting for permission",
        "kind_question": "❓ has a question",
        "kind_done": "✅ is done",
        "age_now": "just now",
        "age_min": "{m} min",
        "age_hour": "{h} h {m} min",
        "reminder": "⏰ Reminder: '{title}' {kind} (for {age}).",
        "failure": "⚠️ Claude stopped on an error\n💬 {title}\n\n{text}",
        "perm_head": "🔐 **Claude asks for permission**",
        "perm_foot": "_Tap a button. Or reply with text to deny with an explanation._",
        "btn_allow": "✅ Allow",
        "btn_deny": "❌ Deny",
        "btn_send": "✅ Send",
        "question_head": "❓ **Claude has a question**",
        "question_foot_multi": "_You may pick several, then tap ✅ Send. Or reply with your own text._",
        "question_foot": "_Tap a choice, or reply with your own text._",
        "done_head": "✅ **Claude is done**",
        "done_foot_buttons": "_Tap a button, or reply with your own text to let Claude continue._",
        "done_foot": "_Reply with your own text to let Claude continue._",
        "shortened": "…(shortened, read the rest in the Claude app)",
        "note_continued_pc": "✔️ Continued on the computer",
        "note_answered_pc": "✔️ Answered on the computer",
        "note_expired": "⌛ Expired",
        "note_allowed": "✔️ Allowed via Telegram",
        "note_denied": "✖️ Denied via Telegram",
        "note_denied_text": "✖️ Denied, with your explanation",
        "note_chosen": "✔️ Chosen: {label}",
        "note_answer": "✔️ Your answer: {answer}",
        "note_sent": "✔️ Your reply was sent to Claude",
        "to_claude_denied": "{owner} denied this via Telegram.",
        "to_claude_denied_text": "{owner} denied this via Telegram and wrote: {text}",
        "to_claude_wake": "Message from {owner} via Telegram: {text}",
        "already_handled": "This has already been handled.",
        "pick_one": "Pick at least one option first.",
        "nothing_waiting": "Nothing is waiting for a reply from you. Send /status for an overview.",
        "nothing_waiting_here": "Nothing in this chat is waiting for a reply from you. Send /status for an overview.",
        "several_waiting": "Several things are waiting for you. Reply to the right message: long-press it (or swipe left) and choose Reply.",
        "question_answered": "That question has already been answered.",
        "forwarded": "📨 Passed on to Claude.",
        "tool_command": "Run command:",
        "tool_write": "Write file:",
        "tool_edit": "Edit file:",
        "tool_notebook": "Edit notebook:",
        "tool_fetch": "Fetch web page:",
        "tool_read": "Read file:",
        "act_commit": "Commit",
        "act_create_pr": "Create pull request",
        "act_merge": "Merge",
        "act_fix_ci": "Fix CI",
        "act_address_comments": "Address comments",
        "act_resolve_conflicts": "Resolve conflicts",
        "act_verify": "Verify",
        "act_archive": "Archive",
        "act_new_session": "New session",
    },
    "nl": {
        "owner_default": "de gebruiker",
        "mode_away": "🚶 weg (meldingen aan)",
        "mode_home": "🏠 thuis (geen meldingen)",
        "started": "✅ Postbode opgestart. Schakelaar staat op: {mode}",
        "help": (
            "Hoi {owner} 👋 Ik ben je Claude-postbode.\n\n"
            "/weg: meldingen aan. Alles wat op je wacht komt meteen hierheen.\n"
            "/thuis: meldingen uit (je zit achter je pc).\n"
            "/status: wat wacht er nu op je?\n\n"
            "Antwoorden: tik op een knop, of typ je eigen tekst.\n\n"
            "Schakelaar staat nu op: {mode}"
        ),
        "away_waiting": "🚶 Weg-modus aan. Er wacht(en) nu {count} ding(en) op je, die stuur ik je nu.",
        "away_nothing": "🚶 Weg-modus aan. Er wacht nu niets op je; ik meld me zodra dat wel zo is.",
        "home": "🏠 Thuis-modus: je krijgt geen meldingen meer. Berichten die nog openstaan, kun je nog steeds beantwoorden.",
        "status_switch": "Schakelaar: {mode}",
        "status_topics": "Draadjes per chat: {state}",
        "on": "aan",
        "off": "uit",
        "status_nothing": "Er wacht nu niets op je. 🎉",
        "status_line": "{n}. '{title}' {kind} ({age})",
        "status_hint_away": "\nTyp /weg om ze hierheen te halen.",
        "kind_permission": "🔐 wacht op toestemming",
        "kind_question": "❓ heeft een vraag",
        "kind_done": "✅ is klaar",
        "age_now": "net",
        "age_min": "{m} min",
        "age_hour": "{h} u {m} min",
        "reminder": "⏰ Herinnering: '{title}' {kind} (al {age}).",
        "failure": "⚠️ Claude liep vast op een fout\n💬 {title}\n\n{text}",
        "perm_head": "🔐 **Claude vraagt toestemming**",
        "perm_foot": "_Tik op een knop. Of antwoord met tekst om te weigeren met uitleg._",
        "btn_allow": "✅ Toestaan",
        "btn_deny": "❌ Weigeren",
        "btn_send": "✅ Versturen",
        "question_head": "❓ **Claude heeft een vraag**",
        "question_foot_multi": "_Je mag meerdere kiezen; tik daarna op ✅ Versturen. Of antwoord met eigen tekst._",
        "question_foot": "_Tik op een keuze, of antwoord met je eigen tekst._",
        "done_head": "✅ **Claude is klaar**",
        "done_foot_buttons": "_Tik op een knop, of antwoord met je eigen tekst om Claude verder te laten gaan._",
        "done_foot": "_Antwoord met je eigen tekst om Claude verder te laten gaan._",
        "shortened": "…(ingekort, lees verder in de Claude-app)",
        "note_continued_pc": "✔️ Verder gegaan op de pc",
        "note_answered_pc": "✔️ Beantwoord op de pc",
        "note_expired": "⌛ Verlopen",
        "note_allowed": "✔️ Toegestaan via Telegram",
        "note_denied": "✖️ Geweigerd via Telegram",
        "note_denied_text": "✖️ Geweigerd, met jouw uitleg",
        "note_chosen": "✔️ Gekozen: {label}",
        "note_answer": "✔️ Je antwoord: {answer}",
        "note_sent": "✔️ Je antwoord is naar Claude gestuurd",
        "to_claude_denied": "{owner} heeft dit via Telegram geweigerd.",
        "to_claude_denied_text": "{owner} weigerde via Telegram en schreef: {text}",
        "to_claude_wake": "Bericht van {owner} via Telegram: {text}",
        "already_handled": "Dit is al afgehandeld.",
        "pick_one": "Kies eerst minstens één optie.",
        "nothing_waiting": "Er wacht nu niets op een antwoord van je. Typ /status voor een overzicht.",
        "nothing_waiting_here": "Er wacht in deze chat nu niets op een antwoord van je. Typ /status voor een overzicht.",
        "several_waiting": "Er wachten meerdere dingen op je. Antwoord op het juiste bericht: houd het ingedrukt (of swipe naar links) en kies Antwoorden.",
        "question_answered": "Die vraag is al beantwoord.",
        "forwarded": "📨 Doorgegeven aan Claude.",
        "tool_command": "Commando uitvoeren:",
        "tool_write": "Bestand schrijven:",
        "tool_edit": "Bestand aanpassen:",
        "tool_notebook": "Notebook aanpassen:",
        "tool_fetch": "Webpagina ophalen:",
        "tool_read": "Bestand lezen:",
        "act_commit": "Commit maken",
        "act_create_pr": "Pull request maken",
        "act_merge": "Mergen",
        "act_fix_ci": "CI repareren",
        "act_address_comments": "Opmerkingen verwerken",
        "act_resolve_conflicts": "Conflicten oplossen",
        "act_verify": "Controleren",
        "act_archive": "Archiveren",
        "act_new_session": "Nieuwe sessie",
    },
}


class Messages:
    def __init__(self, language: str = "en", owner: str = ""):
        self.lang = language if language in TEXTS else "en"
        self.owner = owner or TEXTS[self.lang]["owner_default"]

    def __call__(self, key: str, **kwargs) -> str:
        template = TEXTS[self.lang].get(key) or TEXTS["en"][key]
        return template.format(owner=self.owner, **kwargs)
