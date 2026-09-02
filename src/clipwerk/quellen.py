"""Rohdaten eines Twitch-Streams einlesen und vereinheitlichen.

Ein Stream kommt nie in einem Format. Mal liegt ein Whisper-JSON mit
Wortzeiten vor, mal nur eine SRT-Datei aus dem Auto-Untertitel. Der Chat
kommt entweder als VOD-Export (`content_offset_seconds`), als Zeile aus
einem IRC-Mitschnitt oder als selbstgebaute JSONL. Dieses Modul macht aus
allem dasselbe: eine Liste `Segment` und eine Liste `ChatNachricht`,
beide in **Sekunden ab Streambeginn**.

Alles andere im Clip-Werk rechnet nur noch mit diesen zwei Listen. Wer ein
neues Eingabeformat braucht, erweitert genau hier - und nirgends sonst.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


class QuellenFehler(RuntimeError):
    """Eingabedatei fehlt, ist leer oder in keinem erkannten Format."""


# --------------------------------------------------------------------------- #
# Datenmodell
# --------------------------------------------------------------------------- #
@dataclass
class Wort:
    text: str
    start: float
    ende: float


@dataclass
class Segment:
    """Ein gesprochener Abschnitt mit Zeitstempel."""
    start: float
    ende: float
    text: str
    woerter: list[Wort] = field(default_factory=list)

    @property
    def dauer(self) -> float:
        return max(0.0, self.ende - self.start)

    def wortliste(self) -> list[Wort]:
        """Wortzeiten - notfalls aus der Segmentlänge geschätzt.

        Auto-Untertitel liefern keine Wortzeiten. Für die Untertitel-Ausgabe
        brauchen wir trotzdem welche, sonst stehen 3-7 Wörter ohne Takt auf
        dem Bild. Die Schätzung verteilt die Segmentdauer nach Wortlänge -
        das ist nicht exakt, aber deutlich näher als gleichmäßig zu teilen.
        """
        if self.woerter:
            return self.woerter
        teile = [w for w in self.text.split() if w]
        if not teile:
            return []
        laengen = [len(w) + 1 for w in teile]
        gesamt = sum(laengen)
        zeiten: list[Wort] = []
        laufend = self.start
        for wort, laenge in zip(teile, laengen):
            anteil = self.dauer * (laenge / gesamt)
            zeiten.append(Wort(wort, laufend, laufend + anteil))
            laufend += anteil
        return zeiten


@dataclass
class ChatNachricht:
    sekunde: float
    nutzer: str
    text: str


@dataclass
class Stream:
    """Alles, was das Clip-Werk über einen Stream weiß."""
    stream_id: str
    datum: str
    streamer: str
    spiel: str = ""
    segmente: list[Segment] = field(default_factory=list)
    chat: list[ChatNachricht] = field(default_factory=list)
    video: Path | None = None

    @property
    def nur_chat(self) -> bool:
        """Kein Transkript vorhanden – die Auswahl stützt sich allein auf den Chat."""
        return not self.segmente

    @property
    def laenge(self) -> float:
        enden = [s.ende for s in self.segmente] + [c.sekunde for c in self.chat]
        return max(enden) if enden else 0.0

    def text_zwischen(self, start: float, ende: float) -> str:
        teile = [s.text.strip() for s in self.segmente
                 if s.ende > start and s.start < ende and s.text.strip()]
        return " ".join(teile)

    def chat_zwischen(self, start: float, ende: float) -> list[ChatNachricht]:
        return [c for c in self.chat if start <= c.sekunde < ende]


# --------------------------------------------------------------------------- #
# Zeitstempel
# --------------------------------------------------------------------------- #
_ZEIT = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?")


def sekunden(stempel: str) -> float:
    """'01:02:03,500' oder '02:03.5' -> Sekunden."""
    treffer = _ZEIT.search(stempel.strip())
    if not treffer:
        raise QuellenFehler(f"Zeitstempel nicht lesbar: {stempel!r}")
    stunden, minuten, sek, bruch = treffer.groups()
    wert = int(minuten) * 60 + int(sek)
    if stunden:
        wert += int(stunden) * 3600
    if bruch:
        wert += int(bruch) / (10 ** len(bruch))
    return float(wert)


def stempel(wert: float, mit_stunden: bool = False) -> str:
    """Sekunden -> '1:23' bzw. '1:02:03' für die Ausgabe."""
    wert = max(0.0, wert)
    ganz = int(wert)
    std, rest = divmod(ganz, 3600)
    minute, sek = divmod(rest, 60)
    if std or mit_stunden:
        return f"{std}:{minute:02d}:{sek:02d}"
    return f"{minute}:{sek:02d}"


# --------------------------------------------------------------------------- #
# Transkript
# --------------------------------------------------------------------------- #
def _aus_whisper(daten: dict) -> list[Segment]:
    segmente = []
    for roh in daten.get("segments", []):
        woerter = []
        for w in roh.get("words") or []:
            text = (w.get("word") or w.get("text") or "").strip()
            if not text:
                continue
            woerter.append(Wort(text, float(w.get("start", roh.get("start", 0))),
                                float(w.get("end", roh.get("end", 0)))))
        text = (roh.get("text") or " ".join(w.text for w in woerter)).strip()
        if not text:
            continue
        segmente.append(Segment(float(roh.get("start", 0.0)),
                                float(roh.get("end", 0.0)), text, woerter))
    return segmente


def _aus_untertiteldatei(inhalt: str) -> list[Segment]:
    """SRT und WebVTT teilen sich denselben Aufbau: Zeit --> Zeit, dann Text."""
    segmente: list[Segment] = []
    block: list[str] = []

    def block_abschliessen(zeilen: list[str]) -> None:
        zeitzeile = next((z for z in zeilen if "-->" in z), None)
        if not zeitzeile:
            return
        links, rechts = zeitzeile.split("-->")[:2]
        text_zeilen = zeilen[zeilen.index(zeitzeile) + 1:]
        # WebVTT kennt Sprecher- und Zeitmarken im Text; beides stört.
        text = " ".join(text_zeilen)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return
        segmente.append(Segment(sekunden(links), sekunden(rechts.split()[0]), text))

    for zeile in inhalt.splitlines():
        if zeile.strip():
            block.append(zeile.strip())
            continue
        if block:
            block_abschliessen(block)
            block = []
    if block:
        block_abschliessen(block)

    # Auto-Untertitel wiederholen die Vorzeile ("rollende" Untertitel). Das
    # blaeht jeden Clip-Text auf und verfaelscht die Wortdichte.
    entdoppelt: list[Segment] = []
    for seg in segmente:
        if entdoppelt and seg.text.startswith(entdoppelt[-1].text):
            rest = seg.text[len(entdoppelt[-1].text):].strip()
            if not rest:
                entdoppelt[-1].ende = seg.ende
                continue
            seg = Segment(seg.start, seg.ende, rest)
        entdoppelt.append(seg)
    return entdoppelt


def lade_transkript(pfad: Path) -> list[Segment]:
    if not pfad.exists():
        raise QuellenFehler(f"Transkript nicht gefunden: {pfad}")
    inhalt = pfad.read_text(encoding="utf-8", errors="replace")
    if not inhalt.strip():
        raise QuellenFehler(f"Transkript ist leer: {pfad}")

    if pfad.suffix.lower() == ".json" or inhalt.lstrip()[:1] in "{[":
        daten = json.loads(inhalt)
        if isinstance(daten, list):
            daten = {"segments": daten}
        segmente = _aus_whisper(daten)
    else:
        segmente = _aus_untertiteldatei(inhalt)

    if not segmente:
        raise QuellenFehler(f"Kein Segment erkannt in {pfad}")
    return sorted(segmente, key=lambda s: s.start)


# --------------------------------------------------------------------------- #
# Chat
# --------------------------------------------------------------------------- #
_IRC = re.compile(r"^\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s+<?([^:>]{1,40})>?:\s+(.*)$")


def _chat_eintrag(roh: dict) -> ChatNachricht | None:
    for schluessel in ("content_offset_seconds", "time_in_seconds", "sekunde",
                       "offset", "zeit", "time"):
        if schluessel in roh and roh[schluessel] is not None:
            try:
                sek = float(roh[schluessel])
            except (TypeError, ValueError):
                continue
            break
    else:
        return None

    nutzer = ""
    for schluessel in ("nutzer", "user", "name", "author", "commenter"):
        wert = roh.get(schluessel)
        if isinstance(wert, dict):
            wert = wert.get("display_name") or wert.get("name")
        if wert:
            nutzer = str(wert)
            break

    text = ""
    for schluessel in ("text", "message", "body", "nachricht"):
        wert = roh.get(schluessel)
        if isinstance(wert, dict):
            wert = wert.get("body") or wert.get("message")
        if wert:
            text = str(wert)
            break
    if not text.strip():
        return None
    return ChatNachricht(sek, nutzer, text.strip())


def lade_chat(pfad: Path) -> list[ChatNachricht]:
    if not pfad.exists():
        raise QuellenFehler(f"Chat nicht gefunden: {pfad}")
    inhalt = pfad.read_text(encoding="utf-8", errors="replace")
    nachrichten: list[ChatNachricht] = []

    # Nicht am ersten Zeichen entscheiden: eine IRC-Zeile beginnt mit
    # "[00:12:34]" und sähe damit aus wie eine JSON-Liste.
    daten = None
    if inhalt.lstrip()[:1] in "{[":
        try:
            daten = json.loads(inhalt)
        except json.JSONDecodeError:
            daten = None
    if daten is not None:
        if isinstance(daten, dict):
            # Entweder ein Export mit Liste darin - oder eine JSONL-Datei mit
            # genau einer Zeile, die dann selbst die Nachricht ist.
            liste = (daten.get("comments") or daten.get("messages")
                     or daten.get("chat"))
            daten = liste if liste is not None else [daten]
        for roh in daten:
            eintrag = _chat_eintrag(roh) if isinstance(roh, dict) else None
            if eintrag:
                nachrichten.append(eintrag)
    else:
        for zeile in inhalt.splitlines():
            zeile = zeile.strip()
            if not zeile:
                continue
            if zeile.startswith("{"):
                try:
                    eintrag = _chat_eintrag(json.loads(zeile))
                except ValueError:
                    eintrag = None
                if eintrag:
                    nachrichten.append(eintrag)
                continue
            treffer = _IRC.match(zeile)
            if treffer:
                zeit, nutzer, text = treffer.groups()
                if text.strip():
                    nachrichten.append(ChatNachricht(sekunden(zeit), nutzer.strip(),
                                                     text.strip()))

    return sorted(nachrichten, key=lambda c: c.sekunde)


# --------------------------------------------------------------------------- #
# Stream zusammensetzen
# --------------------------------------------------------------------------- #
def lade_stream(stream_id: str, datum: str, streamer: str,
                transkript: Path | None = None, chat: Path | None = None,
                spiel: str = "", video: Path | None = None) -> Stream:
    """Mindestens eine Quelle muss da sein - Transkript oder Chat.

    Nur Chat ist ein gültiger Fall: die guten Momente findet der Chat auch
    ohne Transkript. Was dann fehlt, sind Untertitel und Zitate - siehe
    `Stream.nur_chat`.
    """
    if transkript is None and chat is None:
        raise QuellenFehler("Weder Transkript noch Chat angegeben – ohne "
                            "mindestens eine der beiden Quellen gibt es "
                            "nichts zu analysieren.")
    return Stream(
        stream_id=stream_id,
        datum=datum,
        streamer=streamer,
        spiel=spiel,
        segmente=lade_transkript(transkript) if transkript else [],
        chat=lade_chat(chat) if chat else [],
        video=video,
    )
