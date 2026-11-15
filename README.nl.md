# Claude Telegram Bridge

[English](README.md) · **Nederlands**

Krijg een Telegram-bericht als **Claude Code** je nodig heeft, en antwoord vanaf je telefoon.
Claude gaat dan verder in dezelfde chat, op je eigen pc.

Gemaakt voor **Claude Desktop (Code-tab) op Windows**, gebouwd op de officiële
[Claude Code-hooks](https://code.claude.com/docs/en/hooks). Geen tweede AI, geen betaalde diensten,
geen server in de cloud: een klein Python-programma op je eigen pc en een Telegram-bot.

---

## Wat je ermee kunt

| In Telegram | Wat er gebeurt |
|---|---|
| `/weg` (of `/away`) | Meldingen aan. Alles wat op je wacht komt meteen naar je telefoon, ook wat al wachtte. |
| `/thuis` (of `/home`) | Meldingen uit. Gebruik dit als je achter je pc zit. |
| `/status` | Overzicht: welke Claude-chats wachten op je, en staat de schakelaar op thuis of weg. |
| Knop tikken | Antwoord op een vraag, toestemming geven/weigeren, of de keuze onder "Claude is klaar". |
| Zelf typen | Je eigen antwoord. In een draadje gaat het altijd naar die ene Claude-chat. |

Je krijgt een bericht als Claude:

- **toestemming vraagt** (✅ Toestaan / ❌ Weigeren, of typ een uitleg om te weigeren);
- **een vraag stelt** (de keuzes als knoppen, of typ je eigen antwoord);
- **klaar is** (samenvatting met opmaak + de keuzevraag uit de app als knoppen);
- **vastloopt op een fout**.

Wacht iets 30 minuten op je, dan krijg je een herinnering (maximaal 3 keer).
Elke Claude-chat krijgt een **eigen draadje** in je botchat, met de naam van de chat erboven.
Antwoord je op de pc, dan wordt het Telegram-bericht bijgewerkt ("✔️ Beantwoord op de pc").

## Hoe het werkt (in gewone woorden)

```
Claude (op je pc)  <->  haakje (hook.py)  <->  postbode (bridge.py)  <->  Telegram  <->  jij (telefoon)
```

1. **Het haakje** (`hook.py`) wordt door Claude Code zelf gestart op vaste momenten (officiële hooks:
   `PermissionRequest`, `Stop`, `StopFailure`, `UserPromptSubmit`, `PostToolUse`, `PostToolUseFailure`, `SessionEnd`).
2. **De postbode** (`bridge.py`) draait altijd op de achtergrond. Hij heeft een "loket" dat alleen op je eigen
   pc bereikbaar is (`127.0.0.1:8765`, met geheim wachtwoord) en praat met Telegram.
3. Het haakje geeft het moment door aan het loket en wacht (maximaal 8 uur) op jouw antwoord.
   Wie het eerst antwoordt, pc of Telegram, wint.
4. Na "klaar" luistert de chat nog 8 uur: stuur je iets, dan wordt Claude wakker en gaat verder.

**Veiligheidsnet:** draait de postbode niet, dan doen de haakjes niets en werkt Claude precies zoals zonder koppeling.

## Installeren van nul (bijv. op een nieuwe pc)

Nodig: Windows, Claude Desktop met Claude Code, [uv](https://docs.astral.sh/uv/), Telegram.

1. **Bot maken:** stuur `/newbot` naar **@BotFather**. Bewaar de sleutel (deel hem nooit in een chat).
2. **Je nummer:** stuur iets naar **@userinfobot**, die geeft je **Id**.
3. **Draadjes aanzetten (optioneel):** BotFather → Open (app) → je bot → **Threaded Mode** aan.
4. **Instellingen:** kopieer [`.env.example`](.env.example) naar `%USERPROFILE%\.claude-telegram\.env` en vul in
   (voor Nederlands: `BRIDGE_LANGUAGE=nl`).
5. **Code klaarzetten:** in deze map `uv sync`
6. **Postbode automatisch laten starten:** `powershell -ExecutionPolicy Bypass -File autostart.ps1`
   en daarna één keer starten: `Start-ScheduledTask -TaskName "Claude Telegram Bridge"`
7. **Haakjes installeren:** `uv run python install.py`
8. **Testen:** druk op **Start** bij je bot, stuur `/status`, dan `/weg`, en laat Claude iets vragen.

## Instellingen en bestanden

In `%USERPROFILE%\.claude-telegram\` (nooit in git):

| Bestand | Wat |
|---|---|
| `.env` | Bot-sleutel, je Telegram-nummer, taal (`en`/`nl`) en je naam |
| `bridge.json` | Poort en geheim wachtwoord van het loket (maakt de postbode zelf) |
| `state.json` | Stand van de schakelaar + welk draadje bij welke Claude-chat hoort |
| `logs\bridge.log` | Logboek (de bot-sleutel komt hier bewust niet in) |

## Werkt het niet?

| Wat je ziet | Wat je doet |
|---|---|
| Bot antwoordt niet op `/status` | Postbode draait niet. Wacht 3 minuten (de waakhond start hem), of: `Start-ScheduledTask -TaskName "Claude Telegram Bridge"`. Kijk in `logs\bridge.log`. |
| Geen meldingen | Staat de schakelaar op `/weg`? Check met `/status`. |
| "Port 8765 is in use" in het logboek | Er draait al een postbode. Niets aan de hand. |
| "Dit is al afgehandeld" bij een knop | Het was al beantwoord (op de pc) of verlopen. |
| Bericht komt zonder opmaak | Telegram weigerde de opmaak; de postbode stuurde het daarom als gewone tekst. |
| Bot-sleutel per ongeluk gedeeld | `/revoke` bij @BotFather, nieuwe sleutel in `.env`, postbode herstarten. |

**Postbode herstarten** (bijv. na een code-aanpassing), in PowerShell:

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'bridge\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-ScheduledTask -TaskName "Claude Telegram Bridge"
```

## Weer weghalen

```powershell
uv run python install.py --uninstall
powershell -ExecutionPolicy Bypass -File autostart.ps1 -Uninstall
```

Daarna werkt Claude weer precies zoals voor de koppeling. Reservekopieën van je Claude-instellingen
staan naast `%USERPROFILE%\.claude\settings.json` (`settings.json.backup-...`).

## Grenzen (eerlijk)

- De pc moet **aan, wakker en ingelogd** zijn. Zet slaapstand uit als hij aan de stroom zit; laptopklep open.
  Na een herstart door Windows Update wacht hij op het inlogscherm.
- Chats in de Claude-app lopen na een herstart van de pc niet vanzelf door.
- Een vrij Telegram-bericht na "klaar" ziet Claude als "bericht via de bot", niet als iets wat je zelf in de chat
  typte. Gewone opdrachten doet Claude gewoon; voor riskante dingen vraagt het eerst toestemming (die geef je met
  een knop). Een antwoord op een **vraag** van Claude telt wel als jouw echte antwoord.
- Zolang er een vraag wacht, telt elke getypte tekst in dat draadje als antwoord op die vraag.
- Berichten gaan via Telegram's servers: zet er geen wachtwoorden of geheimen in.
- Wie je Telegram-account heeft, kan Claude aansturen: zet **tweestapsverificatie** aan in Telegram.
- Voorlopig alleen Windows.

## Licentie

[MIT](LICENSE) © 2026 Indy Heynis
