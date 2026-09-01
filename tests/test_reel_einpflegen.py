"""Tests für die Brücke vom Reel-Werk in die Automatik.

Der Befehl `reel-einpflegen` ist die einzige Stelle, an der eine Datei aus
dem per .gitignore gesperrten Ordner reelwerk/fertig/ in den versionierten
Ordner content/medien/projekte/ wandert. Zwei Dinge müssen deshalb sitzen:

1. **Die Größenbremse.** Ein Reel aus dem Reel-Werk wiegt rund 8 MB. Eine
   unbearbeitete Handydatei wiegt ein Vielfaches davon und hätte im Repo
   nichts verloren. Über MAX_REEL_MB bricht der Befehl ab und schreibt nichts.
2. **Das Ergebnis passt zum Planer.** planer._aus_video sucht ein Video im
   Ordner und ein Bild mit dem Präfix "cover" oder "nachher". Liegt am Ende
   etwas anderes dort, entsteht nie ein Beitrag - und das fällt sonst erst
   Wochen später auf, wenn ein Posttag leer bleibt.

Die Tests gehen nicht ins Netz und rufen kein echtes ffmpeg auf: der Auszug
des Titelbilds wird durch eine Attrappe ersetzt, die eine winzige Datei
schreibt. Wo ffmpeg fehlen soll, gibt die Attrappe False zurück.

Lauf:  .venv/bin/python -m unittest discover -s tests
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "src"))

import main      # noqa: E402
import planer    # noqa: E402


def _argumente(**abweichend) -> SimpleNamespace:
    """Dieselben Vorgaben, die argparse in main() setzt."""
    werte = {
        "datei": None,
        "name": None,
        "titel": None,
        "gewerk": "Sanierung",
        "ort": "Mülheim an der Ruhr",
        "hashtags": "sanierung",
        "titelbild": None,
        "sekunde": 0.0,
        "ueberschreiben": False,
        "trocken": False,
    }
    werte.update(abweichend)
    return SimpleNamespace(**werte)


class ReelEinpflegenBasis(unittest.TestCase):
    """Gemeinsamer Aufbau: eigener fertig-Ordner, eigener Projekte-Ordner."""

    def setUp(self):
        self._ordner = TemporaryDirectory()
        wurzel = Path(self._ordner.name)

        self._sicher = {
            "REELWERK_FERTIG": main.REELWERK_FERTIG,
            "PROJEKTE_DIR": main.PROJEKTE_DIR,
            "_titelbild_ziehen": main._titelbild_ziehen,
        }

        self.fertig = wurzel / "fertig"
        self.projekte = wurzel / "projekte"
        self.fertig.mkdir()
        main.REELWERK_FERTIG = self.fertig
        main.PROJEKTE_DIR = self.projekte

        self.ffmpeg_aufrufe: list[tuple] = []
        main._titelbild_ziehen = self._titelbild_attrappe
        self.titelbild_gelingt = True

        self.addCleanup(self._aufraeumen)

    def _titelbild_attrappe(self, video: Path, ziel: Path,
                            sekunde: float = 0.0) -> bool:
        """Statt ffmpeg: merkt sich den Aufruf und legt eine winzige Datei ab."""
        self.ffmpeg_aufrufe.append((Path(video), Path(ziel), sekunde))
        if not self.titelbild_gelingt:
            return False
        Path(ziel).write_bytes(b"\xff\xd8\xff\xd9")   # kleinstmögliches JPEG
        return True

    def _aufraeumen(self):
        for name, wert in self._sicher.items():
            setattr(main, name, wert)
        self._ordner.cleanup()

    def _reel(self, name: str = "Dichtband in jede Ecke.mp4",
              megabyte: float = 8.0) -> Path:
        pfad = self.fertig / name
        pfad.write_bytes(b"\0" * int(megabyte * 1024 * 1024))
        return pfad


class Groessenbremse(ReelEinpflegenBasis):
    """Über MAX_REEL_MB wird abgebrochen, bevor irgendetwas kopiert ist."""

    def test_zu_grosses_reel_gibt_1(self):
        self._reel("Rohclip vom Handy.mp4", megabyte=main.MAX_REEL_MB + 1)

        code = main.cmd_reel_einpflegen(
            _argumente(datei="Rohclip vom Handy.mp4"))

        self.assertEqual(code, 1)

    def test_zu_grosses_reel_kopiert_nichts(self):
        self._reel("Rohclip vom Handy.mp4", megabyte=main.MAX_REEL_MB + 1)

        main.cmd_reel_einpflegen(_argumente(datei="Rohclip vom Handy.mp4"))

        self.assertFalse(self.projekte.exists())
        self.assertEqual(self.ffmpeg_aufrufe, [])

    def test_knapp_unter_der_grenze_geht_durch(self):
        self._reel("Knapp drunter.mp4", megabyte=main.MAX_REEL_MB - 1)

        code = main.cmd_reel_einpflegen(_argumente(datei="Knapp drunter.mp4"))

        self.assertEqual(code, 0)
        self.assertTrue((self.projekte / "knapp-drunter" / "reel.mp4").exists())


class ErgebnisPasstZumPlaner(ReelEinpflegenBasis):
    """Was der Befehl ablegt, muss der Planer als Reel erkennen."""

    def test_video_titelbild_und_info_liegen_im_projektordner(self):
        self._reel()

        code = main.cmd_reel_einpflegen(
            _argumente(datei="Dichtband in jede Ecke.mp4"))

        ordner = self.projekte / "dichtband-in-jede-ecke"
        self.assertEqual(code, 0)
        self.assertTrue((ordner / "reel.mp4").exists())
        self.assertTrue((ordner / "cover.jpg").exists())
        self.assertTrue((ordner / "info.json").exists())

    def test_planer_erkennt_den_ordner_als_reel(self):
        self._reel()
        main.cmd_reel_einpflegen(_argumente(datei="Dichtband in jede Ecke.mp4"))

        echt = planer.PROJEKTE_DIR
        planer.PROJEKTE_DIR = self.projekte
        try:
            mit_video = planer.projekte_mit_video()
            self.assertEqual([o.name for o in mit_video],
                             ["dichtband-in-jede-ecke"])
            # Genau der Weg, den planer.plane() an einem Reel-Tag nimmt.
            plan = planer._aus_video(mit_video[0], main.date.today())
        finally:
            planer.PROJEKTE_DIR = echt

        self.assertEqual(plan["typ"], "reel")
        self.assertTrue(plan["video"].endswith("reel.mp4"))
        self.assertTrue(plan["titelbild"].endswith("cover.jpg"))

    def test_info_json_traegt_titel_gewerk_und_ort(self):
        self._reel()

        main.cmd_reel_einpflegen(
            _argumente(datei="Dichtband in jede Ecke.mp4",
                       gewerk="Badsanierung", ort="Essen"))

        info = json.loads(
            (self.projekte / "dichtband-in-jede-ecke" / "info.json")
            .read_text(encoding="utf-8"))
        self.assertEqual(info["titel"], "Dichtband in jede Ecke")
        self.assertEqual(info["gewerk"], "Badsanierung")
        self.assertEqual(info["ort"], "Essen")

    def test_zweiter_lauf_laesst_eine_gepflegte_info_json_stehen(self):
        self._reel()
        main.cmd_reel_einpflegen(_argumente(datei="Dichtband in jede Ecke.mp4"))

        datei = self.projekte / "dichtband-in-jede-ecke" / "info.json"
        info = json.loads(datei.read_text(encoding="utf-8"))
        info["caption"] = "Von Hand geschrieben."
        info["gewerk"] = "Badsanierung"
        datei.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")

        main.cmd_reel_einpflegen(
            _argumente(datei="Dichtband in jede Ecke.mp4",
                       ueberschreiben=True, gewerk="Sanierung"))

        danach = json.loads(datei.read_text(encoding="utf-8"))
        self.assertEqual(danach["caption"], "Von Hand geschrieben.")
        self.assertEqual(danach["gewerk"], "Badsanierung")


class NameUndQuelle(ReelEinpflegenBasis):
    """Ordnername aus dem Dateinamen oder aus --name."""

    def test_umlaute_werden_umgeschrieben(self):
        self._reel("Estrich für die Dusche.mp4")

        main.cmd_reel_einpflegen(_argumente(datei="Estrich für die Dusche.mp4"))

        self.assertTrue(
            (self.projekte / "estrich-fuer-die-dusche" / "reel.mp4").exists())

    def test_name_argument_schlaegt_den_dateinamen(self):
        self._reel("IMG_4711.mp4")

        main.cmd_reel_einpflegen(
            _argumente(datei="IMG_4711.mp4", name="Bad Heiermannstr."))

        self.assertTrue(
            (self.projekte / "bad-heiermannstr" / "reel.mp4").exists())

    def test_unbekannte_datei_gibt_1(self):
        self.assertEqual(
            main.cmd_reel_einpflegen(_argumente(datei="gibt-es-nicht.mp4")), 1)
        self.assertFalse(self.projekte.exists())

    def test_kein_video_gibt_1(self):
        (self.fertig / "notiz.txt").write_text("kein Video", encoding="utf-8")

        self.assertEqual(
            main.cmd_reel_einpflegen(_argumente(datei="notiz.txt")), 1)
        self.assertFalse(self.projekte.exists())

    def test_ohne_datei_wird_nur_aufgelistet(self):
        self._reel()

        code = main.cmd_reel_einpflegen(_argumente())

        self.assertEqual(code, 0)
        self.assertFalse(self.projekte.exists())

    def test_vorhandenes_reel_wird_ohne_ueberschreiben_nicht_ersetzt(self):
        self._reel()
        main.cmd_reel_einpflegen(_argumente(datei="Dichtband in jede Ecke.mp4"))
        ziel = self.projekte / "dichtband-in-jede-ecke" / "reel.mp4"
        ziel.write_bytes(b"unberuehrt")

        code = main.cmd_reel_einpflegen(
            _argumente(datei="Dichtband in jede Ecke.mp4"))

        self.assertEqual(code, 1)
        self.assertEqual(ziel.read_bytes(), b"unberuehrt")

    def test_trockenlauf_schreibt_nichts(self):
        self._reel()

        code = main.cmd_reel_einpflegen(
            _argumente(datei="Dichtband in jede Ecke.mp4", trocken=True))

        self.assertEqual(code, 0)
        self.assertFalse(self.projekte.exists())
        self.assertEqual(self.ffmpeg_aufrufe, [])


class TitelbildFehlt(ReelEinpflegenBasis):
    """Ohne ffmpeg gibt es kein Titelbild - und das muss auffallen."""

    def test_misslungener_auszug_gibt_1(self):
        self.titelbild_gelingt = False
        self._reel()

        code = main.cmd_reel_einpflegen(
            _argumente(datei="Dichtband in jede Ecke.mp4"))

        ordner = self.projekte / "dichtband-in-jede-ecke"
        self.assertEqual(code, 1)
        self.assertFalse((ordner / "cover.jpg").exists())
        # Das Video liegt trotzdem da - nachtragen muss man nur das Bild.
        self.assertTrue((ordner / "reel.mp4").exists())

    def test_eigenes_titelbild_kommt_ohne_ffmpeg_aus(self):
        self.titelbild_gelingt = False
        self._reel()
        eigenes = Path(self._ordner.name) / "eigenes.jpg"
        eigenes.write_bytes(b"\xff\xd8\xff\xd9")

        code = main.cmd_reel_einpflegen(
            _argumente(datei="Dichtband in jede Ecke.mp4",
                       titelbild=str(eigenes)))

        self.assertEqual(code, 0)
        self.assertEqual(self.ffmpeg_aufrufe, [])
        self.assertTrue(
            (self.projekte / "dichtband-in-jede-ecke" / "cover.jpg").exists())


class TitelbildAuszug(unittest.TestCase):
    """_titelbild_ziehen selbst, ohne dass ffmpeg da sein muss."""

    def test_ohne_ffmpeg_kein_titelbild(self):
        echt = main._ffmpeg
        main._ffmpeg = lambda: None
        try:
            with TemporaryDirectory() as ordner:
                ziel = Path(ordner) / "cover.jpg"
                self.assertFalse(
                    main._titelbild_ziehen(Path(ordner) / "reel.mp4", ziel))
                self.assertFalse(ziel.exists())
        finally:
            main._ffmpeg = echt


if __name__ == "__main__":
    unittest.main()
