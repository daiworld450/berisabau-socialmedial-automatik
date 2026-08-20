"""Täglicher Google-Ads-News-Check: Quellen abrufen, filtern, im festen
Format an den Kanal schicken.

Komplett regelbasiert, ohne API-Aufruf an ein Sprachmodell - kostet also
nichts im laufenden Betrieb. Der Preis dafür: die Meldungen sind wörtliche
Ausschnitte aus der Quelle statt einer freien Zusammenfassung, und die
Überschrift kommt aus einem festen Kategorie-Etikett statt frei formuliert.

Ablauf:
  1. Rohtext aller offiziellen Quellen abrufen (kein Aggregator, keine
     Zweitverwertung - siehe QUELLEN_SEITEN/ENTWICKLER_BLOG_FEED unten),
     dabei Absatzgrenzen aus dem HTML als Zeilenumbrüche erhalten.
  2. Text in überlappende Mini-Abschnitte (ein paar Zeilen) zerlegt, jeder
     Abschnitt gegen die Stichwortlisten in FILTER_KATEGORIEN geprüft UND
     auf ein Datum im Prüfzeitraum. Pro (Kategorie, Datum)-Kombination wird
     nur der längste Treffer behalten, damit nicht zehn überlappende
     Fenster dieselbe Meldung zehnmal auslösen.
  3. Jede Meldung wird per Hash (URL bzw. Quelle+Kategorie+Datum) gegen
     Doppelmeldung geprüft, formatiert, mit den drei Tasten (Merken/Mehr
     dazu/Ignorieren) verschickt und in ads_verlauf.json vermerkt. Bereits
     ignorierte Meldungen (gleicher Hash) werden nicht erneut geschickt.
  4. Ist nichts Relevantes dabei und die letzte Kanal-Nachricht liegt mehr
     als STILLE_SCHWELLE_TAGE zurück, kommt eine einzelne Lebenszeichen-
     Zeile statt täglichem Rauschen um seiner selbst willen.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import date, datetime, timedelta
from xml.etree import ElementTree as ET

import requests

import ads_verlauf
import telegram_bot
from config import TELEGRAM_CHAT_ID_ADS

log = logging.getLogger(__name__)

TIMEOUT = 30
STILLE_SCHWELLE_TAGE = 3
# Wie weit zurück ein gefundenes Datum noch als "neu" zählt. Diese
# Google-Seiten sind kumulative Changelogs mit Jahren an Historie - ohne
# dieses Fenster würde jeder alte Eintrag jeden Tag neu gemeldet.
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

# Kategorie -> (Stichwörter fürs Erkennen, feste Überschrift, Bedeutungssatz,
# Handlungsempfehlung). Deckt die fünf Filterkriterien aus der Vorgabe ab.
FILTER_KATEGORIEN = {
    "suche_pmax": {
        "schlagwoerter": [
            "search campaign", "search ads", "performance max", "pmax",
            "smart bidding", "broad match", "dynamic search ads", " dsa ",
            "ai max", "responsive search ad", "search terms", "search partner",
        ],
        "ueberschrift": "Update zu Suche/Performance Max",
        "bedeutung": "Betrifft Suchkampagnen oder Performance Max direkt.",
        "tun": "In den eigenen Kampagnen gegenchecken.",
    },
    "budget_gebot": {
        "schlagwoerter": [
            "budget", "bid strategy", "bidding", "target cpa", "target roas",
            "cost cap", "billing", "invoice", "payment method", "spending limit",
        ],
        "ueberschrift": "Update zu Budget/Geboten",
        "bedeutung": "Kann Auswirkungen auf Budget oder Gebotsstrategie haben.",
        "tun": "In den eigenen Kampagnen gegenchecken.",
    },
    "lokal": {
        "schlagwoerter": [
            "local campaign", "location extension", "location targeting",
            "service area", "local ads", "store visits", "affiliate location",
        ],
        "ueberschrift": "Update zu lokalen Anzeigen",
        "bedeutung": "Betrifft lokale Anzeigen bzw. Standorterweiterungen.",
        "tun": "Prüfen, ob sich das für die eigenen Anzeigen nutzen lässt.",
    },
    "abschaltung": {
        "schlagwoerter": [
            "deprecat", "sunset", "discontinu", "no longer support",
            "will be removed", "phased out", "phase out", "shut down",
            "migrat", "will stop",
        ],
        "ueberschrift": "Funktion wird abgeschaltet",
        "bedeutung": "Eine Funktion wird abgeschaltet oder zwangsweise umgestellt.",
        "tun": "Prüfen, ob eigene Kampagnen betroffen sind.",
    },
    "richtlinie": {
        "schlagwoerter": [
            "policy update", "policy change", "advertising polic", "suspend",
            "disapprov", "violation", "compliance", "account restriction",
        ],
        "ueberschrift": "Richtlinienänderung mit Sperr-Risiko",
        "bedeutung": "Richtlinienänderung mit möglichem Sperr-Risiko fürs Konto.",
        "tun": "Prüfen, ob eigene Kampagnen betroffen sind.",
    },
}

_DATUM_ISO = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_MONATE_EN = {m: i + 1 for i, m in enumerate([
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december"])}
_DATUM_TEXT_EN = re.compile(
    r"\b(" + "|".join(_MONATE_EN) + r")\s+(\d{1,2}),?\s+(20\d{2})\b", re.I)
_MONATE_DE = {m: i + 1 for i, m in enumerate([
    "januar", "februar", "märz", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "dezember"])}
_DATUM_TEXT_DE = re.compile(
    r"\b(\d{1,2})\.\s*(" + "|".join(_MONATE_DE) + r")\s+(20\d{2})\b", re.I)


class NewsFehler(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
def _seite_als_text(url: str, maximal: int = 90000) -> str:
    """HTML zu Text, aber mit erhaltenen Zeilenumbrüchen an Absatzgrenzen -
    sonst verschmilzt die ganze Seite zu einem einzigen langen Satz und eine
    zeilenweise Stichwortsuche findet keine sinnvollen Ausschnitte mehr.
    maximal liegt bewusst hoch: die developers.google.com-Seiten haben ein
    langes Navigationsmenü VOR dem eigentlichen Inhalt - bei einem knappen
    Limit wird der Inhalt abgeschnitten, bevor er überhaupt beginnt."""
    antwort = requests.get(
        url, timeout=TIMEOUT,
        headers={"User-Agent": "Mozilla/5.0 (kompatibel; berisabau-ads-kanal)"})
    antwort.raise_for_status()
    roh = re.sub(r"<script.*?</script>|<style.*?</style>", " ", antwort.text,
                flags=re.S | re.I)
    roh = re.sub(r"</(p|div|li|h[1-6]|tr|section|article)\s*>", "\n", roh, flags=re.I)
    roh = re.sub(r"<br\s*/?>", "\n", roh, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", roh)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    zeilen = [z.strip() for z in text.split("\n")]
    zeilen = [z for z in zeilen if z]
    return "\n".join(zeilen)[:maximal]


def _finde_datum(text: str) -> date | None:
    treffer = _DATUM_ISO.search(text)
    if treffer:
        try:
            return date.fromisoformat(treffer.group(1))
        except ValueError:
            pass
    treffer = _DATUM_TEXT_EN.search(text)
    if treffer:
        monat = _MONATE_EN.get(treffer.group(1).lower())
        if monat:
            try:
                return date(int(treffer.group(3)), monat, int(treffer.group(2)))
            except ValueError:
                pass
    treffer = _DATUM_TEXT_DE.search(text)
    if treffer:
        monat = _MONATE_DE.get(treffer.group(2).lower())
        if monat:
            try:
                return date(int(treffer.group(3)), monat, int(treffer.group(1)))
            except ValueError:
                pass
    return None


def _kategorie_treffer(text: str) -> str | None:
    text_klein = text.lower()
    for schluessel, angaben in FILTER_KATEGORIEN.items():
        if any(wort in text_klein for wort in angaben["schlagwoerter"]):
            return schluessel
    return None


def _kandidaten_aus_seite(quelle_name: str, url: str, text: str, ab_datum: date) -> list[dict]:
    """Diese Seiten sind Changelogs: eine Datumszeile, gefolgt von dem Text,
    der zu genau diesem Datum gehört, bis zur nächsten Datumszeile. Ein
    Abschnitt reicht darum exakt von einer Datumszeile bis zur nächsten -
    ein festes N-Zeilen-Fenster würde bei kurzen Einträgen (Tabellen) in den
    nächsten Eintrag hineinlaufen und Datum und Inhalt verschiedener
    Meldungen vermischen, und bei langen Einträgen (Versions-Changelogs) vor
    dem eigentlichen Inhalt abbrechen."""
    zeilen = text.split("\n")
    datum_zeilen = []
    for i, zeile in enumerate(zeilen):
        datum = _finde_datum(zeile)
        if datum is not None and ab_datum <= datum <= date.today():
            datum_zeilen.append((i, datum))

    beste: dict[tuple[str, date], str] = {}
    for pos, (i, datum) in enumerate(datum_zeilen):
        ende = datum_zeilen[pos + 1][0] if pos + 1 < len(datum_zeilen) else len(zeilen)
        ende = min(ende, i + 150)  # Deckel, falls ein Datum ganz am Seitenende isoliert steht
        ausschnitt = " ".join(zeilen[i:ende]).strip()
        if len(ausschnitt) < 40:
            continue
        kategorie = _kategorie_treffer(ausschnitt)
        if kategorie is None:
            continue
        schluessel = (kategorie, datum)
        if schluessel not in beste or len(ausschnitt) > len(beste[schluessel]):
            beste[schluessel] = ausschnitt

    return [
        {
            "quelle_name": quelle_name,
            "quelle_url": url,
            "kategorie": kategorie,
            "datum": datum,
            "text": ausschnitt[:600],
        }
        for (kategorie, datum), ausschnitt in beste.items()
    ]


def _entwickler_blog_kandidaten(ab_datum: date) -> list[dict]:
    antwort = requests.get(ENTWICKLER_BLOG_FEED, timeout=TIMEOUT)
    antwort.raise_for_status()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    wurzel = ET.fromstring(antwort.content)

    kandidaten = []
    for eintrag in wurzel.findall("a:entry", ns):
        veroeffentlicht_roh = eintrag.findtext("a:published", default="", namespaces=ns)
        try:
            datum = date.fromisoformat(veroeffentlicht_roh[:10])
        except ValueError:
            continue
        if datum < ab_datum:
            continue

        titel = (eintrag.findtext("a:title", default="", namespaces=ns) or "").strip()
        inhalt_roh = (eintrag.findtext("a:content", default="", namespaces=ns)
                     or eintrag.findtext("a:summary", default="", namespaces=ns) or "")
        inhalt = re.sub(r"<[^>]+>", " ", inhalt_roh)
        inhalt = re.sub(r"\s+", " ", inhalt).strip()

        kategorie = _kategorie_treffer(f"{titel} {inhalt}")
        if kategorie is None:
            continue

        link = next((l.get("href") for l in eintrag.findall("a:link", ns)
                    if l.get("rel") == "alternate"), "")
        kandidaten.append({
            "quelle_name": "Google Ads Entwickler-Blog",
            "quelle_url": link,
            "kategorie": kategorie,
            "datum": datum,
            "text": inhalt[:600],
            "titel": titel,
        })
    return kandidaten


def _alle_kandidaten() -> list[dict]:
    """Holt alle Quellen, überspringt einzelne bei Netzwerkfehlern statt den
    ganzen Lauf abzubrechen - eine tote Quelle darf die anderen nicht mit
    ausknocken."""
    ab_datum = date.today() - timedelta(days=PRUEFZEITRAUM_TAGE)
    kandidaten: list[dict] = []

    for name, url in QUELLEN_SEITEN:
        try:
            text = _seite_als_text(url)
            kandidaten.extend(_kandidaten_aus_seite(name, url, text, ab_datum))
        except requests.RequestException as fehler:
            log.warning("Quelle nicht erreichbar, übersprungen: %s (%s)", name, fehler)

    try:
        kandidaten.extend(_entwickler_blog_kandidaten(ab_datum))
    except (requests.RequestException, ET.ParseError) as fehler:
        log.warning("Entwickler-Blog nicht erreichbar, übersprungen: %s", fehler)

    return kandidaten


# --------------------------------------------------------------------------- #
def _hash_fuer(kandidat: dict) -> str:
    # Blog-Einträge haben eine echte, eindeutige Artikel-URL - direkt per
    # URL-Hash deduplizieren (genau wie in der Vorgabe verlangt). Die drei
    # HTML-Seiten liefern nur die Seiten-URL, nicht die einzelne Meldung -
    # dort zusätzlich Kategorie+Datum in den Hash einrechnen, sonst würden
    # alle Treffer derselben Seite denselben Hash teilen.
    if kandidat["quelle_name"] == "Google Ads Entwickler-Blog":
        return ads_verlauf.url_hash(kandidat["quelle_url"])
    schluessel = f"{kandidat['quelle_url']}#{kandidat['kategorie']}#{kandidat['datum'].isoformat()}"
    return ads_verlauf.url_hash(schluessel)


def _formatiere(kandidat: dict) -> str:
    angaben = FILTER_KATEGORIEN[kandidat["kategorie"]]
    ueberschrift = kandidat.get("titel") or angaben["ueberschrift"]
    was_passiert = kandidat["text"]
    if len(was_passiert) > 280:
        was_passiert = was_passiert[:279].rstrip() + "…"
    return (
        f"{ueberschrift}\n"
        f"{was_passiert}\n"
        f"{angaben['bedeutung']}\n"
        f"{angaben['tun']}\n"
        f"{kandidat['quelle_name']}, {kandidat['datum'].strftime('%d.%m.%Y')}"
    )


def _mehr_dazu_text(kandidat: dict) -> str:
    angaben = FILTER_KATEGORIEN[kandidat["kategorie"]]
    ueberschrift = kandidat.get("titel") or angaben["ueberschrift"]
    return (
        f"{ueberschrift}\n\n"
        f"{kandidat['text']}\n\n"
        f"Bedeutung: {angaben['bedeutung']}\n"
        f"Handlung: {angaben['tun']}\n\n"
        f"Quelle: {kandidat['quelle_url']}"
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

    kandidaten = _alle_kandidaten()

    verschickt = []
    for kandidat in kandidaten:
        hash_id = _hash_fuer(kandidat)
        if ads_verlauf.schon_gemeldet(hash_id) or ads_verlauf.ist_ignoriert(hash_id):
            continue
        ueberschrift = kandidat.get("titel") or FILTER_KATEGORIEN[kandidat["kategorie"]]["ueberschrift"]
        telegram_bot.sende_meldung(_formatiere(kandidat), hash_id, chat_id=TELEGRAM_CHAT_ID_ADS)
        ads_verlauf.merke_meldung(hash_id, ueberschrift, kandidat["quelle_url"],
                                  _mehr_dazu_text(kandidat))
        verschickt.append(ueberschrift)

    if not verschickt:
        letzte = ads_verlauf.letzte_meldung_am()
        still_seit = _tage_seit(letzte) if letzte else None
        if still_seit is None or still_seit >= STILLE_SCHWELLE_TAGE:
            datum_text = (datetime.fromisoformat(letzte).strftime("%d.%m.%Y")
                         if letzte else date.today().strftime("%d.%m.%Y"))
            telegram_bot.sende_text(f"Nichts Relevantes seit {datum_text}.",
                                    chat_id=TELEGRAM_CHAT_ID_ADS)
            ads_verlauf.vermerke_leermeldung()

    return {"geprueft_quellen": [n for n, _ in QUELLEN_SEITEN] + ["Google Ads Entwickler-Blog"],
            "verschickt": verschickt}
