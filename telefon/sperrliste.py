"""Nummern, die nie (wieder) angerufen werden.

Das ist der wichtigste Teil des Telefonagenten. Ein Widerspruch muss sofort,
dauerhaft und ohne Umweg über einen Menschen wirken - ein zweiter Anruf nach
einem "Nein" ist der Fall, der Abmahnungen und Bußgelder auslöst, nicht der
erste Anruf.

Deshalb:
  - Eintragen ist unwiderruflich. Es gibt bewusst keine entfernen()-Funktion.
    Wer eine Nummer wieder freigeben will, greift von Hand in die Datei und
    trifft diese Entscheidung sichtbar.
  - Geprüft wird zweimal: beim Zusammenstellen der Wahlliste und noch einmal
    unmittelbar vor dem Wählen. Zwischen beiden Zeitpunkten kann ein Anruf
    von gestern einen Widerspruch erzeugt haben.
  - Die Datei ist Nachweis. Wer behauptet, er habe widersprochen, wird hier
    mit Zeitstempel und Grund gefunden.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from einstellungen import SPERRLISTE_DATEI
from nummern import NummernFehler, normalisieren

log = logging.getLogger(__name__)

# Der Wähler läuft mit mehreren Leitungen; zwei gleichzeitige Einträge dürfen
# sich nicht gegenseitig überschreiben.
_schloss = threading.Lock()


def _ziel(datei: Path | None) -> Path:
    """Pfad erst beim Aufruf auflösen - siehe protokoll._ziel().

    Hier wiegt es schwerer als dort: Eine Sperrliste, die beim Schreiben auf
    eine andere Datei zeigt als beim Lesen, lässt jeden Widerspruch ins Leere
    laufen, ohne dass irgendetwas nach Fehler aussieht.
    """
    return datei or SPERRLISTE_DATEI



def _laden(datei: Path | None = None) -> dict[str, dict]:
    datei = _ziel(datei)
    if not datei.exists():
        return {}
    try:
        with datei.open(encoding="utf-8") as f:
            daten = json.load(f)
    except (json.JSONDecodeError, OSError) as fehler:
        # Eine unlesbare Sperrliste darf nicht dazu führen, dass munter
        # weitergewählt wird. Lieber laut scheitern.
        raise RuntimeError(
            f"Sperrliste {datei} ist nicht lesbar ({fehler}). "
            "Solange das so ist, wird nicht gewählt."
        ) from fehler
    return daten.get("nummern", {})


def _speichern(nummern: dict[str, dict], datei: Path | None = None) -> None:
    datei = _ziel(datei)
    datei.parent.mkdir(parents=True, exist_ok=True)
    # Erst daneben schreiben, dann umbenennen: Ein Absturz mitten im Schreiben
    # darf die Liste nicht halbieren.
    vorlaeufig = datei.with_suffix(".json.neu")
    with vorlaeufig.open("w", encoding="utf-8") as f:
        json.dump({"nummern": nummern}, f, ensure_ascii=False, indent=2)
    vorlaeufig.replace(datei)


def sperren(rohnummer: str, grund: str, quelle: str = "gespraech",
            datei: Path | None = None) -> str:
    """Nummer dauerhaft sperren. Gibt die normalisierte Nummer zurück.

    Mehrfaches Sperren ist harmlos: Der erste Eintrag bleibt stehen, spätere
    Gründe werden angehängt, damit die Vorgeschichte lesbar bleibt.
    """
    nummer = normalisieren(rohnummer)
    jetzt = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _schloss:
        nummern = _laden(datei)
        eintrag = nummern.get(nummer)
        if eintrag is None:
            nummern[nummer] = {
                "gesperrt_am": jetzt,
                "grund": grund,
                "quelle": quelle,
                "weitere": [],
            }
        else:
            eintrag.setdefault("weitere", []).append(
                {"am": jetzt, "grund": grund, "quelle": quelle}
            )
        _speichern(nummern, datei)
    log.info("gesperrt: %s (%s)", nummer, grund)
    return nummer


def gesperrt(rohnummer: str, datei: Path | None = None) -> bool:
    """True, wenn die Nummer nicht angerufen werden darf.

    Eine Nummer, die sich nicht normalisieren lässt, gilt als gesperrt. Wenn
    unklar ist, wen man da anruft, ruft man nicht an.
    """
    try:
        nummer = normalisieren(rohnummer)
    except NummernFehler:
        return True
    return nummer in _laden(datei)


def eintrag(rohnummer: str, datei: Path | None = None) -> dict | None:
    """Sperrgrund und Zeitpunkt - für die Auskunft, wenn jemand nachfragt."""
    try:
        nummer = normalisieren(rohnummer)
    except NummernFehler:
        return None
    return _laden(datei).get(nummer)


def alle(datei: Path | None = None) -> dict[str, dict]:
    return _laden(datei)


def einlesen(pfad: Path, grund: str = "Import", quelle: str = "datei",
             datei: Path | None = None) -> tuple[int, list[str]]:
    """Eine Textdatei mit einer Rufnummer je Zeile einlesen.

    Gedacht für Bestandslisten: Kunden, die schon widersprochen haben, eigene
    Nummern, Wettbewerber. Gibt (übernommen, fehlerhafte Zeilen) zurück.
    """
    uebernommen, fehler = 0, []
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        zeile = zeile.split("#", 1)[0].strip()
        if not zeile:
            continue
        try:
            sperren(zeile, grund, quelle, datei)
            uebernommen += 1
        except NummernFehler as f:
            fehler.append(f"{zeile}: {f}")
    return uebernommen, fehler
