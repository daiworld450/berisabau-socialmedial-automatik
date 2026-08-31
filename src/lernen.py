"""Kennzahlen nach 72 Stunden festhalten und Versuche nachhalten.

Zwei Dinge, die die Betriebsanweisung fordert und die vorher fehlten:

**Kennzahlen (Abschnitt 5.9).** `analyse.py` holt Zahlen live von Instagram -
das zeigt den Ist-Stand, aber nicht die Entwicklung. Hier wird je Beitrag
**einmal nach rund 72 Stunden** ein fester Stand weggeschrieben. Erst dadurch
lassen sich Beitraege ueberhaupt vergleichen: 72 Stunden ist der Punkt, an dem
die Erstausspielung durch ist und die Zahlen sich kaum noch bewegen.

**Lernprotokoll (Abschnitt 11).** Jede Aenderung an Format, Uhrzeit,
Hashtag-Satz oder Bildsprache ist ein Versuch mit Erwartung und Pruefdatum. Am
Pruefdatum wird eingetragen, was herauskam - auch wenn die Vermutung daneben
lag. Ohne das wiederholt man alle drei Monate dieselbe Idee.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from config import CONTENT_DIR, LOG_DATEI

KENNZAHLEN = CONTENT_DIR / "kennzahlen.json"
PROTOKOLL  = CONTENT_DIR / "lernprotokoll.json"

# Vorher ist die Erstausspielung noch im Gang, die Zahlen wandern dann noch.
REIFEZEIT_STUNDEN = 72


# --------------------------------------------------------------------------- #
# Kennzahlen
# --------------------------------------------------------------------------- #
def _lies(pfad: Path, leer: dict) -> dict:
    if not pfad.exists():
        return dict(leer)
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return dict(leer)


def _schreib(pfad: Path, daten: dict) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def veroeffentlichte() -> list[dict]:
    """Erfolgreiche Beitraege aus dem Protokoll, neueste zuerst."""
    if not LOG_DATEI.exists():
        return []
    eintraege = []
    for zeile in LOG_DATEI.read_text(encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        try:
            e = json.loads(zeile)
        except json.JSONDecodeError:
            continue
        if e.get("erfolg") and e.get("media_id"):
            eintraege.append(e)
    return sorted(eintraege, key=lambda e: e["zeitpunkt"], reverse=True)


def faellige() -> list[dict]:
    """Beitraege, die reif sind und noch keinen Eintrag haben."""
    daten = _lies(KENNZAHLEN, {"eintraege": {}})
    grenze = datetime.now() - timedelta(hours=REIFEZEIT_STUNDEN)
    return [e for e in veroeffentlichte()
            if datetime.fromisoformat(e["zeitpunkt"]) <= grenze
            and e["media_id"] not in daten["eintraege"]]


def nachtragen(trockenlauf: bool = False) -> str:
    """Fuer jeden reifen Beitrag den Stand einmal festschreiben."""
    offen = faellige()
    if not offen:
        return "Keine Beiträge fällig (alle jünger als 72 Stunden oder schon erfasst)."

    if trockenlauf:
        namen = ", ".join(e["thema"] for e in offen[:5])
        return f"{len(offen)} Beitrag/Beiträge fällig: {namen}"

    import analyse
    daten = _lies(KENNZAHLEN, {
        "_hinweis": (f"Stand je Beitrag, {REIFEZEIT_STUNDEN} Stunden nach der "
                     "Veröffentlichung. Einmalig, wird nicht überschrieben."),
        "eintraege": {}})

    erfasst, gescheitert = 0, []
    for e in offen:
        try:
            werte = analyse._hole_insights(e["media_id"])
        except Exception as fehler:
            gescheitert.append(f"{e['thema']}: {type(fehler).__name__}")
            continue
        daten["eintraege"][e["media_id"]] = {
            "thema": e["thema"],
            "veroeffentlicht": e["zeitpunkt"],
            "gemessen": datetime.now().isoformat(timespec="seconds"),
            "permalink": e.get("permalink"),
            "hashtag_satz": e.get("hashtag_satz"),
            "werte": werte,
        }
        erfasst += 1

    _schreib(KENNZAHLEN, daten)
    text = f"{erfasst} Beitrag/Beiträge nach 72 Stunden erfasst."
    if gescheitert:
        text += f"\n  Nicht abrufbar: {'; '.join(gescheitert)}"
    return text


def vergleich(anzahl: int = 10) -> str:
    """Die erfassten Beitraege gegeneinander - bester und schwaechster."""
    daten = _lies(KENNZAHLEN, {"eintraege": {}})
    eintraege = list(daten["eintraege"].values())
    if len(eintraege) < 2:
        return ("Noch zu wenige Messpunkte für einen Vergleich "
                f"({len(eintraege)}). Ab zwei wird es aussagekräftig.")

    def punkte(e: dict) -> int:
        w = e.get("werte") or {}
        # Profilbesuche zaehlen mehr als Reichweite: Sie sind der Schritt
        # Richtung Anfrage, und darauf kommt es an.
        return int(w.get("reach", 0)) + 5 * int(w.get("profile_visits", 0))

    sortiert = sorted(eintraege, key=punkte, reverse=True)[:anzahl]
    zeilen = ["Beiträge nach 72 Stunden, bester zuerst:", ""]
    for e in sortiert:
        w = e.get("werte") or {}
        zeilen.append(
            f"  {punkte(e):>6}  {e['thema'][:28]:28}  "
            f"Reichweite {w.get('reach', '?')}, "
            f"Profilbesuche {w.get('profile_visits', '?')}")
    return "\n".join(zeilen)


# --------------------------------------------------------------------------- #
# Lernprotokoll
# --------------------------------------------------------------------------- #
def versuch_anlegen(beobachtung: str, hypothese: str, massnahme: str,
                    erwartung: str, wochen: int = 4) -> dict:
    daten = _lies(PROTOKOLL, {
        "_hinweis": ("Jede Änderung an Format, Uhrzeit, Hashtags oder "
                     "Bildsprache ist ein Versuch. Am Prüfdatum wird das "
                     "Ergebnis eingetragen - auch wenn die Hypothese daneben lag."),
        "versuche": []})
    eintrag = {
        "nummer": len(daten["versuche"]) + 1,
        "datum": date.today().isoformat(),
        "beobachtung": beobachtung,
        "hypothese": hypothese,
        "massnahme": massnahme,
        "erwartung": erwartung,
        "pruefdatum": (date.today() + timedelta(weeks=wochen)).isoformat(),
        "ergebnis": "offen",
    }
    daten["versuche"].append(eintrag)
    _schreib(PROTOKOLL, daten)
    return eintrag


def versuch_abschliessen(nummer: int, ergebnis: str) -> bool:
    daten = _lies(PROTOKOLL, {"versuche": []})
    for v in daten["versuche"]:
        if v["nummer"] == nummer:
            v["ergebnis"] = ergebnis
            v["abgeschlossen_am"] = date.today().isoformat()
            _schreib(PROTOKOLL, daten)
            return True
    return False


def faellige_versuche() -> list[dict]:
    daten = _lies(PROTOKOLL, {"versuche": []})
    heute = date.today().isoformat()
    return [v for v in daten["versuche"]
            if v["ergebnis"] == "offen" and v["pruefdatum"] <= heute]


def protokoll_text() -> str:
    daten = _lies(PROTOKOLL, {"versuche": []})
    if not daten["versuche"]:
        return ("Noch kein Versuch festgehalten.\n"
                "Anlegen:  python src/main.py lernen --neu")

    zeilen = []
    for v in daten["versuche"]:
        marke = "offen" if v["ergebnis"] == "offen" else "fertig"
        faellig = " ← FÄLLIG" if v in faellige_versuche() else ""
        zeilen += [
            f"[{v['nummer']}] {v['datum']} · {marke}{faellig}",
            f"    Beobachtung: {v['beobachtung']}",
            f"    Hypothese:   {v['hypothese']}",
            f"    Maßnahme:    {v['massnahme']}",
            f"    Erwartung:   {v['erwartung']}",
            f"    Prüfdatum:   {v['pruefdatum']}",
            f"    Ergebnis:    {v['ergebnis']}",
            "",
        ]
    return "\n".join(zeilen)
