"""Aus Transkript und Chat eine Interessenkurve über den Stream bauen.

Der Chat ist der ehrlichste Sensor, den ein Stream hat: Zuschauer tippen
genau dann, wenn etwas passiert, und sie tippen dabei etwas Bestimmtes -
KEKW bei Lachern, monkaS bei Fremdscham, "clip it" bei allem, was jemand
behalten will. Diese Reihen werden hier je Sekunde gezählt und **gegen den
eigenen Streamdurchschnitt** normiert. Das ist wichtig: ein Stream mit
40.000 Zuschauern hat eine andere Grundlast als einer mit 400, aber in
beiden ist der Ausschlag über der eigenen Grundlast das Signal.

Ohne Chat funktioniert das Modul weiter, dann tragen nur die
Sprachsignale - schwächer, aber nicht wertlos.

Kein numpy: die Kurve eines Sechs-Stunden-Streams hat rund 21.600 Werte,
das rechnet reines Python in Sekundenbruchteilen.
"""
from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from .quellen import Stream

# Reihen, aus denen die Interessenkurve entsteht, mit ihrem Gewicht.
# Der Clipruf wiegt am schwersten, weil er kein Nebenprodukt ist: da hat ein
# Mensch bewusst gesagt "das gehört rausgeschnitten".
GEWICHTE: dict[str, float] = {
    "chat_menge": 1.00,
    "chat_lachen": 1.30,
    "chat_schock": 1.10,
    "chat_wut": 0.90,
    "chat_peinlich": 0.80,
    "chat_clipruf": 2.00,
    "chat_streit": 0.70,
    "chat_hype": 0.80,
    "sprache_lachen": 1.10,
    "sprache_wut": 1.00,
    "sprache_ueberraschung": 0.90,
    "sprache_meinung": 0.70,
    "sprache_story": 0.85,
    "sprache_spannung": 0.70,
    "sprache_fail": 0.80,
    "sprache_win": 0.70,
    "sprache_peinlich": 0.80,
    "sprache_chatbezug": 0.50,
    "sprache_reaktion": 0.50,
    "sprache_ruf": 0.80,
    "wortdichte": 0.40,
}


def lade_lexikon(pfad: Path) -> dict:
    if not pfad.exists():
        raise FileNotFoundError(f"Lexikon fehlt: {pfad}")
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    return daten


@dataclass
class Signalkurve:
    """Je Sekunde ein Wert pro Reihe, plus die gewichtete Summe."""
    aufloesung: float
    laenge: int
    reihen: dict[str, list[float]] = field(default_factory=dict)
    gesamt: list[float] = field(default_factory=list)

    def _feld(self, sekunde: float) -> int:
        return max(0, min(self.laenge - 1, int(sekunde / self.aufloesung)))

    def summe(self, reihe: str, start: float, ende: float) -> float:
        werte = self.reihen.get(reihe)
        if not werte:
            return 0.0
        return sum(werte[self._feld(start):self._feld(ende) + 1])

    def spitzenwert(self, reihe: str, start: float, ende: float) -> float:
        werte = self.reihen.get(reihe)
        if not werte:
            return 0.0
        ausschnitt = werte[self._feld(start):self._feld(ende) + 1]
        return max(ausschnitt) if ausschnitt else 0.0

    def spitzenwert_gesamt(self, start: float, ende: float) -> float:
        ausschnitt = self.verlauf(start, ende)
        return max(ausschnitt) if ausschnitt else 0.0

    def verlauf(self, start: float, ende: float) -> list[float]:
        return self.gesamt[self._feld(start):self._feld(ende) + 1]


@dataclass
class Spitze:
    """Ein Moment, an dem der Stream über seiner eigenen Grundlast liegt."""
    sekunde: float
    staerke: float
    anteile: dict[str, float]

    def fuehrend(self, anzahl: int = 3) -> list[str]:
        return [name for name, _ in
                sorted(self.anteile.items(), key=lambda p: -p[1])[:anzahl]
                if self.anteile[name] > 0]


# --------------------------------------------------------------------------- #
# Zählen
# --------------------------------------------------------------------------- #
def _muster(begriffe: list[str]) -> re.Pattern:
    """Suchmuster mit Wortgrenzen.

    Ohne die Grenzen träfe "was" auch in "etwas" und "waschen", und "lul"
    in "lullen". Bei Emotes und Emoji greifen keine Wortgrenzen - deshalb
    werden sie nur dort gesetzt, wo der Begriff an einem Wortzeichen
    beginnt bzw. endet.
    """
    teile = []
    for begriff in sorted({b.lower() for b in begriffe}, key=len, reverse=True):
        kern = re.escape(begriff)
        if begriff[:1].isalnum():
            kern = r"(?<![\w])" + kern
        if begriff[-1:].isalnum():
            kern = kern + r"(?![\w])"
        teile.append(kern)
    return re.compile("|".join(teile)) if teile else re.compile(r"(?!x)x")


def _treffer(muster: re.Pattern, text: str) -> int:
    return len(muster.findall(text.lower()))


