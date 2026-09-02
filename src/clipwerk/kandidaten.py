"""Aus Spitzen werden Clip-Fenster: Anfang, Ende, Auslassungen.

Drei Entscheidungen fallen hier, und alle drei entscheiden über die
Completion Rate:

1. **Wo fängt der Clip an?** Nicht dort, wo der Streamer Luft holt,
   sondern an einem Satzanfang, der für sich allein trägt. Deshalb wird
   der Start nicht gerechnet, sondern unter mehreren Satzanfängen
   *ausgewählt* - der mit dem stärksten Einstieg gewinnt (Abschnitt 4).
2. **Wo hört er auf?** Wenn die Reaktion abgeklungen ist, nicht wenn die
   Wunschlänge erreicht ist. Ein Clip, der nach dem Lacher noch acht
   Sekunden weiterläuft, verliert genau dort seine Zuschauer.
3. **Was fliegt raus?** Jede Lücke ohne Sprache über 1,2 Sekunden. Das
   sind Ladezeiten, Denkpausen und Menüs - zusammen oft ein Drittel der
   Rohlänge (Abschnitt 3).

Die Netto-Dauer nach den Auslassungen ist die Länge, die der Zuschauer
sieht. Alle Längenregeln gelten für sie, nicht für den Rohausschnitt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .quellen import Segment, Stream
from .signale import GEWICHTE, Signalkurve, Spitze
from .verlauf import STOPP

# Längen nach Abschnitt 3 der Betriebsanweisung.
MIN_KURZ = 7.0        # nur für sehr kurze, sehr starke Momente
MIN_NORMAL = 15.0     # Untergrenze im Regelfall
ZIEL_MAX = 45.0       # Obergrenze im Regelfall
HART_MAX = 60.0       # nur wenn Kontext oder Erzählung es verlangen

# Wie weit vor und nach dem Höhepunkt überhaupt gesucht wird.
VORLAUF_MAX = 30.0
VORLAUF_MIN = 1.5
NACHLAUF_MAX = 25.0

# Lücke ohne Sprache, ab der geschnitten wird.
STILLE = 1.2

# Wie lange der Chat braucht, um auf etwas zu reagieren - lesen, tippen,
# absenden. Nur im Chat-Modus gebraucht, wo keine Sprache verrät, wann der
# Moment wirklich war. Drei bis vier Sekunden decken sich mit dem, was man
# in Mitschnitten sieht: die erste Welle kommt schnell, die Masse danach.
CHAT_VERZUG = 3.5

# Kategorien, denen die 60 Sekunden zustehen, weil ohne Aufbau nichts bleibt.
ERZAEHLEND = {"STORY", "CONTROVERSIAL", "HOT TAKE"}

# Rückfall, wenn kein Lexikon übergeben wird. Die gepflegte Liste steht in
# content/clip_lexikon.json.
_FUELLWOERTER = {"ähm", "ähh", "öhm", "hmm", "also", "halt", "irgendwie",
                 "quasi", "sozusagen", "gleich", "kurz", "mal", "jetzt",
                 "schon", "eben", "grade", "gerade"}

_EINSTIEG = re.compile(
    r"^(und|also|ähm|äh|öhm|ja|so|dann|aber|weil|oder|halt|ne|nee)\b", re.I)


@dataclass
class Kandidat:
    start: float
    ende: float
    hoehepunkt: float
    staerke: float
    anteile: dict[str, float]
    segmente: list[Segment] = field(default_factory=list)
    auslassungen: list[tuple[float, float]] = field(default_factory=list)

    @property
    def roh_dauer(self) -> float:
        return max(0.0, self.ende - self.start)

    @property
    def dauer(self) -> float:
        """Was der Zuschauer sieht: Rohlänge minus herausgeschnittene Stille."""
        weg = sum(bis - von for von, bis in self.auslassungen)
        return max(0.0, self.roh_dauer - weg)

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.segmente if s.text.strip())

    def clipzeit(self, quelle: float) -> float:
        """Zeitpunkt im Quellvideo -> Zeitpunkt im fertigen Clip.

        Jede Auslassung vor diesem Punkt zieht die Zeitachse zusammen.
        Ohne diese Umrechnung stehen Untertitel und Schnittmarken im
        fertigen Video um genau die herausgeschnittene Stille daneben.
        """
        zeit = max(0.0, min(quelle, self.ende) - self.start)
        for von, bis in self.auslassungen:
            if bis <= quelle:
                zeit -= (bis - von)
            elif von < quelle < bis:
                zeit -= (quelle - von)
        return round(max(0.0, zeit), 3)

    def in_auslassung(self, quelle: float) -> bool:
        return any(von <= quelle < bis for von, bis in self.auslassungen)

    @property
    def hoehepunkt_relativ(self) -> float:
        """Position des Höhepunkts im fertigen Clip, 0..1."""
        if self.roh_dauer <= 0:
            return 0.0
        return min(1.0, max(0.0, (self.hoehepunkt - self.start) / self.roh_dauer))


# --------------------------------------------------------------------------- #
# Hilfen
# --------------------------------------------------------------------------- #
def _segmente_im_fenster(stream: Stream, start: float, ende: float) -> list[Segment]:
    return [s for s in stream.segmente if s.ende > start and s.start < ende]


def _einstiegsguete(segment: Segment, kurve: Signalkurve) -> float:
    """Wie stark trägt dieser Satz die ersten zwei Sekunden?

    Belohnt wird, was sofort Spannung erzeugt: eine Frage, ein Ausruf, ein
    Satz mit Inhalt. Bestraft wird der klassische Anfang aus dem Nichts -
    "und ähm also dann" - und ein Satz, der so lang ist, dass in zwei
    Sekunden noch gar nichts gesagt wurde.
    """
    text = segment.text.strip()
    if not text:
        return 0.0
    note = 0.35
    if text.endswith("?") or "?" in text[:60]:
        note += 0.25
    if "!" in text or re.search(r"\b[A-ZÄÖÜ]{3,}\b", text):
        note += 0.20
    if _EINSTIEG.match(text):
        note -= 0.30
    if _ist_fueller(segment, _FUELLWOERTER):
        note -= 0.45
    woerter = len(text.split())
    if woerter >= 4:
        note += 0.15
    if segment.dauer > 0 and woerter / segment.dauer >= 2.5:
        note += 0.15
    # Was direkt beim Einstieg schon im Chat passiert, zieht ebenfalls.
    note += min(0.25, kurve.spitzenwert("chat_menge", segment.start,
                                        segment.start + 2.0) * 0.08)
    return max(0.0, min(1.0, note))


def _ist_fueller(segment: Segment, fuellwoerter: set[str]) -> bool:
    """Ein Satz, der nichts sagt: nur Füllwörter und Funktionswörter.

    Solche Sätze am Anfang kosten den Hook, am Ende die Completion Rate.
    Beides ist teurer als die zwei Sekunden, die sie an Länge bringen.
    """
    woerter = [re.sub(r"[^\wäöüßÄÖÜ]+", "", w).lower()
               for w in segment.text.split()]
    woerter = [w for w in woerter if w]
    if not woerter:
        return True
    # Funktionswörter zählen nicht als Inhalt: "also ähm ich weiß nicht"
    # besteht ausschließlich daraus und sagt trotzdem nichts.
    inhalt = [w for w in woerter
              if len(w) > 3 and w not in fuellwoerter and w not in STOPP]
    return len(inhalt) < 2


def _anteile(kurve: Signalkurve, start: float, ende: float) -> dict[str, float]:
    """Signalanteile über das **ganze** Fenster, nicht nur im Höhepunkt.

    Der Chat hinkt der Sprache um Sekunden hinterher - er reagiert ja erst.
    Wer die Anteile nur in der Spitzensekunde abliest, sieht deshalb den
    Chat und nie den Satz, der ihn ausgelöst hat. Genau daran ist die erste
    Fassung dieses Moduls gescheitert: alles wurde "CHAT MOMENT".
    """
    anteile = {}
    for name, gewicht in GEWICHTE.items():
        wert = kurve.spitzenwert(name, start, ende) * gewicht
        if wert > 0:
            anteile[name] = round(wert, 3)
    return anteile


def _auslassungen(segmente: list[Segment], start: float, ende: float
                  ) -> list[tuple[float, float]]:
    """Lücken ohne Sprache innerhalb des Fensters."""
    luecken: list[tuple[float, float]] = []
    marke = start
    for segment in segmente:
        if segment.start - marke > STILLE:
            luecken.append((round(marke + 0.2, 2), round(segment.start - 0.2, 2)))
        marke = max(marke, segment.ende)
    if ende - marke > STILLE:
        luecken.append((round(marke + 0.2, 2), round(ende, 2)))
    return luecken


# --------------------------------------------------------------------------- #
# Fenster bauen
# --------------------------------------------------------------------------- #
def _ende_waehlen(stream: Stream, kurve: Signalkurve, spitze: Spitze) -> float:
    """Bis die Reaktion abgeklungen ist, dann bis zum Satzende."""
    schwelle = spitze.staerke * 0.35
    ende = spitze.sekunde + 2.0
    schritt = kurve.aufloesung
    while ende < spitze.sekunde + NACHLAUF_MAX:
        if kurve.spitzenwert_gesamt(ende, ende + 2.0) < schwelle:
            break
        ende += schritt

    # Nie mitten im Wort aufhören.
    for segment in stream.segmente:
        if segment.start <= ende < segment.ende:
            ende = min(segment.ende, spitze.sekunde + NACHLAUF_MAX)
            break
    return ende


def _start_waehlen(stream: Stream, kurve: Signalkurve, spitze: Spitze,
                   ende: float, erzaehlend: bool) -> float:
    """Den besten Satzanfang vor dem Höhepunkt auswählen.

    Bewertet wird Einstiegsgüte gegen Länge: ein starker Satz weiter vorn
    darf gewinnen, aber nur solange der Clip in der Zielspanne bleibt.
    """
    frueheste = max(0.0, spitze.sekunde - VORLAUF_MAX)
    grenze = HART_MAX if erzaehlend else ZIEL_MAX

    anfaenge = [s for s in stream.segmente
                if frueheste <= s.start <= spitze.sekunde - VORLAUF_MIN]
    if not anfaenge:
        return max(0.0, min(spitze.sekunde - 3.0, ende - MIN_KURZ))

    bester, beste_note = anfaenge[-1].start, -9.9
    for segment in anfaenge:
        laenge = ende - segment.start
        if laenge < MIN_KURZ:
            continue
        note = _einstiegsguete(segment, kurve)
        # Längenstrafe: alles über der Zielspanne kostet spürbar, alles
        # unter 15 Sekunden nur dann, wenn der Moment nicht sehr stark ist.
        if laenge > grenze:
            note -= (laenge - grenze) * 0.06
        elif laenge > ZIEL_MAX:
            note -= (laenge - ZIEL_MAX) * 0.02
        if laenge < MIN_NORMAL:
            note -= 0.25 if spitze.staerke < 3.0 else 0.05
        # Aufbau ist gut, Vorrede nicht: 6-20 Sekunden vor dem Höhepunkt
        # ist der Bereich, in dem ein Clip Kontext bekommt.
        abstand = spitze.sekunde - segment.start
        if 6.0 <= abstand <= 20.0:
            note += 0.10
        if note > beste_note:
            bester, beste_note = segment.start, note
    return bester


def _beschneiden(segmente: list[Segment], hoehepunkt: float,
                 fuellwoerter: set[str]) -> list[Segment]:
    """Führende und nachlaufende Füllsätze wegnehmen.

    Nie über den Höhepunkt hinweg - was dort steht, ist der Clip.
    """
    while len(segmente) > 1 and segmente[0].ende < hoehepunkt - 1.0 \
            and _ist_fueller(segmente[0], fuellwoerter):
        segmente = segmente[1:]
    while len(segmente) > 1 and segmente[-1].start > hoehepunkt + 1.0 \
            and _ist_fueller(segmente[-1], fuellwoerter):
        segmente = segmente[:-1]
    return segmente


def _ohne_sprache(stream: Stream, kurve: Signalkurve, spitze: Spitze,
                  erzaehlend: bool) -> Kandidat | None:
    """Fenster allein aus der Chatkurve, wenn kein Transkript vorliegt.

    Der Chat reagiert, er handelt nicht - seine Spitze liegt also nach dem
    Moment, nicht auf ihm. Deshalb wird hier bewusst weiter vorn angesetzt
    als bei einem Fenster mit Sprache: der Auslöser liegt vor dem Ausschlag.

    Ohne Sprache gibt es keine Satzgrenzen und keine erkennbare Stille -
    also auch keine Auslassungen. Der Ausschnitt bleibt am Stück, und der
    Zuschnitt ist gröber. Das ist der Preis dafür, in Minuten statt in
    Stunden ein Ergebnis zu haben.
    """
    # Der Chat-Ausschlag ist nicht der Moment, sondern die Antwort darauf:
    # lesen, tippen, absenden. Das Ereignis liegt davor. Wer den Ausschlag
    # als Pointe einträgt, legt sie ans Clipende - und die Bewertung
    # bestraft dann eine Verzögerung, die gar nicht im Video steckt.
    ereignis = max(0.0, spitze.sekunde - CHAT_VERZUG)
    vorlauf = 14.0 if erzaehlend else 9.0
    start = max(0.0, ereignis - vorlauf)

    schwelle = spitze.staerke * 0.4
    ende = spitze.sekunde + 2.0
    while ende < spitze.sekunde + NACHLAUF_MAX:
        if kurve.spitzenwert_gesamt(ende, ende + 2.0) < schwelle:
            break
        ende += kurve.aufloesung

    grenze = HART_MAX if erzaehlend else ZIEL_MAX
    ende = min(ende, start + grenze, stream.laenge)
    if ende - start < MIN_KURZ:
        ende = min(stream.laenge, start + MIN_KURZ)
    if ende - start < MIN_KURZ:
        return None

    kandidat = Kandidat(start=round(start, 2), ende=round(ende, 2),
                        hoehepunkt=min(ereignis, ende - 0.5),
                        staerke=spitze.staerke, anteile={})
    kandidat.anteile = _anteile(kurve, kandidat.start, kandidat.ende)
    return kandidat


def baue(stream: Stream, kurve: Signalkurve, spitze: Spitze,
         kategorie: str = "", fuellwoerter: set[str] | None = None
         ) -> Kandidat | None:
    fuellwoerter = fuellwoerter or _FUELLWOERTER
    erzaehlend = kategorie in ERZAEHLEND
    if stream.nur_chat:
        return _ohne_sprache(stream, kurve, spitze, erzaehlend)
    ende = _ende_waehlen(stream, kurve, spitze)
    start = _start_waehlen(stream, kurve, spitze, ende, erzaehlend)
    if ende - start < MIN_KURZ:
        ende = min(stream.laenge, start + MIN_KURZ)

    segmente = _beschneiden(_segmente_im_fenster(stream, start, ende),
                           spitze.sekunde, fuellwoerter)
    if not segmente:
        return None
    start = max(start, segmente[0].start)
    ende = min(ende, max(segmente[-1].ende, spitze.sekunde + 1.0))
    luecken = _auslassungen(segmente, start, ende)
    kandidat = Kandidat(start=round(start, 2), ende=round(ende, 2),
                        hoehepunkt=spitze.sekunde, staerke=spitze.staerke,
                        anteile=dict(spitze.anteile), segmente=segmente,
                        auslassungen=luecken)

    # Zu lang: vorne kürzen, nie hinten - die Pointe steht am Ende.
    grenze = HART_MAX if erzaehlend else ZIEL_MAX
    while kandidat.dauer > grenze and len(kandidat.segmente) > 1:
        naechster = kandidat.segmente[1].start
        if spitze.sekunde - naechster < 3.0:
            break
        kandidat.start = round(naechster, 2)
        kandidat.segmente = kandidat.segmente[1:]
        kandidat.auslassungen = _auslassungen(kandidat.segmente,
                                              kandidat.start, kandidat.ende)

    if kandidat.dauer < MIN_KURZ or not kandidat.segmente:
        return None
    kandidat.anteile = _anteile(kurve, kandidat.start, kandidat.ende)
    return kandidat


def entdoppeln(kandidaten: list[Kandidat], hoechste_ueberlappung: float = 0.4
               ) -> list[Kandidat]:
    """Zwei Fenster, die sich stark überlappen, sind derselbe Clip.

    Es gewinnt das stärkere; das schwächere fällt weg. Ohne diesen Schritt
    entstehen aus einem langen Lachanfall drei fast gleiche Clips, und der
    Kanal veröffentlicht dreimal dasselbe.
    """
    behalten: list[Kandidat] = []
    for kandidat in sorted(kandidaten, key=lambda k: -k.staerke):
        doppelt = False
        for fest in behalten:
            ueberschneidung = (min(kandidat.ende, fest.ende)
                               - max(kandidat.start, fest.start))
            if ueberschneidung <= 0:
                continue
            anteil = ueberschneidung / min(kandidat.roh_dauer, fest.roh_dauer)
            if anteil > hoechste_ueberlappung:
                doppelt = True
                break
        if not doppelt:
            behalten.append(kandidat)
    return sorted(behalten, key=lambda k: k.start)
