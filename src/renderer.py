"""Rendert die Marken-Vorlagen als PNG in Instagram-Auflösung.

HTML/CSS statt Pillow: so ist die Vorlage exakt dieselbe Design-Sprache wie
berisabau.de (Rajdhani/Rubik, roter Schrägstrich, Raster, Farbverläufe) und
lässt sich später ohne Python-Kenntnisse anpassen.
"""
from __future__ import annotations

import base64
import re
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

from config import BRAND, FONT_DIR, OUT_DIR, TEMPLATE_DIR, BRAND_DIR, datei_url

# Formatabhängige Typo-Skalierung. Die Werte sind auf 1080 px Breite gerechnet.
FORMATE = {
    "feed":    {"w": 1080, "h": 1350, "pad": 72, "h1": 92,  "lead": 32, "punkt": 30, "logo_h": 70},
    "quadrat": {"w": 1080, "h": 1080, "pad": 68, "h1": 84,  "lead": 30, "punkt": 28, "logo_h": 66},
    "story":   {"w": 1080, "h": 1920, "pad": 88, "h1": 104, "lead": 36, "punkt": 34, "logo_h": 78},
}

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


@lru_cache(maxsize=1)
def _schriften() -> dict[str, str]:
    """Schriften als data:-URI – unabhängig von Systemfonts und Netzwerk."""
    fonts = {}
    for ttf in sorted(FONT_DIR.glob("*.ttf")):
        b64 = base64.b64encode(ttf.read_bytes()).decode("ascii")
        fonts[ttf.stem] = f"data:font/truetype;base64,{b64}"
    fehlend = {"Rajdhani-Medium", "Rajdhani-SemiBold", "Rajdhani-Bold", "Rubik"} - fonts.keys()
    if fehlend:
        raise FileNotFoundError(f"Schriften fehlen in {FONT_DIR}: {', '.join(sorted(fehlend))}")
    return fonts


def _css(masse: dict) -> str:
    roh = (TEMPLATE_DIR / "_base.css").read_text(encoding="utf-8")
    return _env.from_string(roh).render(b=BRAND, fonts=_schriften(), m=masse)


def _bildpfad(wert: str | None) -> str | None:
    """Wandelt einen Medien-Pfad in eine file:///-URL, die Chromium laden kann."""
    if not wert:
        return None
    p = Path(wert)
    if not p.is_absolute():
        p = (Path(__file__).resolve().parent.parent / wert).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Bild nicht gefunden: {p}")
    return datei_url(p)


def baue_html(vorlage: str, daten: dict, format: str = "feed") -> str:
    masse = FORMATE[format]
    kontext = dict(daten)

    for schluessel in ("bild", "bild_vorher", "bild_nachher"):
        if schluessel in kontext:
            kontext[schluessel] = _bildpfad(kontext[schluessel])

    # Maße bewusst unter 'm' – sonst überschreiben sie Inhaltsfelder wie 'lead'.
    # Logo ist ueberall rot - Markenvorgabe. Einzige Ausnahme: die rote
    # Kachel-Variante selbst (voll rote Flaeche), da waere ein rotes Logo
    # unsichtbar. Dort bleibt es beim bewaehrten Weiss dieser Variante.
    rote_flaeche = kontext.get("variante") == "rot"
    kontext.update(
        b=BRAND,
        m=masse,
        css=_css(masse),
        logo_weiss=datei_url(BRAND_DIR / "logo-weiss.svg"),
        logo_rot=datei_url(BRAND_DIR / "logo-rot.svg"),
        logo_kachel=datei_url(BRAND_DIR / ("logo-weiss.svg" if rote_flaeche else "logo-rot.svg")),
    )
    return _env.get_template(vorlage).render(**kontext)


def rendere(vorlage: str, daten: dict, ziel: str | Path, format: str = "feed") -> Path:
    """Rendert eine Vorlage als Bild und gibt den Zielpfad zurück.

    Standard ist JPEG: die Instagram-Publishing-API nimmt für 'image_url'
    ausschließlich JPEG an – ein PNG wird abgelehnt.
    """
    masse = FORMATE[format]
    ziel = Path(ziel)
    if not ziel.is_absolute():
        ziel = OUT_DIR / ziel
    ziel.parent.mkdir(parents=True, exist_ok=True)
    typ = "png" if ziel.suffix.lower() == ".png" else "jpeg"

    html = baue_html(vorlage, daten, format)
    tmp = OUT_DIR / "_render.html"
    tmp.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb", "--font-render-hinting=none"])
        page = browser.new_page(viewport={"width": masse["w"], "height": masse["h"]},
                                device_scale_factor=1)
        page.goto(tmp.as_uri())
        page.wait_for_timeout(450)          # Schriften und Bilder sicher geladen
        if typ == "jpeg":
            page.screenshot(path=str(ziel), type="jpeg", quality=92)
        else:
            page.screenshot(path=str(ziel), type="png")
        browser.close()

    tmp.unlink(missing_ok=True)
    return ziel


MAX_SLIDES = 10          # Instagram-Grenze für Carousels


def rendere_carousel(carousel: dict, praefix: str, format: str = "feed") -> list[Path]:
    """Rendert alle Slides eines Carousels und gibt die Pfade in Reihenfolge zurück.

    Reihenfolge ist entscheidend: Instagram zeigt die Slides genau so an, wie
    die Container-IDs übergeben werden.
    """
    slides = carousel["slides"]
    if len(slides) > MAX_SLIDES:
        raise ValueError(
            f"{carousel['id']}: {len(slides)} Slides – Instagram erlaubt höchstens {MAX_SLIDES}."
        )

    pfade = []
    for nr, slide in enumerate(slides, start=1):
        daten = {k: v for k, v in slide.items() if k != "vorlage"}
        daten.setdefault("gewerk", carousel.get("gewerk", ""))
        ziel = OUT_DIR / f"{praefix}_{nr:02d}.jpg"
        pfade.append(rendere(slide["vorlage"], daten, ziel, format=format))
    return pfade


def kuerze_dateiname(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:60] or "post"
