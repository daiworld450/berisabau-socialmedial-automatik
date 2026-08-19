"""Optionale Freigabe-Sperre.

Standard ist volle Automatik. Wer lieber jeden Beitrag vorher sehen will,
setzt FREIGABE_PFLICHT=true in der .env bzw. als Repository-Variable.
Dann veröffentlicht die Automatik nur, was hier eingetragen ist.
"""
from __future__ import annotations

import json
from datetime import datetime

from config import CONTENT_DIR

DATEI = CONTENT_DIR / "freigaben.json"


def _lade() -> dict:
    if DATEI.exists():
        return json.loads(DATEI.read_text(encoding="utf-8"))
    return {"freigegeben": {}}


def _speichere(daten: dict) -> None:
    DATEI.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")


def freigeben(thema_id: str) -> None:
    daten = _lade()
    daten["freigegeben"][thema_id] = datetime.now().isoformat(timespec="seconds")
    _speichere(daten)


def zuruecknehmen(thema_id: str) -> None:
    daten = _lade()
    daten["freigegeben"].pop(thema_id, None)
    _speichere(daten)


def ist_frei(thema_id: str) -> bool:
    return thema_id in _lade()["freigegeben"]


def alle() -> dict[str, str]:
    return _lade()["freigegeben"]
