"""Schickt Post-Entwürfe zur Freigabe an Telegram, bevor irgendetwas online geht.

Ablauf:
  1. vorschlagen: rendert den nächsten Kandidaten, schickt ihn mit zwei
     Tasten (Freigeben / Ablehnen) an den Nutzer.
  2. Der Nutzer tippt auf eine Taste. Telegram merkt sich das als
     "callback_query" – abgeholt wird es aktiv per hole_antworten().
  3. telegram-abfragen wertet das aus: bei Freigeben wird sofort
     veröffentlicht, bei Ablehnen ein neuer Kandidat gerendert und erneut
     geschickt (die abgelehnte ID kommt auf die Ausschlussliste).

Bewusst kein Webhook, sondern kurzes Poll-Intervall per Cron: kein eigener
Server nötig, läuft im selben kostenlosen GitHub-Actions-Rahmen wie der
Rest der Automatik.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import requests

from config import (TELEGRAM_BOT_TOKEN_SOCIAL, TELEGRAM_BOT_TOKEN_ADS,
                    TELEGRAM_CHAT_ID, TELEGRAM_CHAT_ID_ADS)

log = logging.getLogger(__name__)

TIMEOUT = 30
# Telegram-Bildunterschriften sind auf 1024 Zeichen begrenzt (Instagram-
# Captions dürfen bis 2200) - deshalb geht der volle Text als zweite Nachricht.
MAX_BILDUNTERSCHRIFT = 1000


class TelegramFehler(Exception):
    pass


def aktiv() -> bool:
    return bool(TELEGRAM_BOT_TOKEN_SOCIAL and TELEGRAM_CHAT_ID)


def aktiv_ads() -> bool:
    return bool(TELEGRAM_BOT_TOKEN_ADS and TELEGRAM_CHAT_ID_ADS)


def _basis_url(bot_token: str) -> str:
    return f"https://api.telegram.org/bot{bot_token}"


def _api(methode: str, bot_token: str = TELEGRAM_BOT_TOKEN_SOCIAL, **daten) -> dict:
    try:
        antwort = requests.post(f"{_basis_url(bot_token)}/{methode}", data=daten, timeout=TIMEOUT)
    except requests.RequestException as fehler:
        raise TelegramFehler(f"{methode}: keine Verbindung – {fehler}") from None

    inhalt = antwort.json()
    if not inhalt.get("ok"):
        raise TelegramFehler(f"{methode}: {inhalt.get('description', antwort.text)}")
    return inhalt["result"]


def _api_datei(methode: str, feld: str, pfad: Path, bot_token: str = TELEGRAM_BOT_TOKEN_SOCIAL, **daten) -> dict:
    try:
        with pfad.open("rb") as f:
            antwort = requests.post(f"{_basis_url(bot_token)}/{methode}", data=daten,
                                    files={feld: f}, timeout=TIMEOUT)
    except requests.RequestException as fehler:
        raise TelegramFehler(f"{methode}: keine Verbindung – {fehler}") from None

    inhalt = antwort.json()
    if not inhalt.get("ok"):
        raise TelegramFehler(f"{methode}: {inhalt.get('description', antwort.text)}")
    return inhalt["result"]


def _kuerzen(text: str, laenge: int = MAX_BILDUNTERSCHRIFT) -> str:
    if len(text) <= laenge:
        return text
    return text[: laenge - 1].rstrip() + "…"


@dataclass
class Vorschlag:
    nachricht_id: int
    chat_id: str


def sende_vorschlag(bild: Path, kurztext: str, volltext: str, plan_id: str,
                    versuch: int = 1) -> Vorschlag:
    """Schickt Bild + Tasten, danach den vollständigen Text als eigene Nachricht.

    plan_id steckt in den callback-Daten (z. B. "ok:t-grossformat") - so weiß
    telegram-abfragen später, welchen Kandidaten die Antwort betrifft, ohne
    eine eigene Datenbank zu brauchen.
    """
    tasten = {
        "inline_keyboard": [[
            {"text": "✅ Freigeben", "callback_data": f"ok:{plan_id}"[:64]},
            {"text": "❌ Ablehnen", "callback_data": f"nein:{plan_id}"[:64]},
        ]]
    }
    import json as _json
    ergebnis = _api_datei(
        "sendPhoto", "photo", bild,
        chat_id=TELEGRAM_CHAT_ID,
        caption=_kuerzen(kurztext, 1000),
        reply_markup=_json.dumps(tasten),
        bot_token=TELEGRAM_BOT_TOKEN_SOCIAL,
    )
    _api("sendMessage", chat_id=TELEGRAM_CHAT_ID, text=volltext,
        disable_web_page_preview=True, bot_token=TELEGRAM_BOT_TOKEN_SOCIAL)
    return Vorschlag(nachricht_id=ergebnis["message_id"], chat_id=str(ergebnis["chat"]["id"]))


def sende_text(text: str, chat_id: str | None = None, markdown: bool = False) -> None:
    """chat_id=TELEGRAM_CHAT_ID_ADS schickt automatisch über den Ads-Bot,
    sonst über den Social-Media-Bot - beide haben getrennte Tokens."""
    ziel = chat_id or TELEGRAM_CHAT_ID
    ist_ads = ziel == TELEGRAM_CHAT_ID_ADS
    bot_token = TELEGRAM_BOT_TOKEN_ADS if ist_ads else TELEGRAM_BOT_TOKEN_SOCIAL
    if not (bot_token and ziel):
        return
    zusatz = {"parse_mode": "Markdown"} if markdown else {}
    _api("sendMessage", chat_id=ziel, text=text, disable_web_page_preview=True,
        bot_token=bot_token, **zusatz)


def markiere(nachricht_id: int, zusatz: str, chat_id: str | None = None) -> None:
    """Hängt eine Statuszeile an die Bildunterschrift, damit im Chat sichtbar
    bleibt, was aus dem Vorschlag geworden ist, statt dass die Tasten einfach
    verschwinden."""
    try:
        _api("editMessageCaption", chat_id=chat_id or TELEGRAM_CHAT_ID,
            message_id=nachricht_id, caption=zusatz, bot_token=TELEGRAM_BOT_TOKEN_SOCIAL)
    except TelegramFehler as fehler:
        log.warning("Bildunterschrift konnte nicht aktualisiert werden: %s", fehler)


def markiere_text(nachricht_id: int, neuer_text: str, chat_id: str | None = None) -> None:
    """Wie markiere(), aber für reine Textnachrichten (editMessageText statt
    editMessageCaption) - für Ads-Meldungen, die kein Bild haben."""
    try:
        _api("editMessageText", chat_id=chat_id or TELEGRAM_CHAT_ID_ADS,
            message_id=nachricht_id, text=neuer_text,
            disable_web_page_preview=True, bot_token=TELEGRAM_BOT_TOKEN_ADS)
    except TelegramFehler as fehler:
        log.warning("Text konnte nicht aktualisiert werden: %s", fehler)


def sende_meldung(text: str, hash_id: str, chat_id: str | None = None) -> int:
    """Schickt eine Ads-Kanal-Meldung mit den drei Tasten Merken / Mehr dazu /
    Ignorieren. Gibt die message_id zurück (für spätere markiere_text()-
    Aufrufe, wenn der Nutzer eine Taste drückt).
    """
    import json as _json
    tasten = {
        "inline_keyboard": [[
            {"text": "📌 Merken", "callback_data": f"merken:{hash_id}"[:64]},
            {"text": "ℹ️ Mehr dazu", "callback_data": f"mehr:{hash_id}"[:64]},
            {"text": "🚫 Ignorieren", "callback_data": f"ignorieren:{hash_id}"[:64]},
        ]]
    }
    ergebnis = _api("sendMessage", chat_id=chat_id or TELEGRAM_CHAT_ID_ADS,
                    text=text, reply_markup=_json.dumps(tasten),
                    disable_web_page_preview=True, bot_token=TELEGRAM_BOT_TOKEN_ADS)
    return ergebnis["message_id"]


def beantworte_callback(callback_query_id: str, text: str = "", ads: bool = False) -> None:
    """Nimmt der Taste im Chat den Lade-Kreis - ohne das bleibt sie hängen.
    ads=True beantwortet über den Ads-Bot (für merken/mehr/ignorieren)."""
    bot_token = TELEGRAM_BOT_TOKEN_ADS if ads else TELEGRAM_BOT_TOKEN_SOCIAL
    try:
        _api("answerCallbackQuery", callback_query_id=callback_query_id, text=text,
            bot_token=bot_token)
    except TelegramFehler as fehler:
        log.warning("Callback-Antwort fehlgeschlagen: %s", fehler)


def hole_antworten(letzte_update_id: int, bot_token: str = TELEGRAM_BOT_TOKEN_SOCIAL) -> tuple[list[dict], int]:
    """Neue Tastendrücke seit letzte_update_id, für EINEN Bot.

    Gibt (Liste von {"daten": "ok:t-x", "callback_query_id": ..., "nachricht_id": ...},
    neue_letzte_update_id) zurück. Kurzes Poll (timeout=0) statt Long-Poll,
    weil das hier per Cron alle paar Minuten läuft statt dauerhaft zu laufen.
    Seit 28.08.2026 zwei getrennte Bots (Social/Ads) - getUpdates ist pro Bot-
    Token, deshalb muss diese Funktion für jeden Bot einzeln aufgerufen werden.
    """
    # Plausibilitaetspruefung des Zaehlerstands.
    #
    # Telegram fuehrt die update_id PRO BOT. Bei der Trennung in Social- und
    # Ads-Bot am 28.08.2026 wurde der Stand des alten gemeinsamen Bots
    # uebernommen (252.660.748) - der neue Social-Bot zaehlt aber viel
    # niedriger (131.777.xxx). Der Bot fragte also nach Updates ab einer
    # Nummer, die es nie geben wird, und war seitdem blind.
    #
    # Deshalb: erst ohne Offset nachsehen, was tatsaechlich anliegt. Liegt der
    # gespeicherte Stand ueber der hoechsten echten Nummer, ist er falsch und
    # wird auf die aktuelle Lage gesetzt. Bewusst NICHT auf 0 - sonst wuerden
    # alte, laengst ueberholte Tastendruecke nachtraeglich verarbeitet. Genau
    # so waere am 28.08. beinahe ein Testbeitrag veroeffentlicht worden.
    if letzte_update_id > 0:
        vorschau = _api("getUpdates", offset=0, timeout=0, limit=100,
                        allowed_updates='["callback_query","message"]',
                        bot_token=bot_token)
        if vorschau:
            hoechste = max(u["update_id"] for u in vorschau)
            if letzte_update_id > hoechste:
                log.warning(
                    "Zaehlerstand %s liegt ueber der hoechsten echten "
                    "update_id %s - wird korrigiert.", letzte_update_id, hoechste)
                letzte_update_id = hoechste - 1

    updates = _api("getUpdates", offset=letzte_update_id + 1, timeout=0,
                   allowed_updates='["callback_query","message"]', bot_token=bot_token)
    treffer = []
    neue_letzte = letzte_update_id
    for u in updates:
        neue_letzte = max(neue_letzte, u["update_id"])

        cq = u.get("callback_query")
        if cq and "data" in cq:
            treffer.append({
                "art": "taste",
                "daten": cq["data"],
                "callback_query_id": cq["id"],
                "nachricht_id": cq["message"]["message_id"],
            })
            continue

        # Getippte Befehle. Seit 29.08.2026 hört der Bot auch auf Text, damit
        # jederzeit ein neuer Vorschlag angefordert werden kann - nicht nur
        # dann, wenn gerade einer zur Freigabe offen ist.
        nachricht = u.get("message") or {}
        text = (nachricht.get("text") or "").strip()
        if not text.startswith("/"):
            continue
        # "/neu@MeinBot arg" -> befehl "neu"
        befehl = text.split()[0].lstrip("/").split("@")[0].lower()
        treffer.append({
            "art": "befehl",
            "daten": f"befehl:{befehl}",
            "befehl": befehl,
            "callback_query_id": None,
            "nachricht_id": nachricht.get("message_id"),
            "chat_id": str((nachricht.get("chat") or {}).get("id", "")),
        })
    return treffer, neue_letzte


def pruefe_zugang(ads: bool = False) -> str:
    """Für 'zugang': Botname zurückgeben oder eine TelegramFehler auslösen."""
    bot_token = TELEGRAM_BOT_TOKEN_ADS if ads else TELEGRAM_BOT_TOKEN_SOCIAL
    info = _api("getMe", bot_token=bot_token)
    return f"@{info.get('username', '?')}"
