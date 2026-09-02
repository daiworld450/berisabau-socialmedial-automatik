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

# Ohne Transkript sind zwei der sechs Teilnoten unbekannt und stehen auf
# einem neutralen Wert. Dadurch ist die erreichbare Höchstpunktzahl
# gedeckelt: dieselben Momente liegen im Chat-Modus messbar tiefer, ohne
# schlechter zu sein. An einem Vergleichslauf über dieselben sieben
# Momente betrug der Abstand im Mittel 7,3 Punkte (Einzelwerte 2 bis 12).
# Die Schwelle wandert deshalb mit, sonst bedeutet "65" hier faktisch 72.
#
# Der Wert stammt aus einem synthetischen Stream und ist eine erste
# Eichung, keine Konstante - an echten Streams gehört er nachgemessen.
SCHWELLE_OHNE_TRANSKRIPT = 58

# Ausschlag, ab dem ein Moment als "so stark wie es wird" gilt. Über den
# eigenen Streamschnitt hinaus ist das Sechsfache der robusten Streuung ein
# sehr seltener Ausschlag - alles darüber bringt keine Zusatzpunkte mehr.
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


def _note_unterhaltung(kandidat: Kandidat) -> float:
    staerke = min(1.0, kandidat.staerke / STAERKE_DECKEL)
    gefuehl = sum(kandidat.anteile.get(reihe, 0.0) for reihe in _GEFUEHL)
    gefuehl = min(1.0, gefuehl / 4.0)
    return max(0.0, min(1.0, staerke * 0.6 + gefuehl * 0.4))


def _note_watchtime(kandidat: Kandidat) -> float:
    dauer = kandidat.dauer
    if MIN_NORMAL <= dauer <= ZIEL_MAX:
        laenge = 1.0
    elif dauer < MIN_NORMAL:
        laenge = 0.55 + 0.45 * (dauer - 7.0) / (MIN_NORMAL - 7.0)
    else:
        laenge = max(0.35, 1.0 - (dauer - ZIEL_MAX) / 30.0)

    woerter = len(kandidat.text.split())
    if kandidat.segmente:
        dichte = min(1.0, (woerter / dauer) / 3.0) if dauer > 0 else 0.0
    else:
        dichte = 0.5        # ohne Transkript unbekannt, siehe _note_hook

    # Rest-Stille nach den Auslassungen: was übrig bleibt, kostet.
    weg = sum(bis - von for von, bis in kandidat.auslassungen)
    sauber = 1.0 if kandidat.roh_dauer <= 0 else max(
        0.4, 1.0 - max(0.0, (weg / kandidat.roh_dauer) - 0.25))

    return max(0.0, min(1.0, laenge * 0.45 + dichte * 0.30 + sauber * 0.25))


def _note_share(kandidat: Kandidat, kategorie: str) -> float:
    neigung = kat.KATEGORIEN[kategorie].share
    ueberraschung = min(1.0, (kandidat.anteile.get("sprache_ueberraschung", 0.0)
                              + kandidat.anteile.get("chat_schock", 0.0)) / 2.5)
    clipruf = min(1.0, kandidat.anteile.get("chat_clipruf", 0.0) / 2.0)
    zitierbar = min(1.0, len(_ZITIERBAR.findall(kandidat.text)) / 3.0)
    return max(0.0, min(1.0, neigung * 0.55 + ueberraschung * 0.20
                        + clipruf * 0.15 + zitierbar * 0.10))


def _note_kommentar(kandidat: Kandidat, kategorie: str) -> float:
    neigung = kat.KATEGORIEN[kategorie].kommentar
    streit = min(1.0, (kandidat.anteile.get("chat_streit", 0.0)
                       + kandidat.anteile.get("sprache_meinung", 0.0)) / 2.0)
    frage = 1.0 if "?" in kandidat.text else 0.0
    return max(0.0, min(1.0, neigung * 0.6 + streit * 0.3 + frage * 0.1))


def _note_follower(kandidat: Kandidat, kategorie: str, sicherheit: float) -> float:
    neigung = kat.KATEGORIEN[kategorie].follower
    person = min(1.0, (kandidat.anteile.get("sprache_story", 0.0)
                       + kandidat.anteile.get("sprache_chatbezug", 0.0)) / 2.0)
    # Ein Clip, dessen Kategorie eindeutig ist, passt in ein Serienformat -
    # und Serienformate sind das, wofür Menschen folgen.
    return max(0.0, min(1.0, neigung * 0.55 + person * 0.25 + sicherheit * 0.20))


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
        "unterhaltung": _note_unterhaltung(kandidat),
        "watchtime": _note_watchtime(kandidat),
        "share": _note_share(kandidat, kategorie),
        "kommentar": _note_kommentar(kandidat, kategorie),
        "follower": _note_follower(kandidat, kategorie, sicherheit),
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
