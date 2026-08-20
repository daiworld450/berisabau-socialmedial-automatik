"""Zustand für den Google-Ads-Update-Kanal: was wurde schon gemeldet, was
gemerkt, welches Thema soll nicht mehr auftauchen.

Gleiches Muster wie freigaben.py - eine JSON-Datei statt einer Datenbank,
weil GitHub Actions ohnehin bei jedem Lauf einen frischen Checkout macht und
das Ergebnis zurückcommittet (siehe .github/workflows/ads-*.yml).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from config import ADS_VERLAUF_DATEI

_SCHLUESSEL = ("gemeldet", "gemerkt", "ignoriert")


def _leer() -> dict:
    return {k: {} for k in _SCHLUESSEL}


def _lade() -> dict:
    if ADS_VERLAUF_DATEI.exists():
        daten = json.loads(ADS_VERLAUF_DATEI.read_text(encoding="utf-8"))
        for schluessel in _SCHLUESSEL:
            daten.setdefault(schluessel, {})
        return daten
    return _leer()


def _speichere(daten: dict) -> None:
    ADS_VERLAUF_DATEI.write_text(
        json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()[:16]


def schon_gemeldet(hash_id: str) -> bool:
    return hash_id in _lade()["gemeldet"]


def ist_ignoriert(hash_id: str) -> bool:
    return hash_id in _lade()["ignoriert"]


def merke_meldung(hash_id: str, ueberschrift: str, url: str, volltext: str) -> None:
    daten = _lade()
    daten["gemeldet"][hash_id] = {
        "ueberschrift": ueberschrift,
        "url": url,
        "volltext": volltext,
        "gesendet_am": datetime.now().isoformat(timespec="seconds"),
    }
    _speichere(daten)


def hole_meldung(hash_id: str) -> dict | None:
    return _lade()["gemeldet"].get(hash_id)


def gemeldete_ueberschriften(letzte: int = 30) -> list[str]:
    """Für den Relevanzfilter: worüber wurde zuletzt schon berichtet, damit
    dieselbe Story nicht als 'neu' durchgeht, nur weil eine andere Quelle sie
    noch einmal aufgreift."""
    eintraege = sorted(_lade()["gemeldet"].values(),
                       key=lambda e: e["gesendet_am"], reverse=True)
    return [e["ueberschrift"] for e in eintraege[:letzte]]


def merken(hash_id: str) -> None:
    daten = _lade()
    daten["gemerkt"][hash_id] = datetime.now().isoformat(timespec="seconds")
    _speichere(daten)


def ignorieren(hash_id: str, thema: str = "") -> None:
    daten = _lade()
    daten["ignoriert"][hash_id] = {
        "thema": thema,
        "seit": datetime.now().isoformat(timespec="seconds"),
    }
    _speichere(daten)


def ignorierte_themen() -> list[str]:
    return [e["thema"] for e in _lade()["ignoriert"].values() if e.get("thema")]


def letzte_meldung_am() -> str | None:
    """ISO-Zeitpunkt der letzten Kanal-Nachricht (egal ob echte Meldung
    oder 'Nichts Relevantes'-Zeile) - Basis für die Stille-Schwelle in
    ads_news.py."""
    daten = _lade()
    zeitpunkte = [e["gesendet_am"] for e in daten["gemeldet"].values()]
    letzte_leermeldung = daten.get("letzte_leermeldung_am")
    if letzte_leermeldung:
        zeitpunkte.append(letzte_leermeldung)
    return max(zeitpunkte) if zeitpunkte else None


def vermerke_leermeldung() -> None:
    daten = _lade()
    daten["letzte_leermeldung_am"] = datetime.now().isoformat(timespec="seconds")
    _speichere(daten)
