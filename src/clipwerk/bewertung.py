"""Der 100-Punkte-Maßstab aus Abschnitt 2 der Betriebsanweisung.

Hook 25 · Unterhaltung 20 · Watchtime 20 · Share 15 · Kommentar 10 ·
Follower 10. Jede Teilnote wird zuerst als Wert zwischen 0 und 1 gerechnet
und dann mit ihrer Punktzahl multipliziert. Dadurch bleibt sichtbar, *warum*
ein Clip 71 statt 84 Punkte hat - und nicht nur, dass er es hat.

Zwei Regeln, die den Rest tragen:

* **Unter 65 Punkten wird verworfen.** Nicht "später vielleicht" - verworfen.
  Ein mittelmäßiger Clip kostet Reichweite für die nächsten drei guten.
* **Ab 80 Punkten höchste Priorität**, das heißt: zuerst veröffentlicht, in
  die beste Zeitschiene, und auf allen drei Plattformen.

Die Faktoren aus `lernkurve.py` verschieben Teilnoten je Kategorie, sobald
echte Zahlen vorliegen. Sie sind gedeckelt (siehe dort), damit gelernte
Vorlieben die Messung verschieben, aber nie ersetzen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import kategorien as kat
from .kandidaten import MIN_NORMAL, ZIEL_MAX, Kandidat
from .signale import Signalkurve

HOECHSTPUNKTE = {
    "hook": 25.0,
    "unterhaltung": 20.0,
    "watchtime": 20.0,
    "share": 15.0,
    "kommentar": 10.0,
    "follower": 10.0,
}

SCHWELLE_VERWERFEN = 65
SCHWELLE_PRIORITAET = 80

# Die Schwelle wandert mit der Betriebsart, weil die Punktzahl es tut.
#
# `_mittel` lässt Bestandteile, die in einem Stream gar nicht messbar sind,
# herausfallen statt sie als Null zu werten. Das ist richtig - eine fehlende
# Messung ist kein schlechter Wert - hat aber eine Folge: was übrig bleibt,
# trägt volles Gewicht. Im Chatbetrieb sind das vor allem die
# Kategorieneigungen und der Chatausschlag, und beide sind großzügig. Ohne
# Gegengewicht bekäme derselbe Moment ohne Transkript *mehr* Punkte als mit.
#
# Nachgemessen an fünf synthetischen Streams mit unterschiedlich lebhaftem
# Chat (Reaktionswelle 6 bis 30 Nachrichten, Grundlast 0,8 bis 3 s je
# Nachricht), jeweils derselbe Stream in allen drei Betriebsarten, Abstand
# über die gemeinsam gefundenen Momente:
#
#   nur Chat        +5 bis +11 Punkte über dem Vollbetrieb  (Mittel  +8,8)
#   nur Transkript  -11 bis +0,5 Punkte darunter            (Mittel  -4,1)
#
# Die Streuung ist groß, weil sie davon abhängt, wie laut der Chat ist -
# also von etwas, das sich von Stream zu Stream ändert. Die Zahlen sind
# eine erste Eichung an erfundenem Material, keine Konstanten. An echten
# Streams gehören sie nachgemessen; `tests/test_clipwerk.py` hält den
# Vergleich als Test fest, damit eine Verschiebung auffällt.
#
# Vorgeschichte: bis zum 02.09.2026 stand hier eine einzelne abgesenkte
# Schwelle von 58 für den Chatbetrieb. Sie war gegen eine Fassung gemessen,
# die fehlende Messungen als Null wertete. Seit `_mittel` das nicht mehr
# tut, hätte sie die Korrektur doppelt gezählt - in die falsche Richtung.
SCHWELLE_NUR_CHAT = 73
SCHWELLE_NUR_TRANSKRIPT = 61


def schwelle_fuer(stream) -> int:
    """Die Punktschwelle, die für diesen Stream gilt."""
    if not stream.segmente:
        return SCHWELLE_NUR_CHAT
    if not stream.chat:
        return SCHWELLE_NUR_TRANSKRIPT
    return SCHWELLE_VERWERFEN

# Ausschlag, ab dem ein Moment als "so stark wie es wird" gilt. Über den
# eigenen Streamschnitt hinaus ist das Sechsfache der robusten Streuung ein
# sehr seltener Ausschlag - alles darüber bringt keine Zusatzpunkte mehr.
#
# Der Wert gilt für einen Stream mit vollem Sensorsatz. `kandidat.staerke`
# ist eine Summe über die Signalreihen: fehlt der Chat, fehlt gut die
# Hälfte des Gewichts, und derselbe Moment landet bei der halben Zahl. Der
# Deckel wandert deshalb mit `Signalkurve.bezug` mit - sonst misst die
# Unterhaltungsnote nicht den Moment, sondern die Anzahl der Sensoren.
STAERKE_DECKEL = 6.0

_GEFUEHL = ("chat_lachen", "chat_schock", "chat_wut", "chat_peinlich",
            "sprache_lachen", "sprache_wut", "sprache_ueberraschung",
            "sprache_fail", "sprache_win")
_ZITIERBAR = re.compile(r"\b(nie|niemals|immer|keiner|jeder|nichts|alles|"
                        r"komplett|absolut|ehrlich|wirklich)\b", re.I)


@dataclass
class Bewertung:
    hook: float
    unterhaltung: float
    watchtime: float
    share: float
    kommentar: float
    follower: float
    kategorie: str
    sicherheit: float
    begruendung: str = ""
    teilnoten: dict[str, float] = field(default_factory=dict)

    @property
    def punkte(self) -> int:
        return int(round(self.hook + self.unterhaltung + self.watchtime
                         + self.share + self.kommentar + self.follower))

    @property
    def bestanden(self) -> bool:
        return self.punkte >= SCHWELLE_VERWERFEN

    @property
    def vorrang(self) -> bool:
        return self.punkte >= SCHWELLE_PRIORITAET


# --------------------------------------------------------------------------- #
# Teilnoten
# --------------------------------------------------------------------------- #
def _note_hook(kandidat: Kandidat, kurve: Signalkurve) -> float:
    from .kandidaten import _einstiegsguete

    erstes = kandidat.segmente[0] if kandidat.segmente else None
    # Ohne Transkript lässt sich der Einstiegssatz nicht beurteilen. Dann
    # steht hier bewusst ein neutraler Wert statt einer Null: der Einstieg
    # ist unbekannt, nicht schlecht. Eine Null würde jeden Chat-Clip unter
    # die Schwelle drücken, obwohl über ihn nur weniger bekannt ist.
    guete = _einstiegsguete(erstes, kurve) if erstes else 0.5

    # Was in den ersten zwei Sekunden schon passiert, gemessen am Höhepunkt
    # des Clips selbst. Ein Clip, der bei null anfängt, verliert hier.
    hoehe = max(0.001, kurve.spitzenwert_gesamt(kandidat.start, kandidat.ende))
    sofort = min(1.0, kurve.spitzenwert_gesamt(kandidat.start,
                                               kandidat.start + 2.0) / hoehe)

    # Wann kommt die Auflösung? Zu früh heißt: kein Grund weiterzuschauen.
    # Zu spät heißt: die meisten sind vorher weg.
    lage = kandidat.hoehepunkt_relativ
    if lage <= 0.15:
        takt = 0.55
    elif lage <= 0.75:
        takt = 1.0 - abs(lage - 0.45) * 0.6
    else:
        takt = max(0.35, 1.0 - (lage - 0.75) * 2.2)

    return max(0.0, min(1.0, guete * 0.40 + sofort * 0.25 + takt * 0.35))


def _mittel(teile: list[tuple[float, float, bool]]) -> float:
    """Gewichteter Mittelwert über die Bestandteile, die messbar sind.

    Ein Bestandteil, den es in diesem Stream gar nicht gibt - der Clipruf
    ohne Chat, die Wortdichte ohne Transkript - zählt nicht als Null,
    sondern fällt heraus; sein Gewicht verteilt sich auf den Rest.

    Der Unterschied ist der zwischen „gemessen und schlecht" und „nicht
    gemessen". Als Null gewertet, verlor jeder Clip aus einem Stream ohne
    Chat rund zehn Punkte für etwas, das nicht am Clip lag.
    """
    gewicht = sum(g for _, g, messbar in teile if messbar)
    if gewicht <= 0:
        return 0.0
    summe = sum(wert * g for wert, g, messbar in teile if messbar)
    return max(0.0, min(1.0, summe / gewicht))


def _anteil(kandidat: Kandidat, kurve: Signalkurve, reihen: tuple[str, ...],
            je_reihe: float) -> float:
    """Signalanteile über die messbaren Reihen, auf 0..1 gebracht.

    `je_reihe` ist der Ausschlag, ab dem eine einzelne Reihe als voll
    ausgeschlagen gilt. Der Teiler wächst mit der Zahl der Reihen, die es
    in diesem Stream gibt - sonst wäre der Höchstwert ohne Chat gar nicht
    erreichbar.
    """
    messbar = [r for r in reihen if kurve.hat(r)]
    if not messbar:
        return 0.0
    summe = sum(kandidat.anteile.get(r, 0.0) for r in messbar)
    return min(1.0, summe / (je_reihe * len(messbar)))


def _note_unterhaltung(kandidat: Kandidat, kurve: Signalkurve) -> float:
    # Zwei Bezugspunkte, der kleinere gilt: die feste Obergrenze aus der
    # Betriebsanweisung, mit dem Sensorsatz mitskaliert - und das Niveau,
    # das dieser Stream selbst überhaupt erreicht. Ohne den zweiten misst
    # die Note bei fehlendem Chat weiter die Datenlage; ohne den ersten
    # würde ein sehr starker Stream sich selbst kleinrechnen.
    deckel = max(0.5, min(STAERKE_DECKEL * kurve.bezug, kurve.spitzenniveau))
    staerke = min(1.0, kandidat.staerke / deckel)
    gefuehl = _anteil(kandidat, kurve, _GEFUEHL, 4.0 / len(_GEFUEHL))
    return _mittel([(staerke, 0.6, True), (gefuehl, 0.4, True)])


def _note_watchtime(kandidat: Kandidat) -> float:
    dauer = kandidat.dauer
    if MIN_NORMAL <= dauer <= ZIEL_MAX:
        laenge = 1.0
    elif dauer < MIN_NORMAL:
        laenge = 0.55 + 0.45 * (dauer - 7.0) / (MIN_NORMAL - 7.0)
    else:
        laenge = max(0.35, 1.0 - (dauer - ZIEL_MAX) / 30.0)

    woerter = len(kandidat.text.split())
    dichte = (min(1.0, (woerter / dauer) / 3.0)
              if kandidat.segmente and dauer > 0 else 0.0)

    # Rest-Stille nach den Auslassungen: was übrig bleibt, kostet.
    weg = sum(bis - von for von, bis in kandidat.auslassungen)
    sauber = 1.0 if kandidat.roh_dauer <= 0 else max(
        0.4, 1.0 - max(0.0, (weg / kandidat.roh_dauer) - 0.25))

    return _mittel([
        (laenge, 0.45, True),
        (dichte, 0.30, bool(kandidat.segmente)),
        (sauber, 0.25, True),
    ])


def _note_share(kandidat: Kandidat, kategorie: str, kurve: Signalkurve) -> float:
    neigung = kat.KATEGORIEN[kategorie].share
    ueberraschung = _anteil(kandidat, kurve,
                            ("sprache_ueberraschung", "chat_schock"), 1.25)
    clipruf = _anteil(kandidat, kurve, ("chat_clipruf",), 2.0)
    zitierbar = min(1.0, len(_ZITIERBAR.findall(kandidat.text)) / 3.0)
    return _mittel([
        (neigung, 0.55, True),
        (ueberraschung, 0.20, kurve.hat_sprache or kurve.hat_chat),
        (clipruf, 0.15, kurve.hat_chat),
        (zitierbar, 0.10, bool(kandidat.segmente)),
    ])


def _note_kommentar(kandidat: Kandidat, kategorie: str,
                    kurve: Signalkurve) -> float:
    neigung = kat.KATEGORIEN[kategorie].kommentar
    streit = _anteil(kandidat, kurve, ("chat_streit", "sprache_meinung"), 1.0)
    frage = 1.0 if "?" in kandidat.text else 0.0
    return _mittel([
        (neigung, 0.6, True),
        (streit, 0.3, True),
        (frage, 0.1, bool(kandidat.segmente)),
    ])


def _note_follower(kandidat: Kandidat, kategorie: str, sicherheit: float,
                   kurve: Signalkurve) -> float:
    neigung = kat.KATEGORIEN[kategorie].follower
    person = _anteil(kandidat, kurve,
                     ("sprache_story", "sprache_chatbezug"), 1.0)
    # Ein Clip, dessen Kategorie eindeutig ist, passt in ein Serienformat -
    # und Serienformate sind das, wofür Menschen folgen.
    return _mittel([
        (neigung, 0.55, True),
        (person, 0.25, kurve.hat_sprache),
        (sicherheit, 0.20, True),
    ])


# --------------------------------------------------------------------------- #
# Begründung
# --------------------------------------------------------------------------- #
_KLARTEXT = {
    "chat_menge": "der Chat zieht spürbar an",
    "chat_lachen": "Lach-Emotes brechen aus",
    "chat_schock": "der Chat ist überrascht",
    "chat_wut": "der Chat reagiert auf den Ausraster",
    "chat_peinlich": "Fremdscham im Chat",
    "chat_clipruf": "Zuschauer fordern selbst einen Clip",
    "chat_streit": "der Chat widerspricht",
    "chat_hype": "Hype im Chat",
    "sprache_lachen": "er lacht selbst",
    "sprache_wut": "er rastet aus",
    "sprache_ueberraschung": "er ist sichtbar überrascht",
    "sprache_meinung": "er bezieht klar Stellung",
    "sprache_story": "er erzählt eine Geschichte",
    "sprache_spannung": "er baut Spannung auf",
    "sprache_fail": "es geht schief",
    "sprache_win": "es geht auf",
    "sprache_peinlich": "ihm ist es unangenehm",
    "sprache_chatbezug": "er spricht den Chat direkt an",
    "sprache_reaktion": "er reagiert auf etwas",
    "sprache_ruf": "er wird laut",
    "wortdichte": "dicht gesprochen, keine Leerlaufzeit",
}


def _begruendung(kandidat: Kandidat, note: Bewertung) -> str:
    from .quellen import stempel

    fuehrend = [name for name, _ in
                sorted(kandidat.anteile.items(), key=lambda p: -p[1])[:2]]
    gruende = [_KLARTEXT.get(name, name) for name in fuehrend
               if kandidat.anteile.get(name, 0) > 0]
    kern = " und ".join(gruende) if gruende else "durchgehend Bewegung im Stream"

    lage = int(round(kandidat.hoehepunkt_relativ * 100))
    weg = sum(bis - von for von, bis in kandidat.auslassungen)
    kern = kern[:1].upper() + kern[1:]
    satz = (f"{kern} bei {stempel(kandidat.hoehepunkt)}. "
            f"Die Pointe liegt bei {lage} % der Cliplänge, davor "
            f"{kandidat.hoehepunkt - kandidat.start:.0f} s Aufbau.")
    if weg >= 1.5:
        satz += f" {weg:.0f} s Stille fallen raus."
    if not kandidat.segmente:
        satz += (" Ohne Transkript bewertet – Einstieg und Wortdichte sind "
                 "geschätzt, der Zuschnitt ist grob.")
    elif note.hook >= 20:
        satz += " Der Einstieg trägt ohne Vorwissen."
    elif note.hook < 14:
        satz += " Der Einstieg ist die Schwachstelle – Text-Hook ist Pflicht."
    return satz


# --------------------------------------------------------------------------- #
# Gesamtnote
# --------------------------------------------------------------------------- #
def bewerte(kandidat: Kandidat, kurve: Signalkurve,
            faktoren: dict[str, dict[str, float]] | None = None) -> Bewertung:
    """Alle sechs Teilnoten, Kategorie und Begründung in einem Durchgang."""
    kategorie, sicherheit = kat.bestimme(kandidat.anteile, kandidat.text)
    faktoren = faktoren or {}
    je_kategorie = faktoren.get(kategorie, {})

    roh = {
        "hook": _note_hook(kandidat, kurve),
        "unterhaltung": _note_unterhaltung(kandidat, kurve),
        "watchtime": _note_watchtime(kandidat),
        "share": _note_share(kandidat, kategorie, kurve),
        "kommentar": _note_kommentar(kandidat, kategorie, kurve),
        "follower": _note_follower(kandidat, kategorie, sicherheit, kurve),
    }
    punkte = {}
    for name, wert in roh.items():
        faktor = je_kategorie.get(name, je_kategorie.get("gesamt", 1.0))
        punkte[name] = round(min(1.0, wert * faktor) * HOECHSTPUNKTE[name], 2)

    note = Bewertung(kategorie=kategorie, sicherheit=round(sicherheit, 2),
                     teilnoten={k: round(v, 3) for k, v in roh.items()},
                     **punkte)
    note.begruendung = _begruendung(kandidat, note)
    return note
