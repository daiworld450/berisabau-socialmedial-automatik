"""Abschnitt 11: was der Stream über den Kanal verrät.

Nach jedem Stream stehen dieselben vier Fragen an. Sie werden hier nicht
aus dem Bauch beantwortet, sondern aus den Clips desselben Laufs:

* **Welche drei Clip-Arten hatten das größte Potenzial?** Gewichtet aus
  Durchschnittsnote *und* Menge - eine Kategorie mit einem 90er-Ausreißer
  ist kein Format, eine mit sechs 78ern schon.
* **Welche Themen häufiger?** Kategorie plus das, worüber in den starken
  Clips tatsächlich gesprochen wurde.
* **Was erzeugt Kommentare?** Die Teilnote „Kommentar" weiß das bereits;
  hier wird sie nur sichtbar gemacht.
* **Welche Serien entstehen daraus?** Die Serienformate aus
  `kategorien.py`, aber nur die, für die dieser Stream genug Material
  geliefert hat - ein Format aus einem einzigen Clip trägt keine Woche.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field

from . import kategorien as kat
from .verlauf import STOPP

# Ab wie vielen Clips eine Kategorie als Format taugt.
FORMAT_MINDESTZAHL = 2

# Nur für die Stichwortliste: Wörter, die in jedem zweiten Satz vorkommen und
# über das Thema nichts sagen. Bewusst getrennt von `verlauf.STOPP` - die
# Liste dort entscheidet mit, ob ein Satz als Füllsatz weggeschnitten wird,
# und darf deshalb nicht beliebig wachsen.
OHNE_AUSSAGE = {
    "euch", "uns", "mir", "dir", "ihm", "ihn", "sich", "dein", "mein", "sein",
    "beim", "vom", "zum", "zur", "über", "unter", "nach", "durch", "gegen",
    "ohne", "jetzt", "hier", "dort", "heute", "immer", "wieder", "mehr",
    "sehr", "ganz", "echt", "gerade", "grade", "einfach", "wirklich", "kurz",
    "schon", "eben", "leute", "sagen", "gesagt", "machen", "gemacht",
}


@dataclass
class Bild:
    kategorie: str
    anzahl: int
    schnitt: float
    bester: int
    kommentar_note: float
    potenzial: float = 0.0
    serie: str = ""


@dataclass
class Auswertung:
    stark: list[Bild] = field(default_factory=list)
    themen: list[str] = field(default_factory=list)
    kommentartreiber: list[Bild] = field(default_factory=list)
    serien: list[str] = field(default_factory=list)
    hinweis: str = ""


def _stichworte(clips: list[dict], hoechstens: int = 6) -> list[str]:
    zaehler: Counter = Counter()
    for clip in clips:
        text = f"{clip.get('thema', '')} {clip.get('texte', {}).get('kernzitat', '')}"
        for wort in re.findall(r"[\wäöüßÄÖÜ]{4,}", text.lower()):
            if wort not in STOPP and wort not in OHNE_AUSSAGE:
                zaehler[wort] += 1
    return [wort for wort, anzahl in zaehler.most_common(hoechstens) if anzahl > 1]


def auswerten(clips: list[dict], streamer: str) -> Auswertung:
    if not clips:
        return Auswertung(hinweis="Keine Clips über der Schwelle – für diesen "
                                  "Stream gibt es nichts abzuleiten.")

    je_kategorie: dict[str, list[dict]] = {}
    for clip in clips:
        je_kategorie.setdefault(clip.get("kategorie", "?"), []).append(clip)

    bilder: list[Bild] = []
    for kategorie, gruppe in je_kategorie.items():
        noten = [int(c.get("score", 0)) for c in gruppe]
        kommentar = [float(c.get("teilnoten", {}).get("kommentar", 0.0))
                     for c in gruppe]
        bild = Bild(
            kategorie=kategorie,
            anzahl=len(gruppe),
            schnitt=round(statistics.fmean(noten), 1),
            bester=max(noten),
            kommentar_note=round(statistics.fmean(kommentar), 2) if kommentar else 0.0,
            serie=kat.serienformat(kategorie, streamer)
            if kategorie in kat.KATEGORIEN else "",
        )
        # Menge zählt, aber gedämpft: der dritte Clip einer Kategorie sagt
        # weniger über das Format aus als der erste.
        bild.potenzial = round(bild.schnitt * (1 + 0.25 * (bild.anzahl - 1) ** 0.5), 1)
        bilder.append(bild)

    nach_potenzial = sorted(bilder, key=lambda b: -b.potenzial)
    nach_kommentar = sorted(bilder, key=lambda b: (-b.kommentar_note, -b.anzahl))

    stark = nach_potenzial[:3]
    serien = [b.serie for b in nach_potenzial
              if b.anzahl >= FORMAT_MINDESTZAHL and b.serie]

    hinweis = ""
    if len(clips) < 5:
        hinweis = ("Wenige Clips in diesem Stream – die Ableitung ist ein "
                   "Hinweis, keine Grundlage. Aussagekräftig wird sie ab "
                   "etwa drei ausgewerteten Streams.")

    return Auswertung(
        stark=stark,
        themen=_stichworte(clips),
        kommentartreiber=[b for b in nach_kommentar[:3] if b.kommentar_note > 0],
        serien=serien[:4],
        hinweis=hinweis,
    )


def als_text(auswertung: Auswertung, streamer: str) -> str:
    if auswertung.hinweis and not auswertung.stark:
        return auswertung.hinweis

    zeilen = ["## Kanal-Auswertung nach diesem Stream", ""]
    zeilen.append("**Drei Clip-Arten mit dem größten Potenzial**")
    for rang, bild in enumerate(auswertung.stark, start=1):
        clips = "Clip" if bild.anzahl == 1 else "Clips"
        zeilen.append(f"{rang}. {bild.kategorie} – {bild.anzahl} {clips}, "
                      f"Schnitt {bild.schnitt}, bester {bild.bester}")
    zeilen.append("")

    zeilen.append("**Häufiger produzieren**")
    if auswertung.stark:
        beste = auswertung.stark[0]
        clips = ("ein verwertbarer Clip" if beste.anzahl == 1
                 else f"{beste.anzahl} verwertbare Clips")
        zeilen.append(f"- Situationen wie in „{beste.kategorie}“ – sie trugen "
                      f"diesen Stream ({clips}).")
    if auswertung.themen:
        zeilen.append("- Wiederkehrende Stichworte der starken Clips: "
                      + ", ".join(auswertung.themen))
    else:
        zeilen.append("- Kein Thema kam mehrfach vor – für eine Themenaussage "
                      "braucht es mehrere Streams.")
    zeilen.append("")

    zeilen.append("**Erzeugt voraussichtlich Kommentare**")
    for bild in auswertung.kommentartreiber:
        zeilen.append(f"- {bild.kategorie} (Teilnote Kommentar "
                      f"{bild.kommentar_note:.2f} von 1,00)")
    if not auswertung.kommentartreiber:
        zeilen.append("- Nichts Ausgeprägtes – in diesem Stream fehlten "
                      "Meinung und Widerspruch.")
    zeilen.append("")

    zeilen.append("**Mögliche Serienformate**")
    for serie in auswertung.serien:
        zeilen.append(f"- „{serie}“")
    if not auswertung.serien:
        zeilen.append(f"- Noch keins: keine Kategorie kam auf "
                      f"{FORMAT_MINDESTZAHL} Clips. Ein Format aus einem "
                      f"einzigen Clip hält keine Woche durch.")

    if auswertung.hinweis:
        zeilen += ["", f"_{auswertung.hinweis}_"]
    return "\n".join(zeilen)
