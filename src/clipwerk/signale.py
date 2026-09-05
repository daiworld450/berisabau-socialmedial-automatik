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


GESAMTGEWICHT = sum(GEWICHTE.values())

# Wie weit ein einzelnes Sprachsegment höchstens ausstrahlt. Ein
# Whisper-Segment ist selten länger; die Grenze schützt nur davor, dass ein
# durchlaufender Monolog eine halbe Minute gleichmäßig einfärbt.
SEGMENT_MAX_FELDER = 15

# Ausschlag, ab dem ein Moment als Spitze gilt - gemessen an einem Stream
# mit vollem Sensorsatz. Bei fehlendem Chat wandert die Schwelle mit
# `Signalkurve.bezug` mit.
SPITZENSCHWELLE = 1.6


def lade_lexikon(pfad: Path) -> dict:
    if not pfad.exists():
        raise FileNotFoundError(f"Lexikon fehlt: {pfad}")
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    return daten


@dataclass
class Signalkurve:
    """Je Sekunde ein Wert pro Reihe, plus die gewichtete Summe.

    `bezug` ist der Anteil des Gesamtgewichts, der in diesem Stream
    überhaupt belegt ist. Er ist 1,0, wenn alle Sensoren Daten liefern, und
    rund 0,53, wenn der Chat fehlt und nur die Sprachreihen tragen.

    Warum das gebraucht wird: `gesamt` ist eine **Summe** über die Reihen.
    Fällt der halbe Sensorsatz weg, halbiert sich die Kurve - ohne dass der
    Stream langweiliger geworden wäre. Jede feste Zahl, die an dieser Kurve
    gemessen wird (die Spitzenschwelle hier, der Stärkedeckel in der
    Bewertung), muss deshalb mit `bezug` mitwandern. Sonst misst man nicht
    den Stream, sondern die Anzahl der Sensoren.
    """
    aufloesung: float
    laenge: int
    reihen: dict[str, list[float]] = field(default_factory=dict)
    gesamt: list[float] = field(default_factory=list)
    hat_chat: bool = True
    hat_sprache: bool = True

    @property
    def bezug(self) -> float:
        """Anteil des Gesamtgewichts, der in diesem Stream messbar ist.

        Bewusst an der **Quelle** festgemacht und nicht daran, welche Reihe
        zufällig gefeuert hat: ob in zweieinhalb Stunden einmal das Wort
        „verkackt" fiel, ist eine Aussage über den Stream. Ob es einen Chat
        gibt, ist eine über die Datenlage. Nur die zweite darf den Maßstab
        verschieben.
        """
        belegt = sum(gewicht for name, gewicht in GEWICHTE.items()
                     if (self.hat_chat if name.startswith("chat_")
                         else self.hat_sprache))
        return round(belegt / GESAMTGEWICHT, 4) if belegt else 1.0

    def hat(self, reihe: str) -> bool:
        """Ist diese Reihe in diesem Stream überhaupt messbar?"""
        return self.hat_chat if reihe.startswith("chat_") else self.hat_sprache

    @property
    def spitzenniveau(self) -> float:
        """Wie hoch dieser Stream im besten Fall kommt.

        Das 99,9-Perzentil, nicht der Höchstwert: ein einzelner Ausreißer
        soll nicht bestimmen, was „stark" heißt.

        Gebraucht, weil `bezug` nur zählt, *wie viele* Sensoren tragen,
        nicht *wie laut* sie sind. Ein Chat schlägt ein Vielfaches dessen
        aus, was Sprachreihen erreichen - die sind schon durch die
        Normierung nach oben gedeckelt. Ohne diesen Bezugspunkt misst die
        Unterhaltungsnote weiter die Datenlage statt den Moment.
        """
        if not self.gesamt:
            return 0.0
        sortiert = sorted(self.gesamt)
        return sortiert[min(len(sortiert) - 1, int(0.999 * len(sortiert)))]

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


# Ab welchem Anteil belegter Sekunden eine Reihe als *laufend* gilt und
# nicht mehr als *seltenes Ereignis*. Der Unterschied entscheidet, was die
# Grundlast ist - siehe _normiere.
DICHTE_GRENZE = 0.5


