"""Aus dem Ton eines Streams ein Transkript machen.

Warum dieser Weg und nicht der Chat: Twitch verlangt für Chatabrufe einen
signierten Nachweis aus einem angemeldeten Browser ("failed integrity
check"). Das ist eine bewusste Schutzmaßnahme, und sie wird hier nicht
umgangen. Ton und Video sind davon nicht betroffen - beides ist anonym
abrufbar, mehrfach am Runner nachgemessen.

Das ist kein Rückschritt. Mit Transkript liefert das Clip-Werk mehr als mit
Chat: Untertitel, Zitate als Hook, Satzgrenzen beim Zuschnitt und das
Herausschneiden von Stille. Der Chat-Modus war der Behelf.

Benutzt wird `faster-whisper` statt `openai-whisper`. Beide erkennen
dasselbe Modell, aber faster-whisper rechnet auf denselben Kernen ein
Mehrfaches - der Unterschied entscheidet, ob ein 2,5-Stunden-Stream in einen
Actions-Lauf passt oder nicht.

Geschrieben wird das Format, das `quellen.lade_transkript` ohnehin liest:
Segmente mit Anfang, Ende, Text und - wo vorhanden - Wortzeiten. Die
Wortzeiten sind der Grund, warum die Untertitel später auf dem Wort sitzen
und nicht auf dem Satz.
"""
from __future__ import annotations

import json
from pathlib import Path

# Modelle nach Aufwand. "small" ist der Punkt, an dem deutsche Umgangssprache
# brauchbar erkannt wird, ohne dass die Laufzeit aus dem Ruder läuft.
MODELLE = ("tiny", "base", "small", "medium", "large-v3")
VORGABE = "small"


class TranskriptFehler(RuntimeError):
    pass


def schreibe(segmente: list[dict], ziel: Path) -> int:
    """Segmente als Whisper-JSON ablegen. Rückgabe ist die Anzahl."""
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps({"segments": segmente}, ensure_ascii=False),
                    encoding="utf-8")
    return len(segmente)


def _segment(roh, mit_woertern: bool) -> dict:
    """Ein faster-whisper-Segment in die Form bringen, die wir lesen."""
    eintrag = {
        "start": round(float(roh.start), 3),
        "end": round(float(roh.end), 3),
        "text": (roh.text or "").strip(),
    }
    if mit_woertern and getattr(roh, "words", None):
        eintrag["words"] = [
            {"word": (w.word or "").strip(),
             "start": round(float(w.start), 3),
             "end": round(float(w.end), 3)}
            for w in roh.words if (w.word or "").strip()
        ]
    return eintrag


def erkenne(ton: Path, ziel: Path, modell: str = VORGABE,
            sprache: str = "de", melden=print) -> int:
    """Ton erkennen und als Whisper-JSON ablegen.

    Läuft mit Stimmerkennung (VAD): Passagen ohne Sprache werden übersprungen
    statt erkannt. Bei einem Stream mit Spielpausen und Musik spart das viel
    Zeit und erspart dem Transkript erfundene Sätze aus Rauschen.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise TranskriptFehler(
            "faster-whisper ist nicht installiert. Nachholen mit:\n"
            "    pip install faster-whisper") from None

    if not ton.exists():
        raise TranskriptFehler(f"Tondatei nicht gefunden: {ton}")
    if modell not in MODELLE:
        raise TranskriptFehler(
            f"Unbekanntes Modell {modell!r}. Möglich: {', '.join(MODELLE)}")

    melden(f"Lade Modell „{modell}“ …")
    # int8 auf der CPU: deutlich schneller, und der Unterschied in der
    # Erkennung faellt bei Umgangssprache nicht ins Gewicht.
    maschine = WhisperModel(modell, device="cpu", compute_type="int8")

    melden(f"Erkenne {ton.name} …")
    strom, info = maschine.transcribe(
        str(ton), language=sprache, word_timestamps=True, vad_filter=True)

    gesamt = float(getattr(info, "duration", 0) or 0)
    segmente: list[dict] = []
    for roh in strom:            # faster-whisper liefert einen Generator
        segmente.append(_segment(roh, mit_woertern=True))
        if len(segmente) % 200 == 0:
            stand = segmente[-1]["end"]
            anteil = f" ({stand / gesamt * 100:.0f} %)" if gesamt else ""
            melden(f"  {len(segmente)} Segmente, bei "
                   f"{int(stand) // 60}:{int(stand) % 60:02d}{anteil}")

    if not segmente:
        raise TranskriptFehler(
            "Keine Sprache erkannt. Enthält die Datei überhaupt Ton?")

    schreibe(segmente, ziel)
    melden(f"{len(segmente)} Segmente in {ziel.name}")
    return len(segmente)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(
        prog="clipwerk-transkript",
        description="Ton eines Streams in ein Transkript umwandeln")
    p.add_argument("ton", help="Tondatei, z. B. ton.m4a")
    p.add_argument("--ziel", default="transkript.json")
    p.add_argument("--modell", default=VORGABE, choices=MODELLE)
    p.add_argument("--sprache", default="de")
    args = p.parse_args(argv)

    try:
        erkenne(Path(args.ton), Path(args.ziel), args.modell, args.sprache)
    except TranskriptFehler as fehler:
        print(f"Abbruch: {fehler}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
