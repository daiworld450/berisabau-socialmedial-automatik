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

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)

TIMEOUT = 30
# Telegram-Bildunterschriften sind auf 1024 Zeichen begrenzt (Instagram-
# Captions dürfen bis 2200) - deshalb geht der volle Text als zweite Nachricht.
MAX_BILDUNTERSCHRIFT = 1000


class TelegramFehler(Exception):
    pass


def aktiv() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def _basis_url() -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def _api(methode: str, **daten) -> dict:
    try:
        antwort = requests.post(f"{_basis_url()}/{methode}", data=daten, timeout=TIMEOUT)
    except requests.RequestException as fehler:
        raise TelegramFehler(f"{methode}: keine Verbindung – {fehler}") from None

    inhalt = antwort.json()
    if not inhalt.get("ok"):
        raise TelegramFehler(f"{methode}: {inhalt.get('description', antwort.text)}")
    return inhalt["result"]


def _api_datei(methode: str, feld: str, pfad: Path, **daten) -> dict:
    try:
        with pfad.open("rb") as f:
            antwort = requests.post(f"{_basis_url()}/{methode}", data=daten,
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
    )
    _api("sendMessage", chat_id=TELEGRAM_CHAT_ID, text=volltext,
        disable_web_page_preview=True)
    return Vorschlag(nachricht_id=ergebnis["message_id"], chat_id=str(ergebnis["chat"]["id"]))


def sende_text(text: str) -> None:
    if not aktiv():
        return
    _api("sendMessage", chat_id=TELEGRAM_CHAT_ID, text=text, disable_web_page_preview=True)


def markiere(nachricht_id: int, zusatz: str) -> None:
    """Hängt eine Statuszeile an die Bildunterschrift, damit im Chat sichtbar
    bleibt, was aus dem Vorschlag geworden ist, statt dass die Tasten einfach
    verschwinden."""
    try:
        _api("editMessageCaption", chat_id=TELEGRAM_CHAT_ID,
            message_id=nachricht_id, caption=zusatz)
    except TelegramFehler as fehler:
        log.warning("Bildunterschrift konnte nicht aktualisiert werden: %s", fehler)


def beantworte_callback(callback_query_id: str, text: str = "") -> None:
    """Nimmt der Taste im Chat den Lade-Kreis - ohne das bleibt sie hängen."""
    try:
        _api("answerCallbackQuery", callback_query_id=callback_query_id, text=text)
    except TelegramFehler as fehler:
        log.warning("Callback-Antwort fehlgeschlagen: %s", fehler)


def hole_antworten(letzte_update_id: int) -> tuple[list[dict], int]:
    """Neue Tastendrücke seit letzte_update_id.

    Gibt (Liste von {"daten": "ok:t-x", "callback_query_id": ..., "nachricht_id": ...},
    neue_letzte_update_id) zurück. Kurzes Poll (timeout=0) statt Long-Poll,
    weil das hier per Cron alle paar Minuten läuft statt dauerhaft zu laufen.
    """
    updates = _api("getUpdates", offset=letzte_update_id + 1, timeout=0,
                   allowed_updates='["callback_query"]')
    treffer = []
    neue_letzte = letzte_update_id
    for u in updates:
        neue_letzte = max(neue_letzte, u["update_id"])
        cq = u.get("callback_query")
        if not cq or "data" not in cq:
            continue
        treffer.append({
            "daten": cq["data"],
            "callback_query_id": cq["id"],
            "nachricht_id": cq["message"]["message_id"],
        })
    return treffer, neue_letzte


def pruefe_zugang() -> str:
    """Für 'zugang': Botname zurückgeben oder eine TelegramFehler auslösen."""
    info = _api("getMe")
    return f"@{info.get('username', '?')}"
