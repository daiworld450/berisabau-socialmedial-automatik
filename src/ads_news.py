"""Täglicher Google-Ads-News-Check: Quellen abrufen, filtern, im festen
Format an den Kanal schicken.

Ablauf:
  1. Rohtext aller offiziellen Quellen abrufen (kein Aggregator, keine
     Zweitverwertung - siehe QUELLEN_SEITEN/ENTWICKLER_BLOG_FEED unten).
  2. Claude bekommt den Rohtext + den Relevanzfilter + bereits gemeldete und
     vom Nutzer ignorierte Themen und liefert eine Liste neuer, relevanter
     Meldungen im festen Format zurück (oder eine leere Liste). Die
     inhaltliche Filterentscheidung liegt bewusst bei der KI, nicht bei
     Stichwortlisten - "betrifft Suchkampagnen" lässt sich nicht zuverlässig
     per Keyword-Matching erkennen.
  3. Jede Meldung wird per URL-Hash gegen Doppelmeldung geprüft, formatiert,
     mit den drei Tasten (Merken/Mehr dazu/Ignorieren) verschickt und in
     ads_verlauf.json vermerkt.
  4. Ist nichts Relevantes dabei und die letzte Kanal-Nachricht liegt mehr
     als STILLE_SCHWELLE_TAGE zurück, kommt eine einzelne Lebenszeichen-
     Zeile statt täglichem Rauschen um seiner selbst willen.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from xml.etree import ElementTree as ET

import requests

import ads_verlauf
import telegram_bot
from config import ANTHROPIC_API_KEY, TELEGRAM_CHAT_ID_ADS

log = logging.getLogger(__name__)

TIMEOUT = 30
ANTHROPIC_MODELL = "claude-sonnet-5"
STILLE_SCHWELLE_TAGE = 3
# Etwas Überlappung zum Vortag, damit bei einem verpassten/fehlgeschlagenen
# Lauf nichts durchrutscht - schon gemeldete URLs werden ohnehin per Hash
# aussortiert, doppeltes Prüfen kostet nur unwesentlich mehr.
PRUEFZEITRAUM_TAGE = 4

# Nur Originalquellen, kein Aggregator, kein SEO-Blog.
QUELLEN_SEITEN = [
    ("Google Ads API Release Notes",
     "https://developers.google.com/google-ads/api/docs/release-notes"),
    ("Google Ads API Feature Deprecations",
     "https://developers.google.com/google-ads/api/docs/deprecations"),
    ("Google Ads Hilfe – Neuerungen und Ankündigungen",
     "https://support.google.com/google-ads/announcements/9048695?hl=de"),
]
ENTWICKLER_BLOG_FEED = "http://feeds.feedburner.com/GoogleAdsDeveloperBlog"


class NewsFehler(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
def _seite_als_text(url: str, maximal: int = 12000) -> str:
    antwort = requests.get(
        url, timeout=TIMEOUT,
        headers={"User-Agent": "Mozilla/5.0 (kompatibel; berisabau-ads-kanal)"})
    antwort.raise_for_status()
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", antwort.text,
                 flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:maximal]


def _entwickler_blog_text(tage: int = PRUEFZEITRAUM_TAGE) -> str:
    antwort = requests.get(ENTWICKLER_BLOG_FEED, timeout=TIMEOUT)
    antwort.raise_for_status()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    wurzel = ET.fromstring(antwort.content)
    grenze = date.today() - timedelta(days=tage)

    bloecke = []
    for eintrag in wurzel.findall("a:entry", ns):
        veroeffentlicht_roh = eintrag.findtext("a:published", default="", namespaces=ns)
        try:
            datum = date.fromisoformat(veroeffentlicht_roh[:10])
        except ValueError:
            continue
        if datum < grenze:
            continue
        titel = (eintrag.findtext("a:title", default="", namespaces=ns) or "").strip()
        link = next((l.get("href") for l in eintrag.findall("a:link", ns)
                    if l.get("rel") == "alternate"), "")
        inhalt_roh = (eintrag.findtext("a:content", default="", namespaces=ns)
                     or eintrag.findtext("a:summary", default="", namespaces=ns) or "")
        inhalt = re.sub(r"<[^>]+>", " ", inhalt_roh)
        inhalt = re.sub(r"\s+", " ", inhalt).strip()[:1500]
        bloecke.append(f"### {titel}\nDatum: {veroeffentlicht_roh[:10]}\nURL: {link}\n{inhalt}\n")

    return "\n".join(bloecke) if bloecke else "(keine Einträge im Prüfzeitraum)"


def _quellen_abrufen() -> dict[str, str]:
    """Holt alle Quellen, überspringt einzelne bei Netzwerkfehlern statt den
    ganzen Lauf abzubrechen - eine tote Quelle darf die anderen nicht mit
    ausknocken."""
    rohtexte: dict[str, str] = {}
    for name, url in QUELLEN_SEITEN:
        try:
            rohtexte[name] = _seite_als_text(url)
        except requests.RequestException as fehler:
            log.warning("Quelle nicht erreichbar, übersprungen: %s (%s)", name, fehler)
    try:
        rohtexte["Google Ads Entwickler-Blog"] = _entwickler_blog_text()
    except (requests.RequestException, ET.ParseError) as fehler:
        log.warning("Entwickler-Blog nicht erreichbar, übersprungen: %s", fehler)
    return rohtexte


# --------------------------------------------------------------------------- #
def _system_prompt(gemeldete: list[str], ignoriert: list[str]) -> str:
    gemeldete_text = "; ".join(gemeldete) or "(noch keine)"
    ignoriert_text = "; ".join(ignoriert) or "(keine)"
    return f"""Du bist Redakteur für einen privaten Telegram-Kanal zu Google Ads.
