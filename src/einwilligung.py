"""Sperrt Fotos, für die keine Einwilligung des Kunden vorliegt.

Warum es das gibt: Die Fotos zeigen fremde Wohnungen. Als Handwerker durfte
Damir dort arbeiten - das ist keine Erlaubnis zu veroeffentlichen. Kommt spaeter
eine Beschwerde, zaehlt nur, ob eine Zustimmung nachweisbar ist.

Der Nachweis ist absichtlich zweigeteilt:

    einwilligungen/register.json     Wer, welches Objekt, wann gefragt, was
                                     erlaubt. Enthaelt Kundennamen - liegt
                                     deshalb NUR lokal und ist gesperrt.

    content/medien/freigabe.json     Nur die Dateinamen, die raus duerfen.
                                     Keine Personendaten. Darf im oeffentlichen
                                     Repo liegen, damit GitHub Actions pruefen
                                     kann, ohne je Kundendaten zu sehen.

Die Sperre schliesst im Zweifel: Was nicht eingetragen ist, geht nicht raus.
Lieber ein Beitrag weniger als ein Foto zu viel.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

WURZEL   = Path(__file__).resolve().parent.parent
FREIGABE = WURZEL / "content" / "medien" / "freigabe.json"
REGISTER = WURZEL / "einwilligungen" / "register.json"


@lru_cache(maxsize=1)
def _freigegeben() -> set[str]:
    """Dateinamen, die veroeffentlicht werden duerfen."""
    if not FREIGABE.exists():
        return set()
    try:
        daten = json.loads(FREIGABE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Eine kaputte Freigabeliste darf nicht dazu fuehren, dass ploetzlich
        # alles erlaubt ist. Im Zweifel sperrt sie alles.
        return set()
    return {str(n) for n in daten.get("freigegeben", [])}


def neu_laden() -> None:
    """Nach dem Eintragen einer Einwilligung aufrufen."""
    _freigegeben.cache_clear()


def ist_frei(pfad: Path | str) -> bool:
    """Darf diese Datei in einen Beitrag?

    Verglichen wird der Dateiname, nicht der Pfad: Dasselbe Foto liegt einmal
    im Eingang, einmal im Pool und einmal im Projektordner - die Einwilligung
    gilt fuer das Motiv, nicht fuer den Ablageort.
    """
    return Path(pfad).name in _freigegeben()


def filtere(pfade: list[Path]) -> list[Path]:
    """Alles ohne Einwilligung aussortieren."""
    return [p for p in pfade if ist_frei(p)]


def gesperrte(pfade: list[Path]) -> list[Path]:
    return [p for p in pfade if not ist_frei(p)]


def bericht(pfade: list[Path]) -> str:
    """Kurze Lage fuer Protokoll und Telegram."""
    frei, gesperrt = filtere(pfade), gesperrte(pfade)
    if not gesperrt:
        return f"{len(frei)} Medien, alle mit Einwilligung."
    namen = ", ".join(p.name for p in gesperrt[:5])
    mehr = f" (+{len(gesperrt) - 5} weitere)" if len(gesperrt) > 5 else ""
    return (f"{len(frei)} freigegeben, {len(gesperrt)} GESPERRT ohne "
            f"Einwilligung: {namen}{mehr}")


def offene_posten() -> list[dict]:
    """Eintraege im Register, bei denen die Zustimmung noch aussteht."""
    if not REGISTER.exists():
        return []
    try:
        daten = json.loads(REGISTER.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [e for e in daten.get("eintraege", []) if e.get("status") != "erteilt"]
