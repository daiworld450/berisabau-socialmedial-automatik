"""Verarbeitet Fotos aus dem Eingangsordner automatisch.

Gedacht als Dauerablage: Baustellenfotos werden roh in
content/medien/eingang/ geworfen, ohne Umbenennen, ohne Sortieren. Dieses
Modul holt sie sich, korrigiert sie handwerklich (Ausrichtung, Belichtung,
Schärfe) und legt sie fertig in content/medien/pool/ ab, wo der Planer sie
für die Säulen "detail" und "mensch" verwendet.

Bewusste Grenze, die auch im Content-Prompt steht: Es wird nichts erzeugt,
nur bearbeitet. Kein KI-Bild ersetzt oder ergänzt ein echtes Foto – das
wäre nach Regel 1 in content/CONTENT-PROMPT.md Wettbewerbsbetrug.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

from config import MEDIEN_DIR

EINGANG_DIR = MEDIEN_DIR / "eingang"
VERARBEITET_DIR = EINGANG_DIR / "verarbeitet"
POOL_DIR = MEDIEN_DIR / "pool"
PROTOKOLL_DATEI = EINGANG_DIR / "verarbeitung.log.json"

ENDUNGEN = {".jpg", ".jpeg", ".png", ".webp"}

# Lange Kante nach der Bearbeitung. Größer bringt für 1080px-Instagrambilder
# nichts, macht die Ablage nur unnötig groß.
MAX_KANTE = 2400
JPEG_QUALITAET = 92


def _eingegangene_fotos() -> list[Path]:
    if not EINGANG_DIR.exists():
        return []
    return sorted(p for p in EINGANG_DIR.iterdir()
                  if p.is_file() and p.suffix.lower() in ENDUNGEN)


def _bearbeite(pfad: Path) -> Image.Image:
    """Handwerkliche Grundkorrektur – keine Inhaltsänderung, kein Zuschnitt.

    Der endgültige Bildausschnitt entsteht erst beim Rendern in der Vorlage
    (object-fit: cover). Hier geht es nur um das, was jedes Foto ab Kamera
    sowieso bräuchte: richtig herum, nicht zu flau, nicht zu weich.
    """
    bild = Image.open(pfad)
    bild = ImageOps.exif_transpose(bild)          # Ausrichtung aus EXIF, dann verwerfen
    if bild.mode != "RGB":
        bild = bild.convert("RGB")

    if max(bild.size) > MAX_KANTE:
        bild.thumbnail((MAX_KANTE, MAX_KANTE), Image.LANCZOS)

    # Milder Autokontrast: kappt die hellsten/dunkelsten 1 % je Kanal, damit
    # ein einzelner Reflex oder Schatten die Korrektur nicht verzieht.
    bild = ImageOps.autocontrast(bild, cutoff=1)
    bild = ImageEnhance.Color(bild).enhance(1.06)
    bild = ImageEnhance.Contrast(bild).enhance(1.04)
    bild = ImageEnhance.Sharpness(bild).enhance(1.15)
    return bild


def _sauberer_name(pfad: Path) -> str:
    zeitstempel = datetime.now().strftime("%Y%m%d-%H%M%S")
    stamm = "".join(c if c.isalnum() or c in "-_" else "-" for c in pfad.stem.lower())
    return f"{zeitstempel}_{stamm or 'foto'}.jpg"


def verarbeite_eingang() -> dict:
    """Verarbeitet alle neuen Fotos im Eingang. Läuft gefahrlos mehrfach."""
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    VERARBEITET_DIR.mkdir(parents=True, exist_ok=True)

    verarbeitet, fehlgeschlagen = [], []

    for quelle in _eingegangene_fotos():
        ziel_name = _sauberer_name(quelle)
        try:
            bild = _bearbeite(quelle)
            bild.save(POOL_DIR / ziel_name, "JPEG", quality=JPEG_QUALITAET)
        except Exception as fehler:                       # noqa: BLE001
            fehlgeschlagen.append({"datei": quelle.name, "grund": str(fehler)})
            continue

        # Original bewahren statt löschen – falls die Bearbeitung mal daneben
        # geht, ist nichts verloren.
        quelle.rename(VERARBEITET_DIR / quelle.name)
        verarbeitet.append({"eingang": quelle.name, "pool": ziel_name})

    if verarbeitet or fehlgeschlagen:
        _protokolliere(verarbeitet, fehlgeschlagen)

    return {"verarbeitet": verarbeitet, "fehlgeschlagen": fehlgeschlagen}


def _protokolliere(verarbeitet: list[dict], fehlgeschlagen: list[dict]) -> None:
    eintraege = []
    if PROTOKOLL_DATEI.exists():
        eintraege = json.loads(PROTOKOLL_DATEI.read_text(encoding="utf-8"))
    eintraege.append({
        "zeitpunkt": datetime.now().isoformat(timespec="seconds"),
        "verarbeitet": verarbeitet,
        "fehlgeschlagen": fehlgeschlagen,
    })
    PROTOKOLL_DATEI.write_text(
        json.dumps(eintraege, ensure_ascii=False, indent=2), encoding="utf-8")