Der Kanalbetreiber führt ein Handwerksunternehmen (Bau/Sanierung, regional)
und nutzt Google Ads mit Suchkampagnen und Performance Max. Er will nur
erfahren, was für ihn wirklich zählt - kein Rauschen, keine Zweitverwertung.

Du bekommst den aktuellen Rohtext mehrerer offizieller Google-Quellen. Melde
NUR Punkte, die MINDESTENS eines dieser Kriterien erfüllen:
- betrifft Suchkampagnen oder Performance Max
- betrifft Budget, Gebotsstrategie oder Abrechnung
- betrifft lokale Anzeigen / Standorterweiterungen (Handwerk, regional)
- eine Funktion wird abgeschaltet oder erzwungen umgestellt
- Richtlinienänderung mit Sperr-Risiko fürs Konto

Alles andere ignorieren. Auch ignorieren:
- Themen, die inhaltlich zu bereits gemeldeten Überschriften passen, selbst
  wenn eine andere Quelle sie erneut aufgreift
- Themen, die der Nutzer per Ignorieren-Taste als uninteressant markiert hat
- reine Video-/App-/Display-/Shopping-Themen ohne Bezug zu Suche/PMax
- Marketing-Erfolgsmeldungen ohne konkrete Handlungsrelevanz

Bereits gemeldet (nicht erneut melden): {gemeldete_text}
Vom Nutzer ignoriert (nicht erneut melden): {ignoriert_text}

Gib AUSSCHLIESSLICH ein JSON-Array zurück, keinen Fließtext davor oder
danach. Leeres Array [], wenn nichts qualifiziert. Pro relevanter Meldung
genau dieses Objekt:
{{
  "ueberschrift": "max. 6 Wörter, Deutsch, Fachbegriffe im Original lassen",
  "was_passiert": "genau 2 Sätze, konkret, keine Floskeln",
  "bedeutung": "1 Satz: was heißt das konkret für ein Handwerksunternehmen mit Suchkampagnen/PMax",
  "tun": "1 kurze Zeile Handlungsempfehlung, oder das Wort 'nichts tun'",
  "quelle_name": "Name der Quelle, z.B. Google Ads API Release Notes",
  "quelle_url": "die exakte URL aus dem Rohtext, zu der diese Meldung gehört",
  "datum": "JJJJ-MM-TT, aus dem Rohtext"
}}