def _normiere(werte: list[float]) -> list[float]:
    """Ausschlag über der eigenen Grundlast, robust gegen Ausreißer.

    Median und mittlere absolute Abweichung statt Mittelwert und
    Standardabweichung: ein einziger Lachanfall mit 300 Nachrichten würde
    sonst die Grundlast so weit hochziehen, dass alle anderen Momente
    verschwinden.
    """
    aktive = [w for w in werte if w > 0]
    if len(aktive) < 5:
        hoechst = max(werte) if werte else 0.0
        return [w / hoechst if hoechst else 0.0 for w in werte]
    mitte = statistics.median(aktive)
    streuung = statistics.median([abs(w - mitte) for w in aktive]) or (mitte or 1.0)
    return [max(0.0, (w - mitte) / (streuung * 1.4826)) for w in werte]


def _glaetten(werte: list[float], fenster: int = 5) -> list[float]:
    """Gleitender Mittelwert. Ein Lacher zieht sich über Sekunden, nicht über
    eine einzelne; ohne Glättung zerfällt jede Reaktion in Nadeln."""
    if fenster <= 1 or len(werte) < fenster:
        return list(werte)
    rand = fenster // 2
    geglaettet = []
    for i in range(len(werte)):
        von, bis = max(0, i - rand), min(len(werte), i + rand + 1)
        geglaettet.append(sum(werte[von:bis]) / (bis - von))
    return geglaettet


def kurve(stream: Stream, lexikon: dict, aufloesung: float = 1.0) -> Signalkurve:
    laenge = max(1, int(stream.laenge / aufloesung) + 1)
    roh: dict[str, list[float]] = {name: [0.0] * laenge for name in GEWICHTE}

    chat_muster = {f"chat_{art}": _muster(begriffe)
                   for art, begriffe in lexikon.get("chat", {}).items()}
    sprach_muster = {f"sprache_{art}": _muster(begriffe)
                     for art, begriffe in lexikon.get("sprache", {}).items()}

    def feld(sekunde: float) -> int:
        return max(0, min(laenge - 1, int(sekunde / aufloesung)))

    for nachricht in stream.chat:
        i = feld(nachricht.sekunde)
        roh["chat_menge"][i] += 1.0
        text = nachricht.text.lower()
        for name, muster in chat_muster.items():
            if name in roh and muster.search(text):
                roh[name][i] += 1.0

    for segment in stream.segmente:
        i = feld(segment.start)
        text = segment.text
        for name, muster in sprach_muster.items():
            if name in roh:
                roh[name][i] += _treffer(muster, text)
        # Rufe und Ausrufe: GROSSSCHRIFT und Ausrufezeichen im Transkript
        # zeigen an, dass jemand lauter geworden ist.
        rufe = len(re.findall(r"\b[A-ZÄÖÜ]{3,}\b", text)) + text.count("!")
        roh["sprache_ruf"][i] += min(3.0, float(rufe))
        if segment.dauer > 0:
            roh["wortdichte"][i] += len(text.split()) / segment.dauer

    reihen = {name: _glaetten(_normiere(werte)) for name, werte in roh.items()}
    gesamt = [0.0] * laenge
    for name, werte in reihen.items():
        gewicht = GEWICHTE[name]
        for i, wert in enumerate(werte):
            gesamt[i] += wert * gewicht

    return Signalkurve(aufloesung=aufloesung, laenge=laenge,
                       reihen=reihen, gesamt=gesamt)


# --------------------------------------------------------------------------- #
# Spitzen finden
# --------------------------------------------------------------------------- #
def spitzen(kurve_: Signalkurve, schwelle: float = 1.6,
            mindestabstand: float = 25.0, hoechstens: int = 60) -> list[Spitze]:
    """Die stärksten Momente, mit Mindestabstand zueinander.

    Der Mindestabstand verhindert, dass ein einziger langer Lachanfall
    fünfmal als eigener Clip auftaucht. Er ist bewusst kleiner als die
    kürzeste sinnvolle Clip-Länge nicht - sondern größer: zwei Clips, die
    sich zur Hälfte überlappen, sind für den Zuschauer derselbe Clip.
    """
    werte = kurve_.gesamt
    if not werte:
        return []

    kandidaten = [(wert, i) for i, wert in enumerate(werte) if wert >= schwelle]
    kandidaten.sort(reverse=True)

    abstand_felder = max(1, int(mindestabstand / kurve_.aufloesung))
    gewaehlt: list[int] = []
    for wert, i in kandidaten:
        if any(abs(i - j) < abstand_felder for j in gewaehlt):
            continue
        gewaehlt.append(i)
        if len(gewaehlt) >= hoechstens:
            break

    ergebnis = []
    for i in sorted(gewaehlt):
        anteile = {name: reihe[i] * GEWICHTE[name]
                   for name, reihe in kurve_.reihen.items() if reihe[i] > 0}
        ergebnis.append(Spitze(sekunde=i * kurve_.aufloesung,
                               staerke=werte[i], anteile=anteile))
    return ergebnis
