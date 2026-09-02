"""ffmpeg-Befehle für das 9:16-Format - Abschnitt 6 und 7.

Dieses Modul rendert nicht selbst, es *baut den Befehl*. Das ist Absicht:
der Befehl lässt sich prüfen, in eine Schnittsoftware übernehmen, in einen
Renderknecht schieben oder eben ausführen. Ein Renderer, der nur eine
fertige Datei ausspuckt, ist bei einem falschen Facecam-Ausschnitt nicht zu
debuggen.

Ein Befehl erledigt vier Dinge in einem Durchgang:

1. **Schnitt** – Anfang und Ende über `-ss`/`-to`, die Stillen im Innern
   über `select`/`aselect`. Das ist der Grund, warum das in einem Durchgang
   geht und nicht in fünf Zwischendateien.
2. **Bildaufteilung** – 1080×1920, je nach Layout aus Gameplay und Facecam
   zusammengesetzt. Ohne Facecam-Koordinaten fällt jedes Layout auf
   „vollbild" zurück, statt einen leeren Kasten zu rendern.
3. **Punch-In** – über `zoompan`, gesteuert aus dem Schnittplan. Kein
   Dauerzoom: nur in den Fenstern, die der Plan nennt.
4. **Untertitel** – die ASS-Datei wird eingebrannt, weil TikTok, Instagram
   und YouTube die Textspur sonst je eigen behandeln.

Braucht ffmpeg ab Version 5 (`zoompan` mit `it`).
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .kandidaten import Kandidat

BREITE, HOEHE = 1080, 1920
BILDRATE = 30
ZOOM_STAERKE = 1.22


@dataclass
class Facecam:
    """Ausschnitt der Webcam im Quellbild, in Pixeln des Quellvideos."""
    x: int
    y: int
    breite: int
    hoehe: int

    @classmethod
    def aus_text(cls, roh: str) -> "Facecam":
        teile = roh.replace("x", ":").split(":")
        if len(teile) != 4:
            raise ValueError("Facecam erwartet 'x:y:breite:höhe', "
                             f"bekommen: {roh!r}")
        return cls(*(int(t) for t in teile))

    def crop(self) -> str:
        return f"crop={self.breite}:{self.hoehe}:{self.x}:{self.y}"


def _behaltene_bereiche(kandidat: Kandidat) -> list[tuple[float, float]]:
    """Die Stücke, die bleiben - in der Zeitachse des zugeschnittenen Videos."""
    bereiche: list[tuple[float, float]] = []
    marke = 0.0
    for von, bis in kandidat.auslassungen:
        von_rel, bis_rel = von - kandidat.start, bis - kandidat.start
        if von_rel > marke:
            bereiche.append((marke, von_rel))
        marke = max(marke, bis_rel)
    laenge = kandidat.roh_dauer
    if marke < laenge:
        bereiche.append((marke, laenge))
    return bereiche or [(0.0, laenge)]


def _schnitt_filter(kandidat: Kandidat) -> tuple[str, str]:
    """select/aselect für die inneren Schnitte, sonst leer."""
    if not kandidat.auslassungen:
        return "", ""
    bereiche = _behaltene_bereiche(kandidat)
    ausdruck = "+".join(f"between(t,{von:.2f},{bis:.2f})" for von, bis in bereiche)
    return (f"select='{ausdruck}',setpts=N/FRAME_RATE/TB",
            f"aselect='{ausdruck}',asetpts=N/SR/TB")


# Wie lange der Zoom braucht, um voll da zu sein. Darunter wirkt es wie ein
# Sprung, darüber merkt es in einem 20-Sekunden-Clip niemand mehr.
ZOOM_RAMPE = 0.25


def _zoom_filter(fenster: list[tuple[float, float]]) -> str:
    """Punch-In nur in den genannten Fenstern, sonst Normalgröße.

    Je Fenster ein Term, der in 0,25 s von 0 auf 1 läuft und am Fensterende
    wieder abfällt. Die Summe wird auf 0..1 begrenzt, damit sich zwei
    überlappende Fenster nicht zu doppeltem Zoom addieren.
    """
    if not fenster:
        return ""
    terme = []
    for von, bis in fenster:
        terme.append(f"between(it,{von:.2f},{bis:.2f})"
                     f"*min(1,(it-{von:.2f})/{ZOOM_RAMPE})")
    anteil = f"min(1,max(0,{'+'.join(terme)}))"
    ausdruck = f"1+{ZOOM_STAERKE - 1:.3f}*{anteil}"
    return (f"zoompan=z='{ausdruck}':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={BREITE}x{HOEHE}:fps={BILDRATE}")


def _layout_filter(layout: str, facecam: Facecam | None) -> str:
    """Kette vom Quellbild zum fertigen 1080×1920-Bild."""
    if layout != "vollbild" and facecam is None:
        layout = "vollbild"

    if layout == "vollbild":
        # Unscharfe, formatfüllende Dopplung als Hintergrund - besser als
        # schwarze Balken, weil TikTok Balkenflächen als Bild wertet.
        return (
            f"[0:v]split=2[hg][vg];"
            f"[hg]scale={BREITE}:{HOEHE}:force_original_aspect_ratio=increase,"
            f"crop={BREITE}:{HOEHE},boxblur=28:2[bg];"
            f"[vg]scale={BREITE}:-2[vd];"
            f"[bg][vd]overlay=(W-w)/2:(H-h)/2,setsar=1[gebaut]"
        )

    if layout == "nur_person":
        return (
            f"[0:v]{facecam.crop()},scale={BREITE}:{HOEHE}:"
            f"force_original_aspect_ratio=increase,crop={BREITE}:{HOEHE},"
            f"setsar=1[gebaut]"
        )

    if layout == "geteilt":
        oben, unten = 760, HOEHE - 760
        return (
            f"[0:v]split=2[cam][spiel];"
            f"[cam]{facecam.crop()},scale={BREITE}:{oben}:"
            f"force_original_aspect_ratio=increase,crop={BREITE}:{oben}[o];"
            f"[spiel]scale={BREITE}:{unten}:force_original_aspect_ratio=increase,"
            f"crop={BREITE}:{unten}[u];"
            f"[o][u]vstack=inputs=2,setsar=1[gebaut]"
        )

    if layout == "facecam_gross":
        cam_breite, cam_hoehe = 700, 394
        return (
            f"[0:v]split=2[hg][cam];"
            f"[hg]scale={BREITE}:{HOEHE}:force_original_aspect_ratio=increase,"
            f"crop={BREITE}:{HOEHE}[bg];"
            f"[cam]{facecam.crop()},scale={cam_breite}:{cam_hoehe}[k];"
            f"[bg][k]overlay=(W-w)/2:220,setsar=1[gebaut]"
        )

    raise ValueError(f"unbekanntes Layout: {layout}")


def ffmpeg_befehl(video: Path, kandidat: Kandidat, layout: str, ziel: Path,
                  untertitel: Path | None = None,
                  facecam: Facecam | None = None,
                  punch_fenster: list[tuple[float, float]] | None = None,
                  ) -> list[str]:
    kette = [_layout_filter(layout, facecam)]
    marke = "[gebaut]"

    schnitt_v, schnitt_a = _schnitt_filter(kandidat)
    if schnitt_v:
        kette.append(f"{marke}{schnitt_v}[geschnitten]")
        marke = "[geschnitten]"

    zoom = _zoom_filter(punch_fenster or [])
    if zoom:
        kette.append(f"{marke}{zoom}[gezoomt]")
        marke = "[gezoomt]"

    if untertitel is not None:
        # Backslashes und Doppelpunkte im Pfad würden den Filtergraph zerlegen.
        pfad = str(untertitel).replace("\\", "/").replace(":", r"\:")
        kette.append(f"{marke}ass='{pfad}'[fertig]")
    else:
        kette.append(f"{marke}null[fertig]")

    audio_kette = []
    if schnitt_a:
        audio_kette.append(f"[0:a]{schnitt_a}[ton]")

    befehl = [
        "ffmpeg", "-y",
        "-ss", f"{kandidat.start:.2f}", "-to", f"{kandidat.ende:.2f}",
        "-i", str(video),
        "-filter_complex", ";".join(kette + audio_kette),
        "-map", "[fertig]",
        "-map", "[ton]" if audio_kette else "0:a?",
        "-r", str(BILDRATE),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart",
        str(ziel),
    ]
    return befehl


def ffmpeg_vorhanden() -> bool:
    return shutil.which("ffmpeg") is not None


def schreibe_skript(befehle: list[list[str]], pfad: Path) -> Path:
    """Alle Befehle als ausführbares Skript - für den Rechner des Editors."""
    import shlex

    zeilen = ["#!/bin/sh",
              "# Erzeugt vom Clip-Werk. Jeder Block ist ein fertiger Clip.",
              "set -e", ""]
    for befehl in befehle:
        zeilen.append(" ".join(shlex.quote(teil) for teil in befehl))
        zeilen.append("")
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text("\n".join(zeilen), encoding="utf-8")
    pfad.chmod(0o755)
    return pfad


def rendere(befehl: list[str]) -> tuple[bool, str]:
    if not ffmpeg_vorhanden():
        return False, "ffmpeg ist nicht installiert – Befehl wurde nur geschrieben."
    lauf = subprocess.run(befehl, capture_output=True, text=True)
    if lauf.returncode == 0:
        return True, ""
    zeilen = (lauf.stderr or "").strip().splitlines()
    return False, zeilen[-1] if zeilen else "ffmpeg meldete einen Fehler ohne Ausgabe."