WICHTIG: Erfinde keine Zahlen, Daten oder Fakten, die nicht wörtlich im
Rohtext stehen. Steht kein Datum im Text, nimm das heutige Datum."""


def _frage_claude(rohtexte: dict[str, str]) -> list[dict]:
    if not ANTHROPIC_API_KEY:
        raise NewsFehler("ANTHROPIC_API_KEY fehlt - ohne KI kein Nachrichtenfilter.")

    system = _system_prompt(ads_verlauf.gemeldete_ueberschriften(),
                            ads_verlauf.ignorierte_themen())
    nutzer = "\n\n".join(f"## Quelle: {name}\n{text}" for name, text in rohtexte.items())

    antwort = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
        json={
            "model": ANTHROPIC_MODELL,
            "max_tokens": 2000,
            "system": system,
            "messages": [{"role": "user", "content": nutzer}],
        },
        timeout=90,
    )
    daten = antwort.json()
    if antwort.status_code >= 400:
        fehler = daten.get("error", {}).get("message", antwort.text[:300])
        raise NewsFehler(f"Anthropic-Fehler ({antwort.status_code}): {fehler}")

    inhalt = daten["content"][0]["text"].strip()
    if inhalt.startswith("```"):
        inhalt = re.sub(r"^```[a-zA-Z]*\n?", "", inhalt)
        inhalt = re.sub(r"```\s*$", "", inhalt)
    try:
        ergebnis = json.loads(inhalt)
    except json.JSONDecodeError as fehler:
        raise NewsFehler(f"KI-Antwort ist kein gültiges JSON: {fehler}\n"
                         f"Antwort: {inhalt[:400]}")
    if not isinstance(ergebnis, list):
        raise NewsFehler("KI-Antwort ist kein JSON-Array.")
    return ergebnis


# --------------------------------------------------------------------------- #
def _formatiere(meldung: dict) -> str:
    return (
        f"{meldung['ueberschrift']}\n"
        f"{meldung['was_passiert']}\n"
        f"{meldung['bedeutung']}\n"
        f"{meldung['tun']}\n"
        f"{meldung['quelle_name']}, {meldung['datum']}"
    )


def _mehr_dazu_text(meldung: dict) -> str:
    return (
        f"{meldung['ueberschrift']}\n\n"
        f"{meldung['was_passiert']}\n\n"
        f"Bedeutung: {meldung['bedeutung']}\n"
        f"Handlung: {meldung['tun']}\n\n"
        f"Quelle: {meldung['quelle_url']}"
    )


def _tage_seit(iso_zeitpunkt: str) -> int:
    return (datetime.now() - datetime.fromisoformat(iso_zeitpunkt)).days


# --------------------------------------------------------------------------- #
def pruefe_und_melde() -> dict:
    """Führt den kompletten täglichen Check aus. Gibt eine Zusammenfassung
    zurück (für die Konsolenausgabe in main.py)."""
    if not telegram_bot.aktiv_ads():
        raise NewsFehler(
            "Ads-Kanal ist nicht eingerichtet (TELEGRAM_CHAT_ID_ADS fehlt).")

    rohtexte = _quellen_abrufen()
    if not rohtexte:
        raise NewsFehler("Keine einzige Quelle war erreichbar - nichts geprüft.")

    meldungen = _frage_claude(rohtexte)

    verschickt = []
    for m in meldungen:
        url = (m.get("quelle_url") or "").strip()
        if not url or not m.get("ueberschrift"):
            continue
        hash_id = ads_verlauf.url_hash(url)
        if ads_verlauf.schon_gemeldet(hash_id):
            continue
        telegram_bot.sende_meldung(_formatiere(m), hash_id, chat_id=TELEGRAM_CHAT_ID_ADS)
        ads_verlauf.merke_meldung(hash_id, m["ueberschrift"], url, _mehr_dazu_text(m))
        verschickt.append(m["ueberschrift"])

    if not verschickt:
        letzte = ads_verlauf.letzte_meldung_am()
        still_seit = _tage_seit(letzte) if letzte else None
        if still_seit is None or still_seit >= STILLE_SCHWELLE_TAGE:
            datum_text = (datetime.fromisoformat(letzte).strftime("%d.%m.%Y")
                         if letzte else date.today().strftime("%d.%m.%Y"))
            telegram_bot.sende_text(f"Nichts Relevantes seit {datum_text}.",
                                    chat_id=TELEGRAM_CHAT_ID_ADS)
            ads_verlauf.vermerke_leermeldung()

    return {"geprueft_quellen": list(rohtexte), "verschickt": verschickt}
