"""Tests für die drei Stellen, an denen ein Fehler bisher still bleibt.

Warum genau diese drei:

1. planer.plane() muss bei gleichem Tag und gleicher Ausschlussliste denselben
   Kandidaten liefern. Darauf baut cmd_freigabe_vorbereiten: der Worker schickt
   nur eine plan_id, der Rest wird aus Tag plus Ausschlussliste rekonstruiert.
   Wäre plane() nicht deterministisch, käme ein anderer Beitrag heraus als der,
   den der Inhaber im Chat gesehen hat.
2. Die Warteschlange trägt seit dem 28.08.2026 zwei getrennte Zähler. Beim
   Laden wird das alte Feld letzte_update_id umgeschrieben. Geht das schief,
   fängt der Bot bei 0 an und arbeitet alte Tastendrücke nach.
3. cmd_freigabe_vorbereiten muss bei unbekannter plan_id abbrechen, statt
   irgendetwas zu rendern oder freizugeben.

Die Tests gehen nicht ins Netz und rendern nichts. Alles, was rendern oder
veröffentlichen würde, wird vorher durch eine Attrappe ersetzt, die beim
Aufruf sofort durchfällt.

Lauf:  .venv/bin/python -m unittest discover -s tests
       .venv/bin/python -m pytest tests/     (falls pytest da ist)

In dieser .venv (Python 3.9.6) ist pytest nicht installiert, deshalb ist
unittest aus der Standardbibliothek der Weg, der ohne Nachinstallieren geht.
Die Tests laufen unter beiden Werkzeugen, sie benutzen nur unittest-Mittel.
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "src"))

import main      # noqa: E402
import planer    # noqa: E402


def _erster_posttag() -> date:
    """Der nächste Tag, für den der Planer überhaupt etwas vorsieht."""
    heute = date.today()
    for i in range(21):
        tag = heute + timedelta(days=i)
        if planer.plane(tag) is not None:
            return tag
    raise unittest.SkipTest(
        "In den nächsten drei Wochen sieht content/themen.json keinen "
        "Posttag vor - ohne Posttag lässt sich plane() nicht prüfen.")


class PlanerIstDeterministisch(unittest.TestCase):
    """plane() darf bei gleicher Eingabe nicht zwischen Kandidaten schwanken."""

    def test_gleicher_tag_gleiche_ausschlussliste_gleicher_kandidat(self):
        tag = _erster_posttag()
        ausschluss = {"gibt-es-nicht-1", "gibt-es-nicht-2"}

        erst = planer.plane(tag, ausschluss=set(ausschluss))
        zweit = planer.plane(tag, ausschluss=set(ausschluss))

        self.assertIsNotNone(erst)
        self.assertIsNotNone(zweit)
        self.assertEqual(erst["id"], zweit["id"])

    def test_ohne_ausschluss_stabil(self):
        tag = _erster_posttag()
        self.assertEqual(planer.plane(tag)["id"], planer.plane(tag)["id"])

    def test_ausgeschlossener_kandidat_kommt_nicht_wieder(self):
        """Genau der Schritt, den die Ablehn-Taste auslöst."""
        tag = _erster_posttag()
        erst = planer.plane(tag)
        self.assertIsNotNone(erst)

        zweit = planer.plane(tag, ausschluss={erst["id"]})
        if zweit is not None:
            self.assertNotEqual(erst["id"], zweit["id"])

    def test_wachsende_ausschlussliste_bleibt_reproduzierbar(self):
        """Die Schleife aus telegram-abfragen: ablehnen, ablehnen, freigeben.

        cmd_freigabe_vorbereiten spielt genau diesen Zustand später aus der
        gespeicherten Ausschlussliste nach.
        """
        tag = _erster_posttag()
        ausschluss: set[str] = set()
        verlauf: list[str] = []

        for _ in range(3):
            plan = planer.plane(tag, ausschluss=set(ausschluss))
            if plan is None:
                break
            verlauf.append(plan["id"])
            ausschluss.add(plan["id"])

        # Dieselbe Liste noch einmal, Schritt für Schritt nachgestellt.
        nachgestellt: set[str] = set()
        for erwartet in verlauf:
            plan = planer.plane(tag, ausschluss=set(nachgestellt))
            self.assertIsNotNone(plan)
            self.assertEqual(plan["id"], erwartet)
            nachgestellt.add(plan["id"])


class WarteschlangeLaden(unittest.TestCase):
    """_warteschlange_laden() samt Migration des alten Zählerformats."""

    def setUp(self):
        self._ordner = TemporaryDirectory()
        self._echt = main.WARTESCHLANGE_DATEI
        self.datei = Path(self._ordner.name) / "telegram_warteschlange.json"
        main.WARTESCHLANGE_DATEI = self.datei
        self.addCleanup(self._aufraeumen)

    def _aufraeumen(self):
        main.WARTESCHLANGE_DATEI = self._echt
        self._ordner.cleanup()

    def _schreibe(self, daten: dict) -> None:
        self.datei.write_text(json.dumps(daten, ensure_ascii=False),
                              encoding="utf-8")

    def test_fehlende_datei_liefert_leeres_geruest(self):
        daten = main._warteschlange_laden()
        self.assertEqual(daten["letzte_update_id_social"], 0)
        self.assertEqual(daten["letzte_update_id_ads"], 0)
        self.assertEqual(daten["wartend"], {})

    def test_altes_feld_wird_auf_den_social_zaehler_umgeschrieben(self):
        self._schreibe({"letzte_update_id": 252660748, "wartend": {}})

        daten = main._warteschlange_laden()

        self.assertEqual(daten["letzte_update_id_social"], 252660748)
        self.assertEqual(daten["letzte_update_id_ads"], 0)
        self.assertNotIn("letzte_update_id", daten)

    def test_migration_laesst_offene_vorschlaege_unangetastet(self):
        self._schreibe({
            "letzte_update_id": 42,
            "wartend": {"2026-09-03": {"plan_id": "w-silikon",
                                       "nachricht_id": 7,
                                       "abgelehnt": ["w-gefaelle"]}},
        })

        daten = main._warteschlange_laden()

        eintrag = daten["wartend"]["2026-09-03"]
        self.assertEqual(eintrag["plan_id"], "w-silikon")
        self.assertEqual(eintrag["abgelehnt"], ["w-gefaelle"])

    def test_neues_format_wird_nicht_angefasst(self):
        self._schreibe({"letzte_update_id_social": 131777223,
                        "letzte_update_id_ads": 9, "wartend": {}})

        daten = main._warteschlange_laden()

        self.assertEqual(daten["letzte_update_id_social"], 131777223)
        self.assertEqual(daten["letzte_update_id_ads"], 9)

    def test_beide_felder_nebeneinander_der_neue_zaehler_gewinnt(self):
        """Kann in einem halb migrierten Stand vorkommen. Der alte Wert darf
        den bereits korrigierten Social-Zähler nicht überschreiben."""
        self._schreibe({"letzte_update_id": 252660748,
                        "letzte_update_id_social": 131777223,
                        "letzte_update_id_ads": 0, "wartend": {}})

        daten = main._warteschlange_laden()

        self.assertEqual(daten["letzte_update_id_social"], 131777223)

    def test_speichern_und_laden_bleibt_gleich(self):
        original = {"letzte_update_id_social": 5, "letzte_update_id_ads": 6,
                    "wartend": {"2026-09-03": {"plan_id": "w-abdichtung",
                                               "nachricht_id": 11,
                                               "abgelehnt": []}}}
        main._warteschlange_speichern(original)

        self.assertEqual(main._warteschlange_laden(), original)


class _Gerendert(AssertionError):
    """Fliegt, sobald eine Attrappe angefasst wird, die nichts tun dürfte."""


class FreigabeVorbereitenBrichtAb(unittest.TestCase):
    """Unbekannte plan_id: Rückgabewert 1, und nichts gerendert."""

    def setUp(self):
        self._ordner = TemporaryDirectory()
        ordner = Path(self._ordner.name)

        self._sicher = {
            "WARTESCHLANGE_DATEI": main.WARTESCHLANGE_DATEI,
            "OUT_DIR": main.OUT_DIR,
            "_erzeuge": main._erzeuge,
            "_erzeuge_alle": main._erzeuge_alle,
            "_schreibe_caption": main._schreibe_caption,
            "_kopiere_video": main._kopiere_video,
            "freigaben": main.freigaben,
        }

        self.datei = ordner / "telegram_warteschlange.json"
        self.out = ordner / "out"
        self.out.mkdir()

        main.WARTESCHLANGE_DATEI = self.datei
        main.OUT_DIR = self.out
        for name in ("_erzeuge", "_erzeuge_alle", "_schreibe_caption",
                     "_kopiere_video"):
            setattr(main, name, self._falle(name))
        main.freigaben = SimpleNamespace(freigeben=self._falle("freigeben"))

        self.addCleanup(self._aufraeumen)

    def _falle(self, name: str):
        def attrappe(*_a, **_k):
            raise _Gerendert(f"{name}() wurde aufgerufen, darf es aber nicht")
        return attrappe

    def _aufraeumen(self):
        for name, wert in self._sicher.items():
            setattr(main, name, wert)
        self._ordner.cleanup()

    def _schlange(self, daten: dict) -> None:
        self.datei.write_text(json.dumps(daten, ensure_ascii=False),
                              encoding="utf-8")

    def test_unbekannte_plan_id_gibt_1(self):
        self._schlange({"letzte_update_id_social": 0, "letzte_update_id_ads": 0,
                        "wartend": {"2026-09-03": {"plan_id": "w-silikon",
                                                   "nachricht_id": 7,
                                                   "abgelehnt": []}}})

        code = main.cmd_freigabe_vorbereiten(
            SimpleNamespace(plan_id="gibt-es-nicht"))

        self.assertEqual(code, 1)

    def test_unbekannte_plan_id_rendert_nichts(self):
        self._schlange({"letzte_update_id_social": 0, "letzte_update_id_ads": 0,
                        "wartend": {"2026-09-03": {"plan_id": "w-silikon",
                                                   "nachricht_id": 7,
                                                   "abgelehnt": []}}})

        main.cmd_freigabe_vorbereiten(SimpleNamespace(plan_id="gibt-es-nicht"))

        self.assertFalse((self.out / "_freigegeben.json").exists())

    def test_unbekannte_plan_id_laesst_die_warteschlange_stehen(self):
        vorher = {"letzte_update_id_social": 3, "letzte_update_id_ads": 0,
                  "wartend": {"2026-09-03": {"plan_id": "w-silikon",
                                             "nachricht_id": 7,
                                             "abgelehnt": ["w-gefaelle"]}}}
        self._schlange(vorher)

        main.cmd_freigabe_vorbereiten(SimpleNamespace(plan_id="gibt-es-nicht"))

        self.assertEqual(json.loads(self.datei.read_text(encoding="utf-8")),
                         vorher)

    def test_leere_plan_id_gibt_1(self):
        self._schlange({"letzte_update_id_social": 0, "letzte_update_id_ads": 0,
                        "wartend": {}})

        self.assertEqual(
            main.cmd_freigabe_vorbereiten(SimpleNamespace(plan_id="")), 1)
        self.assertEqual(
            main.cmd_freigabe_vorbereiten(SimpleNamespace(plan_id="   ")), 1)
        self.assertEqual(
            main.cmd_freigabe_vorbereiten(SimpleNamespace(plan_id=None)), 1)

    def test_leere_warteschlange_gibt_1(self):
        self._schlange({"letzte_update_id_social": 0, "letzte_update_id_ads": 0,
                        "wartend": {}})

        self.assertEqual(
            main.cmd_freigabe_vorbereiten(SimpleNamespace(plan_id="w-silikon")),
            1)


if __name__ == "__main__":
    unittest.main()


class WarteschlangeBleibtBisVeroeffentlicht(unittest.TestCase):
    """Der Vorschlag darf erst verschwinden, wenn der Beitrag draussen ist.

    Am 03.09.2026 gab der Inhaber 'm-werkzeug' frei. Der Lauf renderte,
    trug den Vorschlag aus - und brach danach ab, bevor irgendetwas bei
    Instagram oder Facebook ankam. Damit war der Beitrag weder
    veroeffentlicht noch ein zweites Mal freigebbar: der Eintrag mit Tag
    und Ausschlussliste war fort, und ohne ihn verweigert
    cmd_freigabe_vorbereiten die Arbeit.
    """

    def setUp(self):
        self._ordner = TemporaryDirectory()
        ordner = Path(self._ordner.name)
        self._sicher = {n: getattr(main, n) for n in (
            "WARTESCHLANGE_DATEI", "OUT_DIR", "_erzeuge", "_erzeuge_alle",
            "_schreibe_caption", "_kopiere_video", "_veroeffentliche",
            "freigaben", "planer")}

        # main faengt beim Import einen ImportError ab und setzt dann
        # freigaben/planer/texter auf None - auf diesem Rechner fehlt eine
        # der drei Abhaengigkeiten. Der Planer wird hier echt gebraucht.
        main.planer = planer

        self.datei = ordner / "telegram_warteschlange.json"
        self.out = ordner / "out"
        self.out.mkdir()
        main.WARTESCHLANGE_DATEI = self.datei
        main.OUT_DIR = self.out

        self.tag = date(2026, 9, 3)
        plan = planer.plane(self.tag, ausschluss=set())
        self.plan_id = plan["id"]

        def erzeuge(*_a, **_k):
            bild = self.out / f"{self.tag.isoformat()}_{self.plan_id}.jpg"
            bild.write_bytes(b"jpg")
            return bild

        main._erzeuge = erzeuge
        main._erzeuge_alle = lambda *_a, **_k: [erzeuge()]
        main._schreibe_caption = lambda *_a, **_k: None
        main._kopiere_video = lambda *_a, **_k: erzeuge()
        main.freigaben = SimpleNamespace(freigeben=lambda *_a, **_k: None)
        self.addCleanup(self._aufraeumen)

    def _aufraeumen(self):
        for name, wert in self._sicher.items():
            setattr(main, name, wert)
        self._ordner.cleanup()

    def _schlange_mit_eintrag(self):
        self.datei.write_text(json.dumps({
            "letzte_update_id_social": 0, "letzte_update_id_ads": 0,
            "wartend": {self.tag.isoformat(): {"plan_id": self.plan_id,
                                               "nachricht_id": 39,
                                               "abgelehnt": []}}}),
            encoding="utf-8")

    def _wartend(self):
        return json.loads(self.datei.read_text(encoding="utf-8"))["wartend"]

    def test_rendern_allein_traegt_den_vorschlag_nicht_aus(self):
        self._schlange_mit_eintrag()

        code = main.cmd_freigabe_vorbereiten(
            SimpleNamespace(plan_id=self.plan_id))

        self.assertEqual(code, 0)
        self.assertIn(self.tag.isoformat(), self._wartend(),
                      "Vorschlag wurde schon vor der Veroeffentlichung "
                      "ausgetragen - genau der Fehler vom 03.09.2026")

    def test_nach_erfolgreicher_veroeffentlichung_ist_er_weg(self):
        self._schlange_mit_eintrag()
        main.cmd_freigabe_vorbereiten(SimpleNamespace(plan_id=self.plan_id))
        main._veroeffentliche = lambda *_a, **_k: 0

        code = main.cmd_telegram_veroeffentlichen(SimpleNamespace())

        self.assertEqual(code, 0)
        self.assertNotIn(self.tag.isoformat(), self._wartend())

    def test_gescheiterte_veroeffentlichung_laesst_ihn_stehen(self):
        self._schlange_mit_eintrag()
        main.cmd_freigabe_vorbereiten(SimpleNamespace(plan_id=self.plan_id))
        main._veroeffentliche = lambda *_a, **_k: 1

        code = main.cmd_telegram_veroeffentlichen(SimpleNamespace())

        self.assertEqual(code, 1)
        self.assertIn(self.tag.isoformat(), self._wartend(),
                      "Nach einem Fehlschlag muss der Vorschlag erneut "
                      "freigebbar bleiben")
