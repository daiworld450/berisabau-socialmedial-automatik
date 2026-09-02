"""Die Clip-Datenbank aus Abschnitt 13 - damit nichts zweimal läuft.

Zwei Arten von Doppelung kosten Reichweite, und beide werden hier
abgefangen:

1. **Dieselbe Szene aus demselben Stream.** Zwei Fenster, die sich zur
   Hälfte überlappen, sind für den Zuschauer ein und derselbe Clip. Die
   Zeitüberlappung entscheidet, nicht die Clip-Nummer.
2. **Dieselbe Szene aus verschiedenen Läufen.** Wird ein Stream zweimal
   analysiert - etwa nach besserem Transkript -, dürfen die alten Clips
   nicht ein zweites Mal in die Warteschlange wandern. Dafür der Vergleich
   über den Themenwortschatz, der auch bei leicht verschobenen Zeiten hält.

Gespeichert wird alles, was Abschnitt 13 verlangt: Stream-ID, Datum,
Zeitstempel, Thema, Caption, Virality Score, Plattform, Veröffentlichungs-
datum und die Leistungszahlen. Die Datei ist bewusst lesbares JSON - wer
wissen will, warum ein Clip nicht noch einmal kam, soll das ohne Werkzeug
nachlesen können.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

# Wörter ohne Aussagekraft fürs Thema. Kurz gehalten: eine lange Stoppwort-
# liste macht kurze Clips einander künstlich ähnlich.
STOPP = {
    "der", "die", "das", "und", "ist", "ich", "du", "er", "sie", "es", "wir",
    "ihr", "nicht", "ein", "eine", "einen", "dem", "den", "des", "mit", "auf",
    "für", "von", "zu", "im", "in", "am", "an", "so", "war", "wie", "was",
    "aber", "auch", "doch", "mal", "man", "hat", "habe", "hab", "sind", "wenn",
    "dass", "dann", "noch", "schon", "nur", "ja", "nein", "halt", "also",
}

UEBERLAPPUNG_GRENZE = 0.4     # Anteil der kürzeren Szene
AEHNLICHKEIT_GRENZE = 0.65    # Jaccard über den Themenwortschatz


def _wortmenge(text: str) -> set[str]:
    woerter = re.findall(r"[\wäöüßÄÖÜ]{3,}", (text or "").lower())
    return {w for w in woerter if w not in STOPP}


def aehnlichkeit(links: str, rechts: str) -> float:
    a, b = _wortmenge(links), _wortmenge(rechts)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def leer() -> dict:
    return {"clips": []}


def lade(pfad: Path) -> dict:
    if not pfad.exists():
        return leer()
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return leer()
    daten.setdefault("clips", [])
    return daten


def schreib(pfad: Path, daten: dict) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def clip_id(stream_id: str, start: float) -> str:
    return f"{stream_id}-{int(round(start)):06d}"


# --------------------------------------------------------------------------- #
# Doppelungen
# --------------------------------------------------------------------------- #
def doppelt_zu(neu: dict, bestand: list[dict]) -> dict | None:
    """Gibt den kollidierenden Alteintrag zurück, sonst None."""
    for alt in bestand:
        if alt.get("clip_id") == neu.get("clip_id"):
            return alt
        if alt.get("stream_id") == neu.get("stream_id"):
            ueberschneidung = (min(alt.get("ende", 0), neu.get("ende", 0))
                               - max(alt.get("start", 0), neu.get("start", 0)))
            kuerzeste = min(alt.get("ende", 0) - alt.get("start", 0),
                            neu.get("ende", 0) - neu.get("start", 0))
            if kuerzeste > 0 and ueberschneidung / kuerzeste > UEBERLAPPUNG_GRENZE:
                return alt
        if aehnlichkeit(alt.get("thema", ""), neu.get("thema", "")) >= AEHNLICHKEIT_GRENZE:
            return alt
    return None


def aufnehmen(neue: list[dict], pfad: Path, trockenlauf: bool = False) -> dict:
    """Neue Clips in die Datenbank legen, Doppelungen abweisen."""
    daten = lade(pfad)
    bestand = daten["clips"]
    aufgenommen, abgewiesen = [], []

    for eintrag in neue:
        kollision = doppelt_zu(eintrag, bestand)
        if kollision:
            abgewiesen.append((eintrag.get("clip_id"), kollision.get("clip_id")))
            continue
        eintrag.setdefault("aufgenommen_am", date.today().isoformat())
        eintrag.setdefault("veroeffentlichungen", [])
        bestand.append(eintrag)
        aufgenommen.append(eintrag.get("clip_id"))

    if aufgenommen and not trockenlauf:
        schreib(pfad, daten)
    return {"aufgenommen": aufgenommen, "abgewiesen": abgewiesen,
            "gesamt": len(bestand)}


def finde(pfad: Path, kennung: str) -> dict | None:
    for eintrag in lade(pfad)["clips"]:
        if eintrag.get("clip_id") == kennung:
            return eintrag
    return None


# --------------------------------------------------------------------------- #
# Veröffentlichung und Leistung
# --------------------------------------------------------------------------- #
def veroeffentlicht(pfad: Path, kennung: str, plattform: str,
                    am: str | None = None, post_id: str = "") -> bool:
    daten = lade(pfad)
    for eintrag in daten["clips"]:
        if eintrag.get("clip_id") != kennung:
            continue
        eintrag.setdefault("veroeffentlichungen", [])
        for lauf in eintrag["veroeffentlichungen"]:
            if lauf.get("plattform") == plattform:
                return False        # derselbe Clip, dieselbe Plattform: nein
        eintrag["veroeffentlichungen"].append({
            "plattform": plattform,
            "datum": am or date.today().isoformat(),
            "post_id": post_id,
            "performance": {},
        })
        schreib(pfad, daten)
        return True
    return False


def performance(pfad: Path, kennung: str, plattform: str,
                zahlen: dict) -> bool:
    """Kennzahlen nach Abschnitt 14 an eine Veröffentlichung hängen."""
    daten = lade(pfad)
    for eintrag in daten["clips"]:
        if eintrag.get("clip_id") != kennung:
            continue
        for lauf in eintrag.get("veroeffentlichungen", []):
            if lauf.get("plattform") == plattform:
                lauf.setdefault("performance", {}).update(zahlen)
                lauf["performance"]["erfasst_am"] = date.today().isoformat()
                schreib(pfad, daten)
                return True
    return False


def offen(pfad: Path) -> list[dict]:
    """Clips, die noch auf keiner Plattform liefen."""
    return [e for e in lade(pfad)["clips"] if not e.get("veroeffentlichungen")]
