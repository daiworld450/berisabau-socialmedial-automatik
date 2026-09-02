"""Tests für die Stellen des Telefonagenten, an denen ein Fehler teuer wird.

Es geht hier nicht um Vollständigkeit, sondern um die vier Fragen, deren
falsche Antwort einen rechtswidrigen Anruf auslöst:

1. Erkennt die Sperrliste dieselbe Nummer in anderer Schreibweise wieder?
   Steht "0208 123456" auf der Liste und die Datei sagt "+49208123456",
   würde ein Widerspruch wirkungslos verpuffen.
2. Sperrt freigabe.darf_anrufen() zuverlässig alles, was gesperrt gehört -
   Wochenende, Feiertag, Mobilnummer, zweiter Versuch, Tageslimit?
3. Greift die Widerspruchserkennung auch dann, wenn das Sprachmodell sein
   Werkzeug nicht aufruft?
4. Enthält der Eröffnungssatz die KI-Offenlegung? Fällt sie weg, ist jeder
   Anruf ein Verstoß gegen Art. 50 KI-VO, ohne dass es jemand merkt.

Kein Test geht ins Netz und keiner wählt. Sperrliste und Protokoll laufen in
ein Wegwerfverzeichnis.

Lauf:  .venv/bin/python -m unittest discover -s tests
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "telefon"))

import einstellungen  # noqa: E402
import gespraech  # noqa: E402
import nummern  # noqa: E402
import protokoll  # noqa: E402
import sperrliste  # noqa: E402
import zeitfenster  # noqa: E402


class TestNummern(unittest.TestCase):

    def test_gleiche_nummer_gleiche_form(self):
        """Alle üblichen Schreibweisen müssen auf dasselbe hinauslaufen."""
        formen = ["0208 1234567", "0208/1234567", "0208-123 45 67",
                  "+49 208 1234567", "+49 (0)208 1234567", "0049 208 1234567",
                  "  0208 1234567  "]
        ergebnisse = {nummern.normalisieren(f) for f in formen}
        self.assertEqual(ergebnisse, {"+492081234567"}, ergebnisse)

    def test_unbrauchbares_wird_abgewiesen(self):
        for schrott in ["", "   ", "keine Nummer", "1234", "0"]:
            with self.subTest(schrott=schrott):
                with self.assertRaises(nummern.NummernFehler):
                    nummern.normalisieren(schrott)

    def test_mobil_und_sonderrufnummern(self):
        self.assertTrue(nummern.ist_mobil(nummern.normalisieren("0151 23456789")))
        self.assertTrue(nummern.ist_mobil(nummern.normalisieren("0176 12345678")))
        self.assertFalse(nummern.ist_mobil(nummern.normalisieren("0208 1234567")))
        self.assertTrue(nummern.ist_verboten(nummern.normalisieren("0800 1234567")))
        self.assertTrue(nummern.ist_verboten(nummern.normalisieren("0900 1234567")))
        self.assertFalse(nummern.ist_verboten(nummern.normalisieren("0208 1234567")))


class TestSperrliste(unittest.TestCase):

    def setUp(self):
        self._ordner = TemporaryDirectory()
        self.datei = Path(self._ordner.name) / "sperrliste.json"

    def tearDown(self):
        self._ordner.cleanup()

    def test_widerspruch_wirkt_schreibweisenunabhaengig(self):
        """Der eigentliche Zweck der ganzen Normalisierung."""
        sperrliste.sperren("0208 123 45 67", "kein Interesse", "gespraech",
                           self.datei)
        for form in ["+492081234567", "0208/1234567", "0049 208 1234567"]:
            with self.subTest(form=form):
                self.assertTrue(sperrliste.gesperrt(form, self.datei))

    def test_unbrauchbare_nummer_gilt_als_gesperrt(self):
        """Im Zweifel nicht anrufen - wer weiß, wer da drangeht."""
        self.assertTrue(sperrliste.gesperrt("Unsinn", self.datei))

    def test_vorgeschichte_bleibt_erhalten(self):
        sperrliste.sperren("0208 1234567", "erster Grund", "gespraech",
                           self.datei)
        sperrliste.sperren("0208 1234567", "zweiter Grund", "telefon",
                           self.datei)
        eintrag = sperrliste.eintrag("0208 1234567", self.datei)
        self.assertEqual(eintrag["grund"], "erster Grund")
        self.assertEqual(len(eintrag["weitere"]), 1)
        self.assertEqual(eintrag["weitere"][0]["grund"], "zweiter Grund")

    def test_kaputte_datei_stoppt_statt_durchzuwinken(self):
        """Eine unlesbare Sperrliste darf nicht wie eine leere wirken."""
        self.datei.write_text("{kaputt", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            sperrliste.gesperrt("0208 1234567", self.datei)


class TestZeitfenster(unittest.TestCase):

    def test_erlaubte_und_gesperrte_zeiten(self):
        faelle = [
            (datetime(2026, 9, 7, 10, 0), True, "Montagvormittag"),
            (datetime(2026, 9, 7, 8, 30), False, "vor neun"),
            (datetime(2026, 9, 7, 12, 45), False, "Mittagspause"),
            (datetime(2026, 9, 7, 17, 30), False, "nach Feierabend"),
            (datetime(2026, 9, 4, 16, 0), False, "Freitagnachmittag"),
            (datetime(2026, 9, 5, 10, 0), False, "Samstag"),
            (datetime(2026, 9, 6, 10, 0), False, "Sonntag"),
            (datetime(2026, 6, 4, 10, 0), False, "Fronleichnam"),
            (datetime(2026, 1, 1, 10, 0), False, "Neujahr"),
        ]
        for zeitpunkt, erwartet, name in faelle:
            with self.subTest(name=name):
                self.assertEqual(zeitfenster.erlaubt(zeitpunkt)[0], erwartet)

    def test_ostern_stimmt(self):
        """Fünf bewegliche Feiertage hängen an diesem einen Datum."""
        self.assertEqual(zeitfenster._ostersonntag(2026), zeitfenster.date(2026, 4, 5))
        self.assertEqual(zeitfenster._ostersonntag(2027), zeitfenster.date(2027, 3, 28))
        self.assertEqual(zeitfenster._ostersonntag(2030), zeitfenster.date(2030, 4, 21))

    def test_naechstes_fenster_liegt_im_fenster(self):
        vom_samstag = zeitfenster.naechstes_fenster(
            datetime(2026, 9, 5, 10, 0, tzinfo=zeitfenster.ZEITZONE))
        self.assertTrue(zeitfenster.erlaubt(vom_samstag)[0])
        self.assertEqual(vom_samstag.weekday(), 0)


class TestFreigabe(unittest.TestCase):
    """Das Nadelöhr - hier muss jeder Ausschlussgrund einzeln greifen."""

    def setUp(self):
        self._ordner = TemporaryDirectory()
        ordner = Path(self._ordner.name)
        # Sperrliste und Protokoll auf Wegwerfdateien umbiegen. freigabe
        # greift über die Module darauf zu, deshalb reicht es, die Konstanten
        # in sperrliste und protokoll zu ersetzen.
        self._alte_sperr = sperrliste.SPERRLISTE_DATEI
        self._altes_prot = protokoll.PROTOKOLL_DATEI
        sperrliste.SPERRLISTE_DATEI = ordner / "sperrliste.json"
        protokoll.PROTOKOLL_DATEI = ordner / "anrufe.jsonl"
        # freigabe hat die Vorgabewerte beim Import gebunden.
        import freigabe
        self.freigabe = freigabe
        freigabe.sperrliste.SPERRLISTE_DATEI = sperrliste.SPERRLISTE_DATEI
        freigabe.protokoll.PROTOKOLL_DATEI = protokoll.PROTOKOLL_DATEI
        self.montag = datetime(2026, 9, 7, 10, 0)

    def tearDown(self):
        sperrliste.SPERRLISTE_DATEI = self._alte_sperr
        protokoll.PROTOKOLL_DATEI = self._altes_prot
        self._ordner.cleanup()

    def test_freie_nummer_kommt_durch(self):
        urteil = self.freigabe.darf_anrufen("0208 1234567", self.montag)
        self.assertTrue(urteil, urteil.grund)
        self.assertEqual(urteil.nummer, "+492081234567")

    def test_gesperrte_nummer_wird_gestoppt(self):
        sperrliste.sperren("0208 1234567", "kein Interesse", "gespraech",
                           sperrliste.SPERRLISTE_DATEI)
        urteil = self.freigabe.darf_anrufen("0208 1234567", self.montag)
        self.assertFalse(urteil)
        self.assertIn("gesperrt", urteil.grund)

    def test_mobilnummer_standardmaessig_gesperrt(self):
        urteil = self.freigabe.darf_anrufen("0151 23456789", self.montag)
        self.assertFalse(urteil)
        self.assertIn("Mobilnummer", urteil.grund)

    def test_sonderrufnummer_gesperrt(self):
        self.assertFalse(self.freigabe.darf_anrufen("0800 1234567", self.montag))
        self.assertFalse(self.freigabe.darf_anrufen("0900 1234567", self.montag))

    def test_wochenende_gesperrt(self):
        urteil = self.freigabe.darf_anrufen("0208 1234567",
                                            datetime(2026, 9, 5, 10, 0))
        self.assertFalse(urteil)
        self.assertIn("Anrufzeit", urteil.grund)

    def test_dritter_versuch_gesperrt(self):
        """MAX_VERSUCHE_JE_NUMMER ist 2 - der dritte Anruf ist Belästigung."""
        for _ in range(self.freigabe.e.MAX_VERSUCHE_JE_NUMMER):
            protokoll.eintragen("0208 1234567", ereignis="gewaehlt")
        urteil = self.freigabe.darf_anrufen("0208 1234567", self.montag)
        self.assertFalse(urteil)
        self.assertIn("Versuche", urteil.grund)

    def test_wiederwahl_zu_frueh_gesperrt(self):
        protokoll.eintragen("0208 1234567", ereignis="gewaehlt")
        urteil = self.freigabe.darf_anrufen("0208 1234567", self.montag)
        self.assertFalse(urteil)
        self.assertIn("Abstand", urteil.grund)

    def test_alter_versuch_blockiert_nicht_mehr(self):
        alt = (datetime.now(timezone.utc)
               - timedelta(days=self.freigabe.e.ABSTAND_TAGE + 1))
        protokoll.PROTOKOLL_DATEI.parent.mkdir(parents=True, exist_ok=True)
        protokoll.PROTOKOLL_DATEI.write_text(
            '{"zeit": "%s", "nummer": "+492081234567", "ereignis": "gewaehlt"}\n'
            % alt.isoformat(timespec="seconds"), encoding="utf-8")
        self.assertTrue(self.freigabe.darf_anrufen("0208 1234567", self.montag))

    def test_tageslimit_greift(self):
        for i in range(self.freigabe.e.MAX_ANRUFE_PRO_TAG):
            protokoll.eintragen("+4920812345%02d" % i, ereignis="gewaehlt")
        urteil = self.freigabe.darf_anrufen("0208 7654321", self.montag)
        self.assertFalse(urteil)
        self.assertIn("Tageslimit", urteil.grund)


class TestGespraech(unittest.TestCase):

    def test_offenlegung_steht_im_ersten_satz(self):
        """Art. 50 KI-VO. Fällt der Hinweis weg, merkt es sonst niemand."""
        eroeffnung = gespraech.EROEFFNUNG.lower()
        self.assertIn("ki", eroeffnung)
        self.assertIn("kein mensch", eroeffnung)
        self.assertIn(gespraech.ANGEBOT["firma"].lower(), eroeffnung)

    def test_widerspruch_wird_erkannt(self):
        saetze = [
            "Kein Interesse.",
            "Ich bin nicht interessiert.",
            "Rufen Sie hier nicht mehr an.",
            "Nie wieder anrufen!",
            "Löschen Sie meine Nummer.",
            "Streichen Sie mich aus Ihrer Liste.",
            "Ich widerspreche der Werbung.",
            "Das ist doch verboten.",
            "Ich gebe das meinem Anwalt.",
            "Das gibt eine Abmahnung.",
            "Sie belästigen mich.",
            "Lassen Sie mich in Ruhe.",
        ]
        for satz in saetze:
            with self.subTest(satz=satz):
                self.assertTrue(gespraech.ist_widerspruch(satz))

    def test_normales_gespraech_bricht_nicht_ab(self):
        """Ein zu scharfes Muster würde jedes Gespräch sofort beenden."""
        saetze = ["Ja, erzählen Sie mal.",
                  "Wir haben schon eine Webseite, aber die ist alt.",
                  "Wer sind Sie noch mal?",
                  "Schicken Sie mir das per Mail.",
                  "Interessant, was kostet das denn?"]
        for satz in saetze:
            with self.subTest(satz=satz):
                self.assertFalse(gespraech.ist_widerspruch(satz))

    def test_systemprompt_verbietet_menschbehauptung(self):
        prompt = gespraech.systemprompt({"betrieb": "Fliesen Muster"})
        self.assertIn("Fliesen Muster", prompt)
        self.assertIn("nie, ein Mensch zu sein", prompt)
        self.assertIn("keine Preise", prompt)

    def test_werkzeuge_vollstaendig(self):
        namen = {w["function"]["name"] for w in gespraech.werkzeuge()}
        self.assertEqual(namen, {"nicht_mehr_anrufen", "gespraech_beenden",
                                 "termin_notieren"})


class TestProtokoll(unittest.TestCase):

    def setUp(self):
        self._ordner = TemporaryDirectory()
        self._alt = protokoll.PROTOKOLL_DATEI
        protokoll.PROTOKOLL_DATEI = Path(self._ordner.name) / "anrufe.jsonl"

    def tearDown(self):
        protokoll.PROTOKOLL_DATEI = self._alt
        self._ordner.cleanup()

    def test_abgeschnittene_zeile_kippt_nicht_die_auswertung(self):
        protokoll.eintragen("0208 1234567", ereignis="gewaehlt")
        with protokoll.PROTOKOLL_DATEI.open("a", encoding="utf-8") as f:
            f.write('{"zeit": "2026-09-0')      # Absturz beim Schreiben
        protokoll.eintragen("0201 7654321", ereignis="gewaehlt")
        self.assertEqual(len(protokoll.lesen()), 2)

    def test_nur_gewaehlte_zaehlen_gegen_das_tageslimit(self):
        protokoll.eintragen("0208 1234567", ereignis="uebersprungen")
        protokoll.eintragen("0208 1234568", ereignis="offenlegung")
        protokoll.eintragen("0208 1234569", ereignis="gewaehlt")
        self.assertEqual(protokoll.anrufe_heute(), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
