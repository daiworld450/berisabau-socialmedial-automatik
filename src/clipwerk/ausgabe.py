"""Der Ausgabeblock aus Abschnitt 10 - und das Paket drumherum.

Die Feldnamen stehen wörtlich so in der Betriebsanweisung. Das ist keine
Förmlichkeit: der Block geht an einen Menschen, der schneidet, und der
sucht die Zeile „SCHNITT:", nicht ein hübscheres Wort dafür.

Neben dem Bericht schreibt `schreibe_paket` alles, was ein Editor braucht,
um sofort anzufangen - Untertitel als ASS und SRT, die Rohdaten als JSON
und, wenn das Quellvideo dabei ist, ein Renderskript.
"""
from __future__ import annotations

import json
from pathlib import Path

from .motor import Clip, Ergebnis, punch_fenster
from .quellen import Stream, stempel
from . import render as rnd
from . import untertitel as unt
from . import wachstum

TRENNER = "\n⸻\n"


def clipblock(clip: Clip) -> str:
    k, n, t = clip.kandidat, clip.note, clip.texte
    kopf = [
        f"CLIP NUMMER: {clip.nummer:02d}   ({clip.clip_id})",
        f"Timestamp Start: {stempel(k.start, mit_stunden=True)}",
        f"Timestamp Ende: {stempel(k.ende, mit_stunden=True)}",
        f"Dauer: {k.dauer:.0f} s"
        + (f"  (roh {k.roh_dauer:.0f} s, {k.roh_dauer - k.dauer:.0f} s Stille raus)"
           if k.roh_dauer - k.dauer >= 1.0 else ""),
        f"Kategorie: {n.kategorie}",
        f"Virality Score /100: {n.punkte}"
        + ("   ← höchste Priorität" if n.vorrang else ""),
        f"  Hook {n.hook:.1f}/25 · Unterhaltung {n.unterhaltung:.1f}/20 · "
        f"Watchtime {n.watchtime:.1f}/20 · Share {n.share:.1f}/15 · "
        f"Kommentar {n.kommentar:.1f}/10 · Follower {n.follower:.1f}/10",
        f"Warum dieser Clip: {n.begruendung}",
    ]

    teile = [
        "\n".join(kopf),
        f"HOOK IM VIDEO:\n\n{t.hook}",
        f"SCHNITT:\n\nBildaufteilung: {clip.plan.layout} – "
        f"{rnd_layout_text(clip.plan.layout)}\n\n{clip.plan.als_text()}",
        f"UNTERTITEL:\n\n{unt.als_text(clip.zeilen) or _kein_untertitel(clip)}",
        f"TIKTOK TITEL:\n\n{t.tiktok_titel}",
        f"TIKTOK CAPTION:\n\n{t.tiktok_caption}",
        f"HASHTAGS:\n\n{' '.join(t.hashtags)}",
        f"INSTAGRAM REELS CAPTION:\n\n{t.instagram_caption}",
        f"YOUTUBE SHORTS TITEL:\n\n{t.youtube_titel}   ({len(t.youtube_titel)} Zeichen)",
    ]
    return TRENNER.join(teile)


def _kein_untertitel(clip: Clip) -> str:
    if clip.kandidat.segmente:
        return "(kein Sprachanteil in diesem Ausschnitt)"
    return ("(kein Transkript – Untertitel müssen nachträglich erzeugt "
            "werden, z. B. mit Whisper über den fertigen Clip)")


def rnd_layout_text(layout: str) -> str:
    from .schnitt import LAYOUTS
    return LAYOUTS.get(layout, layout)


