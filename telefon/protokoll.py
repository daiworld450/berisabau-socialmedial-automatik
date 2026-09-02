"""Jeder Anruf wird protokolliert - auch der, der nicht zustande kam.

Das Protokoll ist kein Bericht, sondern Nachweis. Wenn drei Monate später
jemand behauptet, dreimal angerufen worden zu sein, muss hier stehen, was
wirklich war: wann gewählt wurde, wann die KI-Offenlegung fiel, was gesagt
wurde, warum Schluss war.

JSONL statt JSON: anhängbar ohne Sperre, überlebt einen Absturz mitten im
Schreiben, und die Datei bleibt lesbar, wenn sie groß wird.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from einstellungen import PROTOKOLL_DATEI
from nummern import NummernFehler, normalisieren

_schloss = threading.Lock()


def _ziel(datei: Path | None) -> Path:
    """Pfad erst beim Aufruf auflösen, nicht beim Import.

    Stand der Pfad als Vorgabewert in der Signatur (datei=PROTOKOLL_DATEI),
    war er beim Laden des Moduls festgezurrt. eintragen() schaute dann auf
    die globale Variable, lesen() auf den alten Vorgabewert - beide auf
    verschiedene Dateien, sobald jemand die Einstellung umstellt. Das ist
    genau der Fehler, der ein Tageslimit ins Leere laufen lässt.
    """
    return datei or PROTOKOLL_DATEI



def eintragen(nummer: str, **felder) -> dict:
    """Eine Zeile ans Protokoll hängen. Gibt den geschriebenen Satz zurück."""
    datei = _ziel(None)
    try:
        nummer = normalisieren(nummer)
    except NummernFehler:
        pass  # unbrauchbare Nummer trotzdem festhalten - das ist der Befund
    satz = {"zeit": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "nummer": nummer, **felder}
    with _schloss:
        datei.parent.mkdir(parents=True, exist_ok=True)
        with datei.open("a", encoding="utf-8") as f:
            # Endete die Datei mitten in einer Zeile (Absturz beim letzten
            # Schreiben), würde der neue Satz daran kleben und wäre selbst
            # unlesbar - ein Fehler frisst so den nächsten. Erst umbrechen,
            # dann schreiben: die kaputte Zeile bleibt kaputt, der neue Satz
            # ist heil.
            if datei.stat().st_size and not _endet_mit_umbruch(datei):
                f.write("\n")
            f.write(json.dumps(satz, ensure_ascii=False) + "\n")
    return satz


def _endet_mit_umbruch(datei: Path) -> bool:
    with datei.open("rb") as f:
        f.seek(-1, 2)
        return f.read(1) == b"\n"


def lesen(datei: Path | None = None) -> list[dict]:
    datei = _ziel(datei)
    if not datei.exists():
        return []
    saetze = []
    for zeile in datei.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            saetze.append(json.loads(zeile))
        except json.JSONDecodeError:
            # Eine abgeschnittene letzte Zeile (Absturz beim Schreiben) darf
            # nicht die Auswertung der übrigen 5000 verhindern.
            continue
    return saetze


def _zeit(satz: dict) -> datetime:
    return datetime.fromisoformat(satz["zeit"])


def anrufe_heute(datei: Path | None = None) -> int:
    """Zählt nur tatsächlich gewählte Nummern, keine Aussortierten."""
    datei = _ziel(datei)
    heute = datetime.now(timezone.utc).date()
    return sum(1 for s in lesen(datei)
               if s.get("ereignis") == "gewaehlt" and _zeit(s).date() == heute)


def versuche(nummer: str, datei: Path | None = None) -> list[dict]:
    datei = _ziel(datei)
    try:
        nummer = normalisieren(nummer)
    except NummernFehler:
        return []
    return [s for s in lesen(datei)
            if s.get("nummer") == nummer and s.get("ereignis") == "gewaehlt"]


def zuletzt_gewaehlt(nummer: str, datei: Path | None = None) -> datetime | None:
    reihe = versuche(nummer, _ziel(datei))
    return max((_zeit(s) for s in reihe), default=None)


def abstand_eingehalten(nummer: str, tage: int,
                        datei: Path | None = None) -> bool:
    letzter = zuletzt_gewaehlt(nummer, _ziel(datei))
    if letzter is None:
        return True
    return datetime.now(timezone.utc) - letzter >= timedelta(days=tage)


def zusammenfassung(datei: Path | None = None) -> dict[str, int]:
    """Grobe Zählung für die Wochenauswertung."""
    zahlen: dict[str, int] = {}
    for satz in lesen(_ziel(datei)):
        schluessel = satz.get("ergebnis") or satz.get("ereignis") or "unbekannt"
        zahlen[schluessel] = zahlen.get(schluessel, 0) + 1
    return dict(sorted(zahlen.items(), key=lambda p: -p[1]))
