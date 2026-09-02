"""Dynamische Untertitel: 3-7 Wörter gleichzeitig, exakt am Gesprochenen.

Abschnitt 7 der Betriebsanweisung ist streng, und das aus gutem Grund: über
80 Prozent der Shorts laufen ohne Ton. Der Untertitel ist nicht Beiwerk, er
*ist* der Clip für die meisten Zuschauer.

Drei Regeln setzt dieses Modul technisch durch:

* **Nie mehr als sieben Wörter gleichzeitig.** Mehr liest niemand im
  Vorbeiscrollen. Bei drei Wörtern ist der Takt am schnellsten - deshalb
  liegt das Ziel bei vier bis fünf.
* **Umbruch an der Satzgrenze, nicht am Wortzähler.** Ein Umbruch mitten in
  "ich hab ... ihm gesagt" zerreißt die Aussage.
* **Zeitachse des fertigen Clips.** Die herausgeschnittene Stille wird
  herausgerechnet (`Kandidat.clipzeit`), sonst laufen die Untertitel dem
  Bild um Sekunden hinterher.

Hervorhebung: nur Wörter, die die Aussage tragen (Lexikon `wortgewicht`)
oder die der Streamer selbst betont (Ausrufezeichen, Großschrift). Wird
alles hervorgehoben, ist nichts hervorgehoben.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .kandidaten import Kandidat

ZIEL_WOERTER = 5
MAX_WOERTER = 7
MIN_WOERTER = 3
# Sieben kurze Wörter passen nebeneinander, sieben lange nicht. Bei 1080 px
# Breite und 72 px Schrift reißt eine Zeile ab etwa 26 Zeichen um - deshalb
# ist die Zeichenzahl die zweite Grenze neben der Wortzahl.
MAX_ZEICHEN = 26
MAX_STANDZEIT = 2.4       # Sekunden, die eine Zeile höchstens stehen bleibt
MIN_STANDZEIT = 0.45

_SATZENDE = re.compile(r"[.!?…]$")
_KOMMA = re.compile(r"[,;:]$")


@dataclass
class Zeile:
    start: float
    ende: float
    woerter: list[str]
    betont: set[int] = field(default_factory=set)

    @property
    def text(self) -> str:
        return " ".join(self.woerter)

    @property
    def dauer(self) -> float:
        return max(0.0, self.ende - self.start)


def _betonungen(lexikon: dict) -> set[str]:
    roh = lexikon.get("wortgewicht", {}).get("hervorheben", [])
    return {w.lower() for w in roh}


def _sauber(wort: str) -> str:
    return re.sub(r"[^\wäöüßÄÖÜ]+", "", wort).lower()


def zeilen(kandidat: Kandidat, lexikon: dict) -> list[Zeile]:
    """Untertitelzeilen in der Zeitachse des fertigen Clips."""
    betonbar = _betonungen(lexikon)
    gesammelt: list[tuple[str, float, float]] = []
    for segment in kandidat.segmente:
        for wort in segment.wortliste():
            if wort.ende <= kandidat.start or wort.start >= kandidat.ende:
                continue
            if kandidat.in_auslassung(wort.start):
                continue
            gesammelt.append((wort.text,
                              kandidat.clipzeit(wort.start),
                              kandidat.clipzeit(wort.ende)))
    if not gesammelt:
        return []

    ergebnis: list[Zeile] = []
    puffer: list[tuple[str, float, float]] = []

    def abschliessen() -> None:
        if not puffer:
            return
        woerter = [w for w, _, _ in puffer]
        start = puffer[0][1]
        ende = max(puffer[-1][2], start + MIN_STANDZEIT)
        betont = {i for i, (wort, _, _) in enumerate(puffer)
                  if _sauber(wort) in betonbar
                  or (wort.isupper() and len(wort) > 2)
                  or wort.endswith("!")}
        ergebnis.append(Zeile(round(start, 2), round(ende, 2), woerter, betont))
        puffer.clear()

    for eintrag in gesammelt:
        wort, start, ende = eintrag
        if puffer:
            standzeit = ende - puffer[0][1]
            luecke = start - puffer[-1][2]
            zeichen = sum(len(w) + 1 for w, _, _ in puffer) + len(wort)
            if (len(puffer) >= MAX_WOERTER or standzeit > MAX_STANDZEIT
                    or luecke > 0.6
                    or (zeichen > MAX_ZEICHEN and len(puffer) >= 2)):
                abschliessen()
        puffer.append(eintrag)
        if len(puffer) >= MIN_WOERTER and _SATZENDE.search(wort):
            abschliessen()
        elif len(puffer) >= ZIEL_WOERTER and _KOMMA.search(wort):
            abschliessen()
    abschliessen()

    # Eine einzelne Restzeile mit ein bis zwei Wörtern hängt man an die
    # vorige an, statt sie für 0,3 Sekunden aufblitzen zu lassen.
    if len(ergebnis) >= 2 and len(ergebnis[-1].woerter) < MIN_WOERTER:
        letzte = ergebnis.pop()
        vorletzte = ergebnis[-1]
        versatz = len(vorletzte.woerter)
        vorletzte.woerter += letzte.woerter
        vorletzte.betont |= {versatz + i for i in letzte.betont}
        vorletzte.ende = letzte.ende
    return ergebnis


def als_text(zeilen_: list[Zeile]) -> str:
    """Der vollständige Untertiteltext für die Ausgabe nach Abschnitt 10."""
    return " ".join(z.text for z in zeilen_).strip()


# --------------------------------------------------------------------------- #
# Ausgabeformate
# --------------------------------------------------------------------------- #
def _srt_zeit(wert: float) -> str:
    ganz = int(wert)
    ms = int(round((wert - ganz) * 1000))
    std, rest = divmod(ganz, 3600)
    minute, sek = divmod(rest, 60)
    return f"{std:02d}:{minute:02d}:{sek:02d},{ms:03d}"


def als_srt(zeilen_: list[Zeile]) -> str:
    teile = []
    for nummer, zeile in enumerate(zeilen_, start=1):
        teile.append(f"{nummer}\n{_srt_zeit(zeile.start)} --> "
                     f"{_srt_zeit(zeile.ende)}\n{zeile.text}\n")
    return "\n".join(teile)


def _ass_zeit(wert: float) -> str:
    ganz = int(wert)
    hundertstel = int(round((wert - ganz) * 100))
    std, rest = divmod(ganz, 3600)
    minute, sek = divmod(rest, 60)
    return f"{std:d}:{minute:02d}:{sek:02d}.{hundertstel:02d}"


ASS_KOPF = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Clip,{schrift},{groesse},&H00FFFFFF,&H00000000,&H80000000,-1,0,1,7,3,2,60,60,{rand},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def als_ass(zeilen_: list[Zeile], schrift: str = "Arial Black",
            groesse: int = 72, rand: int = 420,
            akzent: str = "&H0022DDFF&") -> str:
    """ASS-Untertitel zum Einbrennen - groß, mittig, mit Akzentfarbe.

    Der untere Rand von 420 Pixeln hält die Zeilen aus der Zone, in der
    TikTok Benutzername, Caption und Buttons einblendet. Wer sie tiefer
    setzt, verschenkt sie an die Oberfläche der App.
    """
    teile = [ASS_KOPF.format(schrift=schrift, groesse=groesse, rand=rand)]
    for zeile in zeilen_:
        stueck = []
        for i, wort in enumerate(zeile.woerter):
            if i in zeile.betont:
                stueck.append(r"{\c" + akzent + r"}" + wort + r"{\c&H00FFFFFF&}")
            else:
                stueck.append(wort)
        teile.append(f"Dialogue: 0,{_ass_zeit(zeile.start)},"
                     f"{_ass_zeit(zeile.ende)},Clip,,0,0,0,,{' '.join(stueck)}")
    return "\n".join(teile) + "\n"
