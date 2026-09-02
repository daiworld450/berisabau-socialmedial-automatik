"""Die zwölf Content-Kategorien mit ihren Eigenschaften.

Die Kategorie ist nicht nur ein Etikett für die spätere Auswertung. Sie
entscheidet mit über drei Teilnoten der Bewertung (Share, Kommentar,
Follower), über die Hashtags und über das Serienformat, in das ein Clip
gehört. Deshalb steht sie hier zentral und nicht verstreut.

Die Neigungswerte sind Startwerte, keine Wahrheit. Sobald echte Zahlen
vorliegen, verschiebt `lernkurve.py` die Gewichtung an der tatsächlichen
Leistung des Kontos - siehe Abschnitt 14 der Betriebsanweisung.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Kategorie:
    name: str
    # Signalreihen aus signale.py, die für diese Kategorie sprechen.
    signale: dict[str, float]
    # Startneigungen 0..1 für die drei sozialen Teilnoten.
    share: float
    kommentar: float
    follower: float
    # Serienformat nach Abschnitt 11 - "{s}" wird durch den Streamernamen ersetzt.
    serie: str
    hook_muster: list[str] = field(default_factory=list)


KATEGORIEN: dict[str, Kategorie] = {
    "FUNNY": Kategorie(
        "FUNNY",
        {"chat_lachen": 1.0, "sprache_lachen": 0.9, "chat_clipruf": 0.4},
        share=0.95, kommentar=0.55, follower=0.75,
        serie="Die wildesten Stream-Momente von {s}",
        hook_muster=["Damit hat wirklich niemand gerechnet 💀",
                     "Seine Reaktion sagt alles 😂",
                     "Er hat sich nicht mehr eingekriegt 😂"]),
    "RAGE": Kategorie(
        "RAGE",
        {"sprache_wut": 1.0, "chat_wut": 0.9, "sprache_ruf": 0.6},
        share=0.85, kommentar=0.80, follower=0.70,
        serie="Chat bringt {s} zum Ausrasten",
        hook_muster=["Er war komplett fertig mit den Nerven.",
                     "Und dann ist es passiert 💀",
                     "Das war der Moment, in dem es kippte."]),
    "REACTION": Kategorie(
        "REACTION",
        {"sprache_reaktion": 1.0, "chat_schock": 0.6},
        share=0.70, kommentar=0.70, follower=0.65,
        serie="{s} reagiert auf …",
        hook_muster=["Seine Reaktion sagt alles 😂",
                     "Er konnte es nicht fassen.",
                     "Guck auf sein Gesicht."]),
    "STORY": Kategorie(
        "STORY",
        {"sprache_story": 1.0, "sprache_spannung": 0.7, "wortdichte": 0.4},
        share=0.65, kommentar=0.75, follower=0.90,
        serie="{s} Storytime",
        hook_muster=["Warte bis zum Ende 😂",
                     "Das hat er noch nie erzählt.",
                     "Diese Geschichte glaubt ihm keiner."]),
    "CONTROVERSIAL": Kategorie(
        "CONTROVERSIAL",
        {"sprache_meinung": 1.0, "chat_streit": 1.0},
        share=0.80, kommentar=1.00, follower=0.60,
        serie="{s} sagt, was keiner sagt",
        hook_muster=["Das hätte er besser nicht gesagt…",
                     "Der Chat ist danach explodiert.",
                     "Damit macht er sich keine Freunde."]),
    "GAMING": Kategorie(
        "GAMING",
        {"chat_hype": 0.8, "sprache_win": 0.6, "sprache_reaktion": 0.3},
        share=0.60, kommentar=0.50, follower=0.55,
        serie="{s} im Spiel",
        hook_muster=["Guck, was gleich passiert.",
                     "Das war kein Zufall.",
                     "Er wusste genau, was er tut."]),
    "FAIL": Kategorie(
        "FAIL",
        {"sprache_fail": 1.0, "chat_peinlich": 0.8, "chat_lachen": 0.5},
        share=0.90, kommentar=0.60, follower=0.65,
        serie="{s} verkackt es",
        hook_muster=["Er wusste sofort, dass er einen Fehler gemacht hat.",
                     "Eine Sekunde später war alles vorbei 💀",
                     "Das tut beim Zusehen weh."]),
    "WIN": Kategorie(
        "WIN",
        {"sprache_win": 1.0, "chat_hype": 1.0},
        share=0.75, kommentar=0.50, follower=0.60,
        serie="{s} liefert ab",
        hook_muster=["Er hat es vorher angekündigt.",
                     "Niemand hat ihm das zugetraut.",
                     "Warte bis zum Ende 😂"]),
    "CHAT MOMENT": Kategorie(
        "CHAT MOMENT",
        {"sprache_chatbezug": 1.0, "chat_streit": 0.4, "chat_clipruf": 0.3},
        share=0.70, kommentar=0.95, follower=0.70,
        serie="Chat ist komplett eskaliert",
        hook_muster=["Chat ist komplett eskaliert 💀",
                     "Ein Zuschauer hat ihn zerstört.",
                     "Er hätte den Chat nicht lesen sollen."]),
    "HOT TAKE": Kategorie(
        "HOT TAKE",
        {"sprache_meinung": 1.0, "sprache_ruf": 0.4},
        share=0.85, kommentar=0.95, follower=0.70,
        serie="{s} ohne Filter",
        hook_muster=["Das sagt sonst keiner laut.",
                     "Er meint das komplett ernst.",
                     "Damit hat er sich nicht beliebt gemacht."]),
    "UNEXPECTED": Kategorie(
        "UNEXPECTED",
        {"sprache_ueberraschung": 1.0, "chat_schock": 1.0},
        share=1.00, kommentar=0.65, follower=0.75,
        serie="{s} ohne Kontext",
        hook_muster=["Damit hat wirklich niemand gerechnet 💀",
                     "Und dann kam das hier.",
                     "Guck bis zur letzten Sekunde."]),
    "CLIP / MEME": Kategorie(
        "CLIP / MEME",
        {"chat_clipruf": 1.0, "chat_lachen": 0.5},
        share=0.90, kommentar=0.55, follower=0.60,
        serie="{s} ohne Kontext",
        hook_muster=["Kein Kontext. Braucht auch keinen.",
                     "Das läuft seit Tagen in meinem Kopf 💀",
                     "Zwei Sekunden, die alles sagen."]),
}

REIHENFOLGE = list(KATEGORIEN)


def bestimme(anteile: dict[str, float], text: str = "") -> tuple[str, float]:
    """Kategorie aus den Signalanteilen eines Moments.

    Rückgabe ist Name und Sicherheit 0..1. Die Sicherheit ist der Abstand
    zur zweitbesten Kategorie: liegt alles dicht beieinander, war der Moment
    nicht eindeutig, und das soll die Bewertung wissen.
    """
    # chat_menge bleibt bewusst außen vor: der Chat wird bei *jedem* starken
    # Moment schneller, egal welcher Art. Als Kategoriesignal würde er alles
    # zu "CHAT MOMENT" machen - gemessen, nicht vermutet.
    punkte: dict[str, float] = {}
    for name, kategorie in KATEGORIEN.items():
        punkte[name] = sum(anteile.get(reihe, 0.0) * gewicht
                           for reihe, gewicht in kategorie.signale.items())

    rangliste = sorted(punkte.items(), key=lambda p: -p[1])
    bester, wert = rangliste[0]
    if wert <= 0:
        # Kein Signal trägt: das ist entweder Gameplay ohne Reaktion oder
        # eine reine Wortpassage. Der Text entscheidet.
        return ("STORY" if len(text.split()) > 25 else "GAMING"), 0.2

    zweiter = rangliste[1][1] if len(rangliste) > 1 else 0.0
    sicherheit = min(1.0, (wert - zweiter) / wert) if wert else 0.0
    return bester, max(0.2, sicherheit)


# --------------------------------------------------------------------------- #
# Hashtags
# --------------------------------------------------------------------------- #
def _tag(text: str) -> str:
    """'Counter-Strike 2' -> '#counterstrike2'."""
    # Reihenfolge ist wichtig: NFKD zerlegt "ü" in u + Trema, danach greift
    # kein replace("ü", "ue") mehr - aus "Grüße" würde "grusse" statt
    # "gruesse". Also erst ersetzen, dann zerlegen.
    roh = text.lower()
    for zeichen, ersatz in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"),
                            ("ß", "ss")):
        roh = roh.replace(zeichen, ersatz)
    roh = unicodedata.normalize("NFKD", roh)
    roh = "".join(z for z in roh if not unicodedata.combining(z))
    roh = re.sub(r"[^a-z0-9]", "", roh)
    return f"#{roh}" if roh else ""


def lade_hashtags(pfad: Path) -> dict:
    return json.loads(pfad.read_text(encoding="utf-8"))


def hashtags(kategorie: str, streamer: str, spiel: str, saetze: dict,
             anzahl: int = 7) -> list[str]:
    """5-8 Hashtags aus fünf Töpfen, ohne Blindfüller.

    Reihenfolge ist Absicht: Streamer zuerst (Wiedererkennung), dann
    Kategorie, dann Spiel, dann Trend, zuletzt Allgemeines. Wird die
    Wunschzahl vorher erreicht, bleiben die schwächeren Töpfe außen vor -
    lieber fünf passende als acht mit Streuverlust.
    """
    anzahl = max(5, min(8, anzahl))
    name = _tag(streamer).lstrip("#")
    gewaehlt: list[str] = []

    def nimm(kandidaten: list[str], hoechstens: int) -> None:
        gesetzt = 0
        for roh in kandidaten:
            if gesetzt >= hoechstens or len(gewaehlt) >= anzahl:
                return
            tag = roh.replace("{streamer}", name).lower()
            if not tag.startswith("#"):
                tag = _tag(tag)
            if tag and tag != "#" and tag not in gewaehlt:
                gewaehlt.append(tag)
                gesetzt += 1

    nimm(saetze.get("streamer", []), 2)
    nimm(saetze.get("kategorien", {}).get(kategorie, []), 3)

    if spiel:
        ausnahme = saetze.get("spiele", {}).get(spiel.strip().lower())
        nimm([ausnahme or _tag(spiel)], 1)

    nimm(saetze.get("trend", []), 2)
    nimm(saetze.get("allgemein", []), anzahl)
    return gewaehlt[:anzahl]


def serienformat(kategorie: str, streamer: str) -> str:
    vorlage = KATEGORIEN[kategorie].serie if kategorie in KATEGORIEN else "{s} Clips"
    return vorlage.replace("{s}", streamer)
