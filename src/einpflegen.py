"""Nimmt geprüfte Themen aus JSON-Dateien in content/themen.json auf.

Getrennt vom Rest, weil das Einpflegen ein seltener, aber heikler Vorgang ist:
Bestehende Themen dürfen dabei nie überschrieben werden, und alles Neue muss
durch dieselbe Selbstprüfung wie der Bestand.
"""
from __future__ import annotations

import json
from pathlib import Path

from config import CONTENT_DIR

THEMEN_DATEI = CONTENT_DIR / "themen.json"
PFLICHTFELDER = {"id", "rubrik", "vorlage", "gewerk", "hashtags", "felder", "caption"}
ERLAUBTE_RUBRIKEN = {"wissen", "fehler", "detail", "mensch", "vorher-nachher"}
ERLAUBTE_VORLAGEN = {"tipp.html", "faq.html", "leistung.html", "zitat.html"}


def _pruefe_struktur(thema: dict) -> list[str]:
    fehler = []
    fehlend = PFLICHTFELDER - thema.keys()
    if fehlend:
        fehler.append(f"Pflichtfelder fehlen: {', '.join(sorted(fehlend))}")
    if thema.get("rubrik") not in ERLAUBTE_RUBRIKEN:
        fehler.append(f"unbekannte Rubrik: {thema.get('rubrik')}")
    if thema.get("vorlage") not in ERLAUBTE_VORLAGEN:
        fehler.append(f"unbekannte Vorlage: {thema.get('vorlage')}")

    f = thema.get("felder", {})
    if thema.get("vorlage") == "faq.html":
        if not f.get("frage") or not f.get("antwort"):
            fehler.append("faq.html ohne frage/antwort")
    else:
        punkte = f.get("punkte", [])
        if len(punkte) != 3:
            fehler.append(f"{len(punkte)} Stichpunkte statt 3")
    return fehler


def einpflegen(dateien: list[Path], trockenlauf: bool = False) -> dict:
    bestand = json.loads(THEMEN_DATEI.read_text(encoding="utf-8"))
    vorhanden = {t["id"] for t in bestand["themen"]}

    neu, abgelehnt, doppelt = [], [], []

    for datei in dateien:
        if not datei.exists():
            abgelehnt.append((str(datei), ["Datei nicht gefunden"]))
            continue
        inhalt = json.loads(datei.read_text(encoding="utf-8"))
        themen = inhalt if isinstance(inhalt, list) else inhalt.get("themen", [])

        for thema in themen:
            probleme = _pruefe_struktur(thema)
            if probleme:
                abgelehnt.append((thema.get("id", "?"), probleme))
                continue
            if thema["id"] in vorhanden:
                doppelt.append(thema["id"])
                continue
            vorhanden.add(thema["id"])
            neu.append(thema)

    if neu and not trockenlauf:
        bestand["themen"].extend(neu)
        THEMEN_DATEI.write_text(
            json.dumps(bestand, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "neu": [t["id"] for t in neu],
        "abgelehnt": abgelehnt,
        "doppelt": doppelt,
        "gesamt_danach": len(bestand["themen"]) + (0 if not trockenlauf else len(neu)),
    }