def _normiere(werte: list[float]) -> list[float]:
    """Ausschlag über der eigenen Grundlast, robust gegen Ausreißer.

    Median und mittlere absolute Abweichung statt Mittelwert und
    Standardabweichung: ein einziger Lachanfall mit 300 Nachrichten würde
    sonst die Grundlast so weit hochziehen, dass alle anderen Momente
    verschwinden.

    Entscheidend ist aber, *was* die Grundlast einer Reihe überhaupt ist,
    und das hängt davon ab, ob die Reihe läuft oder feuert:

    * **Laufende Reihen** (Chatmenge, Wortdichte) sind fast durchgehend
      belegt. Ihre Grundlast ist der übliche Pegel, und das Signal ist der
      Ausschlag darüber.
    * **Seltene Reihen** (Lachen, Clipruf, Ausraster) sind in den meisten
      Sekunden null. Ihre Grundlast ist die Stille - schon ein einzelner
      Treffer ist das Ereignis.

    Bis hierher wurde für beide der Median der *belegten* Sekunden als
    Grundlast genommen. Bei einer seltenen Reihe steht dort fast immer 1,
    die mittlere Abweichung ist 0, und damit fällt die ganze Reihe auf
    null - jeder einzelne Treffer wird als "völlig normal" weggerechnet.
    Genau daran ist die Auswertung von Stream 2862735566 gescheitert: ohne
    Chat blieben nur seltene Sprachreihen übrig, und die löschten sich
    reihenweise selbst aus. Ergebnis: eine flache Kurve, keine Spitze, kein
    Clip - aus 1549 Sprachsegmenten.
    """
    aktive = [w for w in werte if w > 0]
    if not aktive:
        return [0.0] * len(werte)
    if len(aktive) < 5:
        hoechst = max(aktive)
        return [w / hoechst for w in werte]

    if len(aktive) / len(werte) < DICHTE_GRENZE:
        # Seltene Reihe: der übliche Treffer ist die Einheit. Ein Treffer
        # ergibt 1, ein Dreifachtreffer 3 - und Stille bleibt Stille.
        einheit = statistics.median(aktive)
        return [w / einheit for w in werte]

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
        text = segment.text
        # Ein Sprachsegment ist kein Punkt, sondern eine Strecke. Wo genau
        # im Satz gelacht wurde, verrät der Text nicht - also gilt das
        # Signal für die ganze Dauer des Satzes. Trüge es nur die
        # Anfangssekunde, stünde im Transkriptbetrieb eine Nadel alle sechs
        # Sekunden, und die Glättung darunter zöge sie auf ein Fünftel
        # herunter. Genau so entstand aus 1549 Segmenten eine flache Kurve.
        von = feld(segment.start)
        bis = min(von + SEGMENT_MAX_FELDER,
                  feld(max(segment.start, segment.ende - 0.001)))
        felder = range(von, bis + 1)

        rufe = min(3.0, float(len(re.findall(r"\b[A-ZÄÖÜ]{3,}\b", text))
                              + text.count("!")))
        dichte = len(text.split()) / segment.dauer if segment.dauer > 0 else 0.0
        treffer = {name: _treffer(muster, text)
                   for name, muster in sprach_muster.items() if name in roh}

        for i in felder:
            for name, anzahl in treffer.items():
                roh[name][i] += anzahl
            roh["sprache_ruf"][i] += rufe
            roh["wortdichte"][i] += dichte

    reihen = {name: _glaetten(_normiere(werte)) for name, werte in roh.items()}
    gesamt = [0.0] * laenge
    for name, werte in reihen.items():
        gewicht = GEWICHTE[name]
        for i, wert in enumerate(werte):
            gesamt[i] += wert * gewicht

    return Signalkurve(aufloesung=aufloesung, laenge=laenge,
                       reihen=reihen, gesamt=gesamt,
                       hat_chat=bool(stream.chat),
                       hat_sprache=bool(stream.segmente))


# --------------------------------------------------------------------------- #
# Spitzen finden
# --------------------------------------------------------------------------- #
def spitzen(kurve_: Signalkurve, schwelle: float | None = None,
            mindestabstand: float = 25.0, hoechstens: int = 60) -> list[Spitze]:
    """Die stärksten Momente, mit Mindestabstand zueinander.

    Der Mindestabstand verhindert, dass ein einziger langer Lachanfall
    fünfmal als eigener Clip auftaucht. Er ist bewusst kleiner als die
    kürzeste sinnvolle Clip-Länge nicht - sondern größer: zwei Clips, die
    sich zur Hälfte überlappen, sind für den Zuschauer derselbe Clip.

    `schwelle=None` heißt: an den vorhandenen Sensoren ausrichten. Eine
    feste Zahl wäre eine Aussage über den Stream, ist aber in Wahrheit eine
    über die Datenlage - ohne Chat liegt dieselbe Kurve halb so hoch.
    """
    werte = kurve_.gesamt
    if not werte:
        return []
    if schwelle is None:
        schwelle = SPITZENSCHWELLE * kurve_.bezug

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
