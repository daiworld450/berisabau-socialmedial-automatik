"""Abschnitt 14: aus veröffentlichten Clips lernen, welche Art trägt.

Der Kern ist eine einzige Frage: **schneidet eine Kategorie auf diesem
Konto besser ab als der Durchschnitt dieses Kontos?** Nicht besser als ein
Branchenwert, nicht besser als gefühlt - besser als das, was derselbe Kanal
sonst erreicht. Alles andere wäre geraten.

Drei Vorsichtsmaßnahmen, ohne die so ein Regelkreis kippt:

* **Verhältniszahlen statt Rohzahlen.** Ein Clip mit 400.000 Views hat
  natürlich mehr Kommentare als einer mit 4.000. Verglichen wird deshalb
  je View.
* **Schrumpfung nach Stichprobe.** Zwei Rage-Clips sind kein Beweis. Der
  Faktor bewegt sich erst mit wachsender Zahl an Clips voll aus - bei zwei
  Clips zu einem Drittel, bei zehn fast ganz.
* **Deckel.** Kein Faktor geht unter 0,85 oder über 1,15. Gelernte Vorlieben
  sollen die Messung verschieben, nicht ersetzen; sonst frisst sich das
  System in eine Kategorie fest und der Kanal wird eintönig.

Die Teilnoten werden gezielt bewegt: Wer geteilt wird, hebt „share"; wer
kommentiert wird, hebt „kommentar"; wer zu Ende geschaut wird, hebt
„watchtime" und „hook". Ein pauschaler Bonus auf alles wäre unbrauchbar.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path

from . import verlauf

# Kennzahl -> Teilnote, die sie belegt.
BELEGT = {
    "completion": ("watchtime", "hook"),
    "watchtime_sekunden": ("watchtime",),
    "shares": ("share",),
    "saves": ("share",),
    "kommentare": ("kommentar",),
    "follower": ("follower",),
    "likes": ("unterhaltung",),
}

DECKEL_UNTEN = 0.85
DECKEL_OBEN = 1.15
SCHRUMPFUNG_K = 3.0     # ab wie vielen Clips die Hälfte des Effekts greift
MINDESTZAHL = 2         # darunter wird für eine Kategorie gar nichts gelernt


@dataclass
class Kategoriebild:
    kategorie: str
    anzahl: int
    views_schnitt: float
    raten: dict[str, float] = field(default_factory=dict)
    index: float = 1.0


def _zahl(wert) -> float:
    try:
        return float(wert)
    except (TypeError, ValueError):
        return 0.0


def _raten(leistung: dict) -> dict[str, float]:
    """Kennzahlen einer Veröffentlichung als Verhältniszahlen."""
    views = _zahl(leistung.get("views"))
    raten: dict[str, float] = {}

    completion = _zahl(leistung.get("completion"))
    if completion > 1.0:            # als Prozent geliefert
        completion /= 100.0
    if completion:
        raten["completion"] = completion

    watchtime = _zahl(leistung.get("watchtime_sekunden"))
    dauer = _zahl(leistung.get("dauer"))
    if watchtime and dauer:
        raten["watchtime_sekunden"] = min(1.5, watchtime / dauer)
    elif watchtime:
        raten["watchtime_sekunden"] = watchtime

    if views > 0:
        for name in ("shares", "saves", "kommentare", "follower", "likes"):
            wert = _zahl(leistung.get(name))
            if wert:
                raten[name] = wert / views
    return raten


def sammle(pfad: Path) -> list[Kategoriebild]:
    """Je Kategorie ein Bild aus allen erfassten Veröffentlichungen."""
    je_kategorie: dict[str, list[dict]] = {}
    views: dict[str, list[float]] = {}

    for eintrag in verlauf.lade(pfad)["clips"]:
        kategorie = eintrag.get("kategorie") or "?"
        for lauf in eintrag.get("veroeffentlichungen", []):
            leistung = lauf.get("performance") or {}
            if not leistung or "erfasst_am" not in leistung:
                continue
            gemischt = dict(leistung)
            gemischt.setdefault("dauer", eintrag.get("dauer"))
            raten = _raten(gemischt)
            if not raten:
                continue
            je_kategorie.setdefault(kategorie, []).append(raten)
            views.setdefault(kategorie, []).append(_zahl(leistung.get("views")))

    bilder = []
    for kategorie, liste in je_kategorie.items():
        mittel = {}
        for name in {n for r in liste for n in r}:
            werte = [r[name] for r in liste if name in r]
            mittel[name] = statistics.fmean(werte)
        bilder.append(Kategoriebild(
            kategorie=kategorie, anzahl=len(liste),
            views_schnitt=statistics.fmean(views[kategorie]) if views[kategorie] else 0.0,
            raten=mittel))
    return sorted(bilder, key=lambda b: -b.anzahl)


def faktoren(pfad: Path) -> dict[str, dict[str, float]]:
    """Die Korrekturfaktoren, die `bewertung.bewerte` entgegennimmt."""
    bilder = sammle(pfad)
    if len(bilder) < 2:
        return {}       # ohne Vergleichsgruppe gibt es nichts zu lernen

    # Kontoschnitt je Kennzahl über alle Kategorien.
    schnitt: dict[str, float] = {}
    for name in {n for b in bilder for n in b.raten}:
        werte = [b.raten[name] for b in bilder if name in b.raten]
        schnitt[name] = statistics.fmean(werte) if werte else 0.0

    ergebnis: dict[str, dict[str, float]] = {}
    for bild in bilder:
        if bild.anzahl < MINDESTZAHL:
            continue
        vertrauen = bild.anzahl / (bild.anzahl + SCHRUMPFUNG_K)
        je_note: dict[str, list[float]] = {}
        for name, wert in bild.raten.items():
            grund = schnitt.get(name, 0.0)
            if grund <= 0:
                continue
            abweichung = (wert / grund) - 1.0
            for note in BELEGT.get(name, ()):
                je_note.setdefault(note, []).append(abweichung)

        gesetzt: dict[str, float] = {}
        for note, abweichungen in je_note.items():
            roh = 1.0 + statistics.fmean(abweichungen) * vertrauen
            gesetzt[note] = round(min(DECKEL_OBEN, max(DECKEL_UNTEN, roh)), 3)
        if gesetzt:
            gesetzt["gesamt"] = round(
                min(DECKEL_OBEN, max(DECKEL_UNTEN,
                                     statistics.fmean(gesetzt.values()))), 3)
            bild.index = gesetzt["gesamt"]
            ergebnis[bild.kategorie] = gesetzt
    return ergebnis


def bericht(pfad: Path) -> str:
    """Was gelernt wurde, in Sätzen - für den Menschen, nicht für die Maschine."""
    bilder = sammle(pfad)
    if not bilder:
        return ("Noch keine erfassten Kennzahlen. Solange nichts gemessen ist, "
                "bewertet das System rein nach Signalen – das ist der "
                "vorgesehene Zustand am Anfang.")

    korrektur = faktoren(pfad)
    zeilen = ["Gelernt aus veröffentlichten Clips:", ""]
    for bild in bilder:
        teile = []
        if "completion" in bild.raten:
            teile.append(f"Completion {bild.raten['completion'] * 100:.0f} %")
        for name, beschriftung in (("shares", "Shares/View"),
                                   ("kommentare", "Kommentare/View"),
                                   ("follower", "Follower/View")):
            if name in bild.raten:
                teile.append(f"{beschriftung} {bild.raten[name] * 1000:.1f}‰")
        faktor = korrektur.get(bild.kategorie, {}).get("gesamt")
        marke = f"  Faktor {faktor:.2f}" if faktor else "  (zu wenige Clips)"
        zeilen.append(f"{bild.kategorie:<14} n={bild.anzahl:<3} "
                      f"{', '.join(teile) or '—'}{marke}")

    stark = [k for k, w in korrektur.items() if w.get("gesamt", 1.0) > 1.03]
    schwach = [k for k, w in korrektur.items() if w.get("gesamt", 1.0) < 0.97]
    zeilen.append("")
    if stark:
        zeilen.append("Bevorzugt ab jetzt: " + ", ".join(sorted(stark)))
    if schwach:
        zeilen.append("Zurückgestuft: " + ", ".join(sorted(schwach)))
    if not stark and not schwach:
        zeilen.append("Keine Kategorie liegt deutlich vorn – die Auswahl "
                      "bleibt unverändert.")
    return "\n".join(zeilen)