def bericht(ergebnis: Ergebnis, stream: Stream) -> str:
    from .bewertung import SCHWELLE_PRIORITAET, SCHWELLE_VERWERFEN

    vorrang = [c for c in ergebnis.clips if c.note.vorrang]
    kopf = [
        f"# Clip-Bericht: {stream.streamer} – {stream.datum}",
        "",
        f"Stream-ID `{stream.stream_id}`"
        + (f" · {stream.spiel}" if stream.spiel else "")
        + f" · Länge {stempel(stream.laenge, mit_stunden=True)}"
        + f" · {len(stream.segmente)} Sprachsegmente"
        + f" · {len(stream.chat)} Chatnachrichten",
        "",
        f"{ergebnis.geprueft} Momente geprüft, {len(ergebnis.clips)} über "
        f"{SCHWELLE_VERWERFEN} Punkten, davon {len(vorrang)} ab "
        f"{SCHWELLE_PRIORITAET} Punkten (höchste Priorität).",
        "",
    ]
    if not stream.chat:
        kopf += ["> Ohne Chat-Datei fehlt das stärkste Signal. Die Auswahl "
                 "stützt sich allein auf die Sprache und ist entsprechend "
                 "unsicherer.", ""]
    if stream.nur_chat:
        kopf += ["> **Ohne Transkript gelaufen.** Die Momente stammen allein "
                 "aus dem Chat – das findet die Ausschläge zuverlässig, aber "
                 "es fehlen: Untertitel, Zitate als Hook, Satzgrenzen beim "
                 "Zuschnitt und das Herausschneiden von Stille. Die "
                 "Zeitstempel sind Anhaltspunkte, kein fertiger Schnitt. "
                 "Mit Transkript wird aus denselben Momenten deutlich mehr.",
                 ""]
    if not ergebnis.clips:
        kopf += ["Kein Moment hat die Schwelle erreicht. Das ist ein "
                 "gültiges Ergebnis: nicht jeder Stream trägt einen Clip "
                 "(Abschnitt 15).", ""]

    teile = ["\n".join(kopf)]
    for clip in ergebnis.clips:
        teile.append("---\n\n" + clipblock(clip))

    daten = [c.als_dict(stream) for c in ergebnis.clips]
    teile.append("---\n\n" + wachstum.als_text(
        wachstum.auswerten(daten, stream.streamer), stream.streamer))

    if ergebnis.verworfen:
        zeilen = ["---", "", "## Verworfen", "",
                  "Momente, die aufgefallen sind, aber unter der Schwelle "
                  "blieben. Bewusst aufgeführt: wer sie doch will, sieht "
                  "hier, wo sie liegen.", ""]
        for start, punkte, kategorie in sorted(ergebnis.verworfen,
                                               key=lambda v: -v[1])[:15]:
            zeilen.append(f"- {stempel(start, mit_stunden=True)} · "
                          f"{punkte} Punkte · {kategorie}")
        teile.append("\n".join(zeilen))

    return "\n\n".join(teile) + "\n"


# --------------------------------------------------------------------------- #
# Dateien
# --------------------------------------------------------------------------- #
def schreibe_paket(ergebnis: Ergebnis, stream: Stream, ziel: Path,
                   facecam: rnd.Facecam | None = None) -> dict:
    """Bericht, Rohdaten, Untertitel und Renderskript in einen Ordner."""
    ziel.mkdir(parents=True, exist_ok=True)
    untertitel_ordner = ziel / "untertitel"
    untertitel_ordner.mkdir(exist_ok=True)

    daten = [c.als_dict(stream) for c in ergebnis.clips]
    (ziel / "bericht.md").write_text(bericht(ergebnis, stream), encoding="utf-8")
    (ziel / "clips.json").write_text(
        json.dumps({"stream": {"stream_id": stream.stream_id,
                               "datum": stream.datum,
                               "streamer": stream.streamer,
                               "spiel": stream.spiel,
                               "laenge": round(stream.laenge, 1)},
                    "clips": daten}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    befehle: list[list[str]] = []
    for clip in ergebnis.clips:
        name = f"clip-{clip.nummer:02d}"
        ass = untertitel_ordner / f"{name}.ass"
        # Ohne Sprachanteil entstuende eine Datei mit Kopfzeile und nichts
        # dahinter. Die hilft niemandem und sieht im Ordner nach einem
        # Ergebnis aus, das es nicht gibt.
        if clip.zeilen:
            ass.write_text(unt.als_ass(clip.zeilen), encoding="utf-8")
            (untertitel_ordner / f"{name}.srt").write_text(
                unt.als_srt(clip.zeilen), encoding="utf-8")
        if stream.video:
            befehle.append(rnd.ffmpeg_befehl(
                stream.video, clip.kandidat, clip.plan.layout,
                ziel / f"{name}.mp4",
                untertitel=ass if clip.zeilen else None, facecam=facecam,
                punch_fenster=punch_fenster(clip)))

    if not any(untertitel_ordner.iterdir()):
        untertitel_ordner.rmdir()

    skript = None
    if befehle:
        skript = rnd.schreibe_skript(befehle, ziel / "rendern.sh")

    return {"ordner": ziel, "clips": len(daten), "skript": skript,
            "bericht": ziel / "bericht.md", "json": ziel / "clips.json"}
