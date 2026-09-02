"""Tests für das Clip-Werk – Twitch-Stream zu TikTok/Reels/Shorts.

Geprüft wird das, was schiefgehen kann, ohne dass es auffällt:

* **Die Zeitachse.** Wird Stille herausgeschnitten, verschiebt sich alles
  dahinter. Stimmt `clipzeit` nicht, laufen Untertitel und Schnittmarken im
  fertigen Video daneben – und das sieht man erst im gerenderten Clip.
* **Die Längenregeln.** 15–45 Sekunden gelten für die Netto-Dauer, nicht für
  den Rohausschnitt. Wer das verwechselt, veröffentlicht 40-Sekunden-Clips
  mit 12 Sekunden Schweigen darin.
* **Die Doppelungssperre.** Sie ist der einzige Schutz davor, dieselbe Szene
  zweimal zu posten. Fällt sie aus, merkt es niemand – bis der Kanal
  auffällt.
* **Der Deckel auf der Lernkurve.** Ohne ihn frisst sich das System in die
  Kategorie, die zufällig zuerst gut lief.

Die Tests gehen nicht ins Netz und rufen kein ffmpeg auf: der Renderer wird
über den erzeugten Befehl geprüft, nicht über die erzeugte Datei.

Lauf:  python -m unittest discover -s tests
"""
from __future__ import annotations

import json
import sys
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "src"))

from clipwerk import (ausgabe, bewertung, kandidaten, kategorien,   # noqa: E402
                      lernkurve, motor, plan, quellen, render,
                      schnitt, signale, texte, transkript, untertitel,
                      verlauf, wachstum)

LEXIKON = signale.lade_lexikon(WURZEL / "content" / "clip_lexikon.json")
HASHTAGS = kategorien.lade_hashtags(WURZEL / "content" / "clip_hashtags.json")


# --------------------------------------------------------------------------- #
# Beispielstream
# --------------------------------------------------------------------------- #
def _srt(saetze: list[tuple[float, float, str]]) -> str:
    def stempel(w: float) -> str:
        ms = int(round((w - int(w)) * 1000))
        g = int(w)
        return f"{g // 3600:02d}:{(g % 3600) // 60:02d}:{g % 60:02d},{ms:03d}"
    teile = []
    for nummer, (a, b, text) in enumerate(saetze, start=1):
        teile.append(f"{nummer}\n{stempel(a)} --> {stempel(b)}\n{text}\n")
    return "\n".join(teile)


SAETZE = [
    (0.0, 3.0, "also ähm ich weiß nicht"),
    (6.0, 9.0, "ja gut das ist halt so"),
    (12.0, 15.0, "moment ich guck mal kurz"),
    (20.0, 23.5, "Leute ich erzähl euch jetzt mal was."),
    (24.0, 27.0, "Ich hab euch nie erzählt was letztens passiert ist."),
    (27.5, 31.0, "Der Typ stand da und hat mich einfach ANGESCHRIEN!"),
    (31.5, 34.5, "Ich schwöre euch sowas habe ich noch nie erlebt."),
    (35.0, 38.0, "Das ist nicht dein Ernst! Hahaha ich kann nicht mehr!"),
    (42.0, 45.0, "also ähm ja gut"),
    (50.0, 53.0, "ich mach mal weiter"),
]


def _beispielstream(mit_chat: bool = True) -> quellen.Stream:
    with TemporaryDirectory() as ordner:
        pfad = Path(ordner) / "t.srt"
        pfad.write_text(_srt(SAETZE), encoding="utf-8")
        segmente = quellen.lade_transkript(pfad)

    chat: list[quellen.ChatNachricht] = []
    if mit_chat:
        for sekunde in range(0, 60):
            chat.append(quellen.ChatNachricht(float(sekunde), "u", "hi"))
        for i in range(120):                   # Ausschlag um den Höhepunkt
            chat.append(quellen.ChatNachricht(29.0 + (i % 90) / 10.0, f"u{i}",
                                              "KEKW clip it"))
    return quellen.Stream("s-test", "2026-09-01", "K1ANUSH", "Just Chatting",
                          segmente, chat)


# --------------------------------------------------------------------------- #
class Quellen(unittest.TestCase):
    def test_zeitstempel_hin_und_zurueck(self):
        self.assertAlmostEqual(quellen.sekunden("01:02:03,500"), 3723.5)
        self.assertAlmostEqual(quellen.sekunden("02:03.5"), 123.5)
        self.assertEqual(quellen.stempel(3723), "1:02:03")
        self.assertEqual(quellen.stempel(83), "1:23")
        self.assertEqual(quellen.stempel(83, mit_stunden=True), "0:01:23")

    def test_srt_und_vtt_ergeben_dasselbe(self):
        with TemporaryDirectory() as ordner:
            o = Path(ordner)
            (o / "a.srt").write_text(_srt(SAETZE[:3]), encoding="utf-8")
            vtt = "WEBVTT\n\n" + _srt(SAETZE[:3]).replace(",", ".")
            (o / "b.vtt").write_text(vtt, encoding="utf-8")
            a = quellen.lade_transkript(o / "a.srt")
            b = quellen.lade_transkript(o / "b.vtt")
        self.assertEqual([s.text for s in a], [s.text for s in b])
        self.assertEqual(a[0].start, 0.0)

    def test_whisper_json_mit_wortzeiten(self):
        with TemporaryDirectory() as ordner:
            pfad = Path(ordner) / "w.json"
            pfad.write_text(json.dumps({"segments": [
                {"start": 1.0, "end": 3.0, "text": "hallo welt",
                 "words": [{"word": "hallo", "start": 1.0, "end": 1.8},
                           {"word": "welt", "start": 1.9, "end": 3.0}]}]}),
                encoding="utf-8")
            segmente = quellen.lade_transkript(pfad)
        self.assertEqual(len(segmente[0].woerter), 2)
        self.assertEqual(segmente[0].woerter[1].text, "welt")

    def test_geschaetzte_wortzeiten_bleiben_im_segment(self):
        segment = quellen.Segment(10.0, 14.0, "eins zwei drei vier")
        woerter = segment.wortliste()
        self.assertEqual(len(woerter), 4)
        self.assertGreaterEqual(woerter[0].start, 10.0)
        self.assertLessEqual(woerter[-1].ende, 14.01)

    def test_chat_formate(self):
        with TemporaryDirectory() as ordner:
            o = Path(ordner)
            (o / "vod.json").write_text(json.dumps({"comments": [
                {"content_offset_seconds": 12.5,
                 "commenter": {"display_name": "anna"},
                 "message": {"body": "KEKW"}}]}), encoding="utf-8")
            (o / "irc.log").write_text("[00:00:20] bert: was war das\n",
                                       encoding="utf-8")
            (o / "zeilen.jsonl").write_text(
                json.dumps({"zeit": 5, "nutzer": "cem", "text": "hi"}) + "\n",
                encoding="utf-8")
            vod = quellen.lade_chat(o / "vod.json")
            irc = quellen.lade_chat(o / "irc.log")
            jsonl = quellen.lade_chat(o / "zeilen.jsonl")
        self.assertEqual((vod[0].sekunde, vod[0].nutzer), (12.5, "anna"))
        self.assertEqual((irc[0].sekunde, irc[0].text), (20.0, "was war das"))
        self.assertEqual(jsonl[0].nutzer, "cem")

    def test_leeres_transkript_bricht_ab(self):
        with TemporaryDirectory() as ordner:
            pfad = Path(ordner) / "leer.srt"
            pfad.write_text("   ", encoding="utf-8")
            with self.assertRaises(quellen.QuellenFehler):
                quellen.lade_transkript(pfad)


class Signale(unittest.TestCase):
    def test_wortgrenzen(self):
        """'was' darf nicht in 'etwas' oder 'waschen' treffen."""
        muster = signale._muster(["was", "lul"])
        self.assertTrue(muster.search("was war das"))
        self.assertFalse(muster.search("etwas anderes"))
        self.assertFalse(muster.search("lullen"))

    def test_kurve_findet_den_ausschlag(self):
        stream = _beispielstream()
        kurve = signale.kurve(stream, LEXIKON)
        spitzen = signale.spitzen(kurve, schwelle=1.0)
        self.assertTrue(spitzen, "kein Ausschlag gefunden")
        beste = max(spitzen, key=lambda s: s.staerke)
        self.assertTrue(25 <= beste.sekunde <= 45,
                        f"Höhepunkt bei {beste.sekunde} statt im Ereignisfenster")

    def test_mindestabstand_wird_eingehalten(self):
        stream = _beispielstream()
        kurve = signale.kurve(stream, LEXIKON)
        spitzen = signale.spitzen(kurve, schwelle=0.2, mindestabstand=25.0)
        zeiten = sorted(s.sekunde for s in spitzen)
        for links, rechts in zip(zeiten, zeiten[1:]):
            self.assertGreaterEqual(rechts - links, 25.0)


class Kandidaten(unittest.TestCase):
    def _kandidat(self) -> kandidaten.Kandidat:
        stream = _beispielstream()
        kurve = signale.kurve(stream, LEXIKON)
        spitze = max(signale.spitzen(kurve, schwelle=0.5),
                     key=lambda s: s.staerke)
        kandidat = kandidaten.baue(stream, kurve, spitze, "",
                                   set(LEXIKON["fuellwoerter"]))
        self.assertIsNotNone(kandidat)
        return kandidat

    def test_laenge_bleibt_in_der_zielspanne(self):
        kandidat = self._kandidat()
        self.assertGreaterEqual(kandidat.dauer, kandidaten.MIN_KURZ)
        self.assertLessEqual(kandidat.dauer, kandidaten.HART_MAX)

    def test_fuellsaetze_am_rand_fallen_weg(self):
        kandidat = self._kandidat()
        self.assertNotIn("ich mach mal weiter", kandidat.text)
        self.assertNotIn("also ähm ja gut", kandidat.text)

    def test_clipzeit_rechnet_auslassungen_heraus(self):
        kandidat = kandidaten.Kandidat(
            start=10.0, ende=40.0, hoehepunkt=30.0, staerke=1.0, anteile={},
            auslassungen=[(15.0, 20.0), (25.0, 27.0)])
        self.assertEqual(kandidat.clipzeit(10.0), 0.0)
        self.assertEqual(kandidat.clipzeit(14.0), 4.0)
        self.assertEqual(kandidat.clipzeit(21.0), 6.0)     # 5 s weg
        self.assertEqual(kandidat.clipzeit(30.0), 13.0)    # 7 s weg
        self.assertEqual(kandidat.dauer, 23.0)
        # Ein Punkt innerhalb einer Auslassung fällt auf deren Anfang.
        self.assertEqual(kandidat.clipzeit(17.0), 5.0)

    def test_stille_wird_zur_auslassung(self):
        kandidat = self._kandidat()
        for von, bis in kandidat.auslassungen:
            self.assertGreater(bis - von, 0.0)
            self.assertGreaterEqual(von, kandidat.start)
            self.assertLessEqual(bis, kandidat.ende + 0.01)

    def test_entdoppeln_wirft_die_schwaechere_ueberlappung_weg(self):
        a = kandidaten.Kandidat(0.0, 30.0, 15.0, 5.0, {})
        b = kandidaten.Kandidat(10.0, 40.0, 25.0, 2.0, {})   # überlappt stark
        c = kandidaten.Kandidat(100.0, 130.0, 115.0, 3.0, {})
        behalten = kandidaten.entdoppeln([a, b, c])
        self.assertEqual([k.start for k in behalten], [0.0, 100.0])


class Bewertung(unittest.TestCase):
    def _note(self, faktoren=None) -> tuple:
        stream = _beispielstream()
        kurve = signale.kurve(stream, LEXIKON)
        spitze = max(signale.spitzen(kurve, schwelle=0.5),
                     key=lambda s: s.staerke)
        kandidat = kandidaten.baue(stream, kurve, spitze, "",
                                   set(LEXIKON["fuellwoerter"]))
        return bewertung.bewerte(kandidat, kurve, faktoren), kandidat

    def test_punkte_bleiben_im_rahmen(self):
        note, _ = self._note()
        self.assertLessEqual(note.punkte, 100)
        self.assertGreaterEqual(note.punkte, 0)
        for name, hoechstwert in bewertung.HOECHSTPUNKTE.items():
            self.assertLessEqual(getattr(note, name), hoechstwert + 0.01,
                                 f"{name} über der Höchstpunktzahl")

    def test_schwellen_stimmen_mit_der_anweisung_ueberein(self):
        self.assertEqual(bewertung.SCHWELLE_VERWERFEN, 65)
        self.assertEqual(bewertung.SCHWELLE_PRIORITAET, 80)

    def test_lernfaktor_kann_nicht_ueber_die_hoechstpunktzahl_heben(self):
        note, _ = self._note({"FUNNY": {"gesamt": 5.0}, "STORY": {"gesamt": 5.0},
                              "UNEXPECTED": {"gesamt": 5.0},
                              "CHAT MOMENT": {"gesamt": 5.0}})
        self.assertLessEqual(note.punkte, 100)
        self.assertLessEqual(note.hook, bewertung.HOECHSTPUNKTE["hook"] + 0.01)

    def test_begruendung_nennt_einen_zeitpunkt(self):
        note, _ = self._note()
        self.assertIn(":", note.begruendung)
        self.assertTrue(note.begruendung[0].isupper())


class Untertitel(unittest.TestCase):
    def _zeilen(self):
        stream = _beispielstream()
        kurve = signale.kurve(stream, LEXIKON)
        spitze = max(signale.spitzen(kurve, schwelle=0.5),
                     key=lambda s: s.staerke)
        kandidat = kandidaten.baue(stream, kurve, spitze, "",
                                   set(LEXIKON["fuellwoerter"]))
        return kandidat, untertitel.zeilen(kandidat, LEXIKON)

    def test_hoechstens_sieben_woerter(self):
        _, zeilen = self._zeilen()
        self.assertTrue(zeilen)
        for zeile in zeilen:
            self.assertLessEqual(len(zeile.woerter), untertitel.MAX_WOERTER,
                                 f"zu viele Wörter: {zeile.text}")

    def test_zeiten_laufen_vorwaerts_und_im_clip(self):
        kandidat, zeilen = self._zeilen()
        self.assertGreaterEqual(zeilen[0].start, 0.0)
        for links, rechts in zip(zeilen, zeilen[1:]):
            self.assertLessEqual(links.start, rechts.start)
        self.assertLessEqual(zeilen[-1].ende, kandidat.dauer + 1.0)

    def test_text_stammt_aus_dem_transkript(self):
        kandidat, zeilen = self._zeilen()
        gesprochen = kandidat.text.lower()
        for wort in untertitel.als_text(zeilen).lower().split():
            self.assertIn(wort, gesprochen)

    def test_ass_und_srt_sind_wohlgeformt(self):
        _, zeilen = self._zeilen()
        ass = untertitel.als_ass(zeilen)
        self.assertIn("[Events]", ass)
        self.assertEqual(ass.count("Dialogue:"), len(zeilen))
        srt = untertitel.als_srt(zeilen)
        self.assertIn(" --> ", srt)
        self.assertTrue(srt.startswith("1\n"))


class Kategorien(unittest.TestCase):
    def test_zwoelf_kategorien_wie_in_abschnitt_9(self):
        self.assertEqual(len(kategorien.KATEGORIEN), 12)
        self.assertIn("CLIP / MEME", kategorien.KATEGORIEN)

    def test_hashtags_fuenf_bis_acht_und_ohne_doppelte(self):
        for kategorie in kategorien.KATEGORIEN:
            tags = kategorien.hashtags(kategorie, "K1ANUSH", "Counter-Strike 2",
                                       HASHTAGS)
            self.assertGreaterEqual(len(tags), 5, kategorie)
            self.assertLessEqual(len(tags), 8, kategorie)
            self.assertEqual(len(tags), len(set(tags)), kategorie)
            self.assertTrue(all(t.startswith("#") for t in tags))
            self.assertIn("#k1anush", tags)

    def test_umlaute_werden_zum_tag(self):
        self.assertEqual(kategorien._tag("Grüße & Späße"), "#gruessespaesse")

    def test_chatmenge_entscheidet_die_kategorie_nicht(self):
        """Der Chat wird bei jedem starken Moment schneller – wäre chat_menge
        ein Kategoriesignal, wäre alles ein CHAT MOMENT."""
        name, _ = kategorien.bestimme({"chat_menge": 9.0, "sprache_wut": 1.0})
        self.assertEqual(name, "RAGE")

    def test_serienformat_setzt_den_namen_ein(self):
        self.assertEqual(kategorien.serienformat("STORY", "K1ANUSH"),
                         "K1ANUSH Storytime")


class Texte(unittest.TestCase):
    def _texte(self):
        stream = _beispielstream()
        kurve = signale.kurve(stream, LEXIKON)
        spitze = max(signale.spitzen(kurve, schwelle=0.5),
                     key=lambda s: s.staerke)
        kandidat = kandidaten.baue(stream, kurve, spitze, "",
                                   set(LEXIKON["fuellwoerter"]))
        note = bewertung.bewerte(kandidat, kurve)
        return kandidat, texte.baue(kandidat, note, "K1ANUSH", "Just Chatting",
                                    HASHTAGS)

    def test_titellaengen(self):
        _, t = self._texte()
        self.assertLessEqual(len(t.tiktok_titel), texte.TIKTOK_TITEL_MAX)
        self.assertLessEqual(len(t.youtube_titel), texte.YOUTUBE_TITEL_MAX)
        self.assertTrue(t.tiktok_caption)
        self.assertLessEqual(len(t.tiktok_caption), texte.CAPTION_MAX)

    def test_kernzitat_ist_kein_fuellsatz(self):
        kandidat = kandidaten.Kandidat(
            0.0, 20.0, 10.0, 1.0, {},
            segmente=[quellen.Segment(9.0, 11.0, "also ähm ich weiß nicht"),
                      quellen.Segment(12.0, 15.0,
                                      "Der Typ hat mich einfach angeschrien.")])
        self.assertEqual(texte.kernzitat(kandidat),
                         "Der Typ hat mich einfach angeschrien")

    def test_hook_ohne_signal_zitiert_statt_zu_behaupten(self):
        kandidat = kandidaten.Kandidat(
            0.0, 20.0, 10.0, 1.0, {},          # keine Anteile: kein Signal
            segmente=[quellen.Segment(9.0, 12.0,
                                      "Der Typ hat mich einfach angeschrien.")])
        note = bewertung.Bewertung(10, 10, 10, 5, 5, 5, "STORY", 0.5)
        satz = texte.hook(kandidat, note)
        self.assertTrue(satz.startswith("„"),
                        f"unbelegte Behauptung als Hook: {satz}")

    def test_crossposting_variiert_den_hook(self):
        t = texte.Texte("Chat ist eskaliert 💀", "a", "b", "c", "d")
        self.assertNotEqual(texte.variante(t, "tiktok"),
                            texte.variante(t, "instagram"))
        self.assertNotIn("💀", texte.variante(t, "youtube"))


class Schnitt(unittest.TestCase):
    def test_layout_faellt_ohne_facecam_auf_vollbild(self):
        self.assertEqual(schnitt.waehle_layout("GAMING", hat_facecam=False),
                         "vollbild")
        self.assertEqual(schnitt.waehle_layout("GAMING", hat_facecam=True),
                         "geteilt")

    def test_unbekanntes_layout_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            schnitt.waehle_layout("GAMING", True, "quadratisch")

    def test_plan_bleibt_in_der_cliplaenge(self):
        stream = _beispielstream()
        kurve = signale.kurve(stream, LEXIKON)
        spitze = max(signale.spitzen(kurve, schwelle=0.5),
                     key=lambda s: s.staerke)
        kandidat = kandidaten.baue(stream, kurve, spitze, "",
                                   set(LEXIKON["fuellwoerter"]))
        note = bewertung.bewerte(kandidat, kurve)
        plan_ = schnitt.plane(kandidat, note, kurve, stream)
        self.assertTrue(plan_.anweisungen)
        for anweisung in plan_.anweisungen:
            self.assertGreaterEqual(anweisung.von, 0.0)
            self.assertLessEqual(anweisung.bis, kandidat.dauer + 0.01)
        self.assertIn("Punch-In", plan_.als_text())


class Verlauf(unittest.TestCase):
    def _eintrag(self, kennung="s1-000010", start=10.0, ende=40.0,
                 stream_id="s1", thema="ein ganz eigenes thema ueber katzen"):
        return {"clip_id": kennung, "stream_id": stream_id, "start": start,
                "ende": ende, "dauer": ende - start, "thema": thema,
                "kategorie": "FUNNY", "caption": "x", "score": 80}

    def test_ueberlappung_gilt_als_doppelt(self):
        bestand = [self._eintrag()]
        neu = self._eintrag("s1-000020", 20.0, 50.0,
                            thema="voellig andere woerter hier drin")
        self.assertIsNotNone(verlauf.doppelt_zu(neu, bestand))

    def test_getrennte_szenen_sind_nicht_doppelt(self):
        bestand = [self._eintrag()]
        neu = self._eintrag("s1-000200", 200.0, 230.0,
                            thema="voellig andere woerter hier drin")
        self.assertIsNone(verlauf.doppelt_zu(neu, bestand))

    def test_gleiches_thema_aus_anderem_lauf(self):
        bestand = [self._eintrag()]
        neu = self._eintrag("s2-000900", 900.0, 930.0, stream_id="s2")
        self.assertIsNotNone(verlauf.doppelt_zu(neu, bestand))

    def test_aufnehmen_und_zweiter_lauf(self):
        with TemporaryDirectory() as ordner:
            pfad = Path(ordner) / "db.json"
            erst = verlauf.aufnehmen([self._eintrag()], pfad)
            self.assertEqual(erst["aufgenommen"], ["s1-000010"])
            zweit = verlauf.aufnehmen([self._eintrag()], pfad)
            self.assertEqual(zweit["aufgenommen"], [])
            self.assertEqual(len(zweit["abgewiesen"]), 1)
            self.assertEqual(verlauf.lade(pfad)["clips"].__len__(), 1)

    def test_derselbe_clip_laeuft_je_plattform_nur_einmal(self):
        with TemporaryDirectory() as ordner:
            pfad = Path(ordner) / "db.json"
            verlauf.aufnehmen([self._eintrag()], pfad)
            self.assertTrue(verlauf.veroeffentlicht(pfad, "s1-000010", "tiktok"))
            self.assertFalse(verlauf.veroeffentlicht(pfad, "s1-000010", "tiktok"))
            self.assertTrue(verlauf.veroeffentlicht(pfad, "s1-000010", "instagram"))

    def test_kennzahlen_haengen_an_der_veroeffentlichung(self):
        with TemporaryDirectory() as ordner:
            pfad = Path(ordner) / "db.json"
            verlauf.aufnehmen([self._eintrag()], pfad)
            verlauf.veroeffentlicht(pfad, "s1-000010", "tiktok")
            self.assertTrue(verlauf.performance(pfad, "s1-000010", "tiktok",
                                                {"views": 1000}))
            eintrag = verlauf.finde(pfad, "s1-000010")
            leistung = eintrag["veroeffentlichungen"][0]["performance"]
            self.assertEqual(leistung["views"], 1000)
            self.assertIn("erfasst_am", leistung)

    def test_beschaedigte_datei_wirft_nicht(self):
        with TemporaryDirectory() as ordner:
            pfad = Path(ordner) / "db.json"
            pfad.write_text("{kaputt", encoding="utf-8")
            self.assertEqual(verlauf.lade(pfad), {"clips": []})


class Lernkurve(unittest.TestCase):
    def _datenbank(self, ordner: Path) -> Path:
        pfad = ordner / "db.json"
        muster = {"RAGE": (0.75, 0.012, 0.006, 0.004),
                  "GAMING": (0.40, 0.002, 0.001, 0.0006)}
        clips = []
        for kategorie, (comp, sh, ko, fo) in muster.items():
            for i in range(4):
                views = 40000
                clips.append({
                    "clip_id": f"{kategorie}-{i}", "stream_id": "s1",
                    "datum": "2026-08-01", "start": i * 100, "ende": i * 100 + 25,
                    "dauer": 25, "kategorie": kategorie,
                    "thema": f"{kategorie} eigenes thema nummer {i}",
                    "caption": "x", "score": 75,
                    "veroeffentlichungen": [{
                        "plattform": "tiktok", "datum": "2026-08-02",
                        "performance": {"views": views, "completion": comp,
                                        "shares": int(views * sh),
                                        "kommentare": int(views * ko),
                                        "follower": int(views * fo),
                                        "erfasst_am": "2026-08-05"}}]})
        verlauf.schreib(pfad, {"clips": clips})
        return pfad

    def test_bessere_kategorie_bekommt_den_hoeheren_faktor(self):
        with TemporaryDirectory() as ordner:
            pfad = self._datenbank(Path(ordner))
            faktoren = lernkurve.faktoren(pfad)
        self.assertGreater(faktoren["RAGE"]["gesamt"],
                           faktoren["GAMING"]["gesamt"])

    def test_faktoren_bleiben_gedeckelt(self):
        with TemporaryDirectory() as ordner:
            pfad = self._datenbank(Path(ordner))
            faktoren = lernkurve.faktoren(pfad)
        for werte in faktoren.values():
            for faktor in werte.values():
                self.assertGreaterEqual(faktor, lernkurve.DECKEL_UNTEN)
                self.assertLessEqual(faktor, lernkurve.DECKEL_OBEN)

    def test_ohne_zahlen_wird_nichts_gelernt(self):
        with TemporaryDirectory() as ordner:
            pfad = Path(ordner) / "leer.json"
            self.assertEqual(lernkurve.faktoren(pfad), {})
            self.assertIn("Noch keine", lernkurve.bericht(pfad))


class Plan(unittest.TestCase):
    def _clips(self, anzahl: int = 6) -> list[dict]:
        return [{"clip_id": f"c{i}", "score": 90 - i * 5, "kategorie": "FUNNY",
                 "texte": {"hook": f"hook {i}", "tiktok_titel": "t",
                           "tiktok_caption": "c", "instagram_caption": "ic",
                           "youtube_titel": "yt", "hashtags": ["#a"]},
                 "hook_varianten": {"tiktok": f"hook {i}",
                                    "instagram": f"hook {i} ig",
                                    "youtube": f"hook {i} yt"}}
                for i in range(anzahl)]

    def test_hoechster_score_zuerst(self):
        zeitplan = plan.baue(self._clips(), ab=date(2026, 9, 1))
        erster = [e for e in zeitplan if e.plattform == "tiktok"][0]
        self.assertEqual(erster.clip_id, "c0")
        self.assertEqual(erster.score, 90)

    def test_tageshoechstzahl_wird_eingehalten(self):
        zeitplan = plan.baue(self._clips(10), ab=date(2026, 9, 1))
        je_tag: dict = {}
        for eintrag in zeitplan:
            schluessel = (eintrag.plattform, eintrag.datum)
            je_tag[schluessel] = je_tag.get(schluessel, 0) + 1
        for (plattform, _), anzahl in je_tag.items():
            self.assertLessEqual(anzahl, plan.SCHIENEN[plattform][1])

    def test_crossposting_liegt_spaeter_und_klingt_anders(self):
        zeitplan = plan.baue(self._clips(1), ab=date(2026, 9, 1))
        je_plattform = {e.plattform: e for e in zeitplan}
        self.assertLess(je_plattform["tiktok"].datum,
                        je_plattform["instagram"].datum)
        self.assertLess(je_plattform["instagram"].datum,
                        je_plattform["youtube"].datum)
        self.assertNotEqual(je_plattform["tiktok"].hook,
                            je_plattform["instagram"].hook)

    def test_nur_gewuenschte_plattformen(self):
        zeitplan = plan.baue(self._clips(2), ab=date(2026, 9, 1),
                             plattformen=("tiktok",))
        self.assertEqual({e.plattform for e in zeitplan}, {"tiktok"})


class Render(unittest.TestCase):
    def _kandidat(self):
        return kandidaten.Kandidat(
            start=10.0, ende=40.0, hoehepunkt=25.0, staerke=1.0, anteile={},
            auslassungen=[(15.0, 18.0)])

    def test_behaltene_bereiche_lassen_die_stille_aus(self):
        bereiche = render._behaltene_bereiche(self._kandidat())
        self.assertEqual(bereiche, [(0.0, 5.0), (8.0, 30.0)])

    def test_befehl_schneidet_und_setzt_das_format(self):
        befehl = render.ffmpeg_befehl(
            Path("/tmp/quelle.mp4"), self._kandidat(), "vollbild",
            Path("/tmp/ziel.mp4"), punch_fenster=[(1.0, 3.0)])
        text = " ".join(befehl)
        self.assertIn("-ss 10.00", text)
        self.assertIn("-to 40.00", text)
        self.assertIn(f"{render.BREITE}x{render.HOEHE}", text)
        self.assertIn("select=", text)
        self.assertIn("aselect=", text)
        self.assertIn("zoompan", text)
        self.assertIn("libx264", text)

    def test_ohne_facecam_kein_geteiltes_layout(self):
        befehl = render.ffmpeg_befehl(
            Path("/tmp/q.mp4"), self._kandidat(), "geteilt", Path("/tmp/z.mp4"))
        self.assertNotIn("vstack", " ".join(befehl))

    def test_facecam_aus_text(self):
        cam = render.Facecam.aus_text("1450:60:440:300")
        self.assertEqual((cam.x, cam.breite), (1450, 440))
        with self.assertRaises(ValueError):
            render.Facecam.aus_text("1450:60")

    def test_skript_ist_ausfuehrbar(self):
        with TemporaryDirectory() as ordner:
            pfad = render.schreibe_skript([["ffmpeg", "-i", "a b.mp4"]],
                                          Path(ordner) / "r.sh")
            inhalt = pfad.read_text(encoding="utf-8")
        self.assertTrue(inhalt.startswith("#!/bin/sh"))
        self.assertIn("'a b.mp4'", inhalt)


class Wachstum(unittest.TestCase):
    def test_serienformat_erst_ab_zwei_clips(self):
        clips = [{"kategorie": "RAGE", "score": 80, "teilnoten": {"kommentar": 0.8},
                  "thema": "a", "texte": {}},
                 {"kategorie": "RAGE", "score": 78, "teilnoten": {"kommentar": 0.8},
                  "thema": "b", "texte": {}},
                 {"kategorie": "WIN", "score": 90, "teilnoten": {"kommentar": 0.3},
                  "thema": "c", "texte": {}}]
        auswertung = wachstum.auswerten(clips, "K1ANUSH")
        self.assertIn("Chat bringt K1ANUSH zum Ausrasten", auswertung.serien)
        self.assertTrue(all("liefert ab" not in s for s in auswertung.serien))

    def test_ohne_clips_kein_erfundenes_ergebnis(self):
        auswertung = wachstum.auswerten([], "K1ANUSH")
        self.assertEqual(auswertung.stark, [])
        self.assertIn("nichts abzuleiten", auswertung.hinweis)


class NurChat(unittest.TestCase):
    """Der Chat-Modus: kein Transkript, trotzdem brauchbare Momente.

    Er ist der Weg, der in Minuten statt in Stunden ein Ergebnis liefert -
    Whisper über ein Sechs-Stunden-VOD läuft auf einem normalen Rechner
    halbe Nächte. Wichtig ist, dass die Einbußen *ehrlich* sind: gröberer
    Zuschnitt und keine Untertitel, aber keine erfundenen Inhalte.
    """
    def _stream(self) -> quellen.Stream:
        voll = _beispielstream()
        return quellen.Stream("s-chat", "2026-09-01", "K1ANUSH",
                              "Just Chatting", [], voll.chat)

    def test_ohne_beide_quellen_bricht_es_ab(self):
        with self.assertRaises(quellen.QuellenFehler):
            quellen.lade_stream("s", "2026-09-01", "K", None, None)

    def test_nur_chat_wird_erkannt(self):
        self.assertTrue(self._stream().nur_chat)
        self.assertFalse(_beispielstream().nur_chat)

    def test_findet_momente_ohne_transkript(self):
        ergebnis = motor.analysiere(self._stream(), schwelle=0)
        self.assertTrue(ergebnis.clips, "im Chat-Modus kein Moment gefunden")

    def test_erfindet_keine_untertitel_und_keine_zitate(self):
        ergebnis = motor.analysiere(self._stream(), schwelle=0)
        for clip in ergebnis.clips:
            self.assertEqual(clip.zeilen, [])
            self.assertEqual(clip.texte.kernzitat, "")
            # Ein Hook in Anführungszeichen wäre ein Zitat - ohne Transkript
            # gibt es aber nichts zu zitieren.
            self.assertFalse(clip.texte.hook.startswith("„"),
                             f"Zitat-Hook ohne Transkript: {clip.texte.hook}")

    def test_pointe_liegt_vor_dem_chat_ausschlag(self):
        """Der Chat antwortet, er handelt nicht - der Moment liegt davor."""
        stream = self._stream()
        kurve = signale.kurve(stream, LEXIKON)
        spitze = max(signale.spitzen(kurve, schwelle=0.5),
                     key=lambda s: s.staerke)
        kandidat = kandidaten.baue(stream, kurve, spitze)
        self.assertIsNotNone(kandidat)
        self.assertLess(kandidat.hoehepunkt, spitze.sekunde)
        self.assertGreaterEqual(kandidat.hoehepunkt, kandidat.start)

    def test_keine_auslassungen_ohne_sprache(self):
        """Stille lässt sich ohne Transkript nicht erkennen – also wird auch
        keine behauptet."""
        ergebnis = motor.analysiere(self._stream(), schwelle=0)
        for clip in ergebnis.clips:
            self.assertEqual(clip.kandidat.auslassungen, [])
            self.assertEqual(clip.kandidat.dauer, clip.kandidat.roh_dauer)

    def test_laengenregeln_gelten_weiter(self):
        ergebnis = motor.analysiere(self._stream(), schwelle=0)
        for clip in ergebnis.clips:
            self.assertGreaterEqual(clip.kandidat.dauer, kandidaten.MIN_KURZ)
            self.assertLessEqual(clip.kandidat.dauer, kandidaten.HART_MAX)

    def test_bericht_nennt_die_einschraenkung(self):
        stream = self._stream()
        ergebnis = motor.analysiere(stream, schwelle=0)
        text = ausgabe.bericht(ergebnis, stream)
        self.assertIn("Ohne Transkript", text)
        self.assertIn("kein Transkript", text)

    def test_keine_leeren_untertiteldateien(self):
        """Eine ASS-Datei mit Kopfzeile und nichts dahinter sieht nach einem
        Ergebnis aus, das es nicht gibt."""
        stream = self._stream()
        ergebnis = motor.analysiere(stream, schwelle=0)
        with TemporaryDirectory() as ordner:
            ausgabe.schreibe_paket(ergebnis, stream, Path(ordner))
            self.assertFalse((Path(ordner) / "untertitel").exists())

    def test_schwelle_haengt_an_der_betriebsart(self):
        """Jede Betriebsart hat ihre eigene Schwelle, und sie wird an der
        vorhandenen Quelle festgemacht - nicht am Inhalt."""
        voll = _beispielstream()
        self.assertEqual(bewertung.schwelle_fuer(voll),
                         bewertung.SCHWELLE_VERWERFEN)

        ohne_chat = replace(voll, chat=[])
        self.assertEqual(bewertung.schwelle_fuer(ohne_chat),
                         bewertung.SCHWELLE_NUR_TRANSKRIPT)

        ohne_text = replace(voll, segmente=[])
        self.assertEqual(bewertung.schwelle_fuer(ohne_text),
                         bewertung.SCHWELLE_NUR_CHAT)

        # Ohne Transkript fallen Einstieg und Wortdichte aus der Rechnung
        # heraus, statt als Null zu zählen. Was bleibt, trägt volles
        # Gewicht - und das sind die großzügigen Teile. Deshalb liegt die
        # Schwelle dort *höher*, nicht tiefer.
        self.assertGreater(bewertung.SCHWELLE_NUR_CHAT,
                           bewertung.SCHWELLE_VERWERFEN)
        self.assertLess(bewertung.SCHWELLE_NUR_TRANSKRIPT,
                        bewertung.SCHWELLE_VERWERFEN)


class Betriebsarten(unittest.TestCase):
    """Was passiert, wenn eine der beiden Quellen fehlt.

    Am 02.09.2026 lieferte ein Lauf über einen echten Stream mit 1549
    erkannten Sprachsegmenten **null** Clips, und der Bericht sagte dazu
    nur „kein Moment hat die Schwelle erreicht". Das war nicht der Stream,
    das waren drei Fehler, die alle in dieselbe Richtung zeigten:

    1. `_normiere` löschte jede Signalreihe, in der jeder Treffer einzeln
       auftrat - und das sind ohne Chat fast alle.
    2. Sprachsignale saßen nur auf der Anfangssekunde ihres Segments; die
       Glättung zog sie danach auf ein Fünftel herunter.
    3. Die Spitzenschwelle war eine feste Zahl, gemessen an einer Kurve mit
       vollem Sensorsatz. Ohne Chat liegt dieselbe Kurve halb so hoch.

    Jeder einzelne davon hätte gereicht. Deshalb wird hier jeder einzeln
    geprüft, nicht nur das Gesamtergebnis.
    """

    def test_seltene_reihe_wird_nicht_ausgeloescht(self):
        """Eine Reihe, in der jeder Treffer einzeln auftritt, trägt Signal.

        Der Median der belegten Sekunden ist dort 1, die mittlere
        Abweichung 0 - und damit war vorher die ganze Reihe null.
        """
        reihe = [0.0] * 200
        for i in (17, 61, 92, 140, 171):
            reihe[i] = 1.0
        reihe[92] = 3.0
        norm = signale._normiere(reihe)
        self.assertGreater(max(norm), 0.0)
        self.assertGreater(norm[92], norm[17])
        self.assertEqual(norm[0], 0.0)

    def test_sprachsignal_gilt_fuer_das_ganze_segment(self):
        """Ein Satz ist eine Strecke, kein Punkt."""
        stream = _beispielstream(mit_chat=False)
        kurve = signale.kurve(stream, LEXIKON)
        lachen = kurve.reihen["sprache_lachen"]
        # Der Lacher steht in dem Segment von 35 bis 38 Sekunden.
        self.assertGreater(sum(lachen[35:39]), 0.0)
        self.assertGreater(len([w for w in lachen[35:39] if w > 0]), 1)

    def test_bezug_haengt_an_der_quelle_nicht_am_inhalt(self):
        voll = signale.kurve(_beispielstream(), LEXIKON)
        ohne_chat = signale.kurve(_beispielstream(mit_chat=False), LEXIKON)
        self.assertEqual(voll.bezug, 1.0)
        self.assertLess(ohne_chat.bezug, 1.0)
        self.assertGreater(ohne_chat.bezug, 0.4)
        # Die Spitzenschwelle wandert mit, sonst findet die Kurve ohne Chat
        # nie eine Spitze.
        self.assertTrue(signale.spitzen(ohne_chat))

    def test_ohne_chat_entstehen_trotzdem_momente(self):
        """Der Regressionstest zum Lauf über Stream 2862735566."""
        stream = _beispielstream(mit_chat=False)
        ergebnis = motor.analysiere(stream, schwelle=0)
        self.assertGreater(ergebnis.geprueft, 0)
        self.assertTrue(ergebnis.clips)

    def test_nicht_messbares_zaehlt_nicht_als_null(self):
        """Ein fehlender Sensor senkt die Note nicht, er fällt heraus."""
        # Zwei gleich gute Bestandteile, einer davon nicht messbar:
        # das Ergebnis ist der messbare, nicht sein halber Wert.
        self.assertAlmostEqual(
            bewertung._mittel([(0.8, 0.5, True), (0.0, 0.5, False)]), 0.8)
        self.assertAlmostEqual(
            bewertung._mittel([(0.8, 0.5, True), (0.0, 0.5, True)]), 0.4)
        self.assertEqual(bewertung._mittel([(0.8, 0.5, False)]), 0.0)


class Transkript(unittest.TestCase):
    """Die Umwandlung von faster-whisper in unser Format.

    Das Modell selbst wird hier nicht geladen - das dauert Minuten und
    braucht Netz. Geprüft wird die Naht: was faster-whisper liefert, muss
    `quellen.lade_transkript` unverändert wieder einlesen können. Genau an
    dieser Naht wären Wortzeiten still verlorengegangen, und ohne sie sitzen
    die Untertitel auf dem Satz statt auf dem Wort.
    """
    def _roh(self, start, ende, text, woerter=None):
        return SimpleNamespace(
            start=start, ende=ende, end=ende, text=text,
            words=[SimpleNamespace(word=w, start=a, end=b)
                   for w, a, b in (woerter or [])] or None)

    def test_text_wird_entrandet(self):
        s = transkript._segment(
            self._roh(1.0, 2.0, "   Das ist es!   "), True)
        self.assertEqual(s["text"], "Das ist es!")

    def test_wortzeiten_kommen_durch(self):
        s = transkript._segment(self._roh(
            12.0, 15.5, "Das ist nicht dein Ernst!",
            [(" Das", 12.0, 12.3), (" ist", 12.3, 12.6),
             ("  ", 12.6, 12.7), (" nicht", 12.7, 13.0)]), True)
        # Das leere Wort faellt weg, die uebrigen behalten ihre Zeiten.
        self.assertEqual([w["word"] for w in s["words"]],
                         ["Das", "ist", "nicht"])
        self.assertEqual(s["words"][0]["start"], 12.0)

    def test_ohne_wortzeiten_kein_leeres_feld(self):
        s = transkript._segment(self._roh(1.0, 2.0, "hm"), True)
        self.assertNotIn("words", s)

    def test_ergebnis_ist_wieder_einlesbar(self):
        s = transkript._segment(self._roh(
            12.0, 15.5, "Das ist nicht dein Ernst!",
            [("Das", 12.0, 12.3), ("ist", 12.3, 12.6)]), True)
        ohne = transkript._segment(self._roh(1.0, 2.0, "hm"), True)
        with TemporaryDirectory() as ordner:
            ziel = Path(ordner) / "t.json"
            transkript.schreibe([s, ohne], ziel)
            segmente = quellen.lade_transkript(ziel)

        # lade_transkript sortiert nach Startzeit.
        frueh, spaet = segmente
        self.assertEqual(spaet.text, "Das ist nicht dein Ernst!")
        self.assertEqual(spaet.woerter[0].text, "Das")
        # Ohne echte Wortzeiten muessen sie geschaetzt werden, sonst haetten
        # die Untertitel dort keinen Takt.
        self.assertFalse(frueh.woerter)
        self.assertTrue(frueh.wortliste())

    def test_unbekanntes_modell_wird_abgelehnt(self):
        with TemporaryDirectory() as ordner:
            ton = Path(ordner) / "ton.m4a"
            ton.write_bytes(b"x")
            with self.assertRaises(transkript.TranskriptFehler):
                transkript.erkenne(ton, Path(ordner) / "t.json",
                                   modell="gibtsnicht")

    def test_fehlende_tondatei_wird_gemeldet(self):
        with TemporaryDirectory() as ordner:
            with self.assertRaises(transkript.TranskriptFehler):
                transkript.erkenne(Path(ordner) / "weg.m4a",
                                   Path(ordner) / "t.json")


class Gesamtlauf(unittest.TestCase):
    def test_analyse_bis_paket(self):
        stream = _beispielstream()
        ergebnis = motor.analysiere(stream, schwelle=0,
                                    lexikon_datei=WURZEL / "content" / "clip_lexikon.json",
                                    hashtag_datei=WURZEL / "content" / "clip_hashtags.json")
        self.assertTrue(ergebnis.clips)
        with TemporaryDirectory() as ordner:
            paket = ausgabe.schreibe_paket(ergebnis, stream, Path(ordner))
            bericht = paket["bericht"].read_text(encoding="utf-8")
            daten = json.loads(paket["json"].read_text(encoding="utf-8"))
            untertiteldatei = Path(ordner) / "untertitel" / "clip-01.ass"
            self.assertTrue(untertiteldatei.exists())

        # Die Feldnamen aus Abschnitt 10 müssen wörtlich im Bericht stehen -
        # daran orientiert sich der Mensch, der schneidet.
        for feld in ("CLIP NUMMER:", "Timestamp Start:", "Timestamp Ende:",
                     "Dauer:", "Kategorie:", "Virality Score /100:",
                     "Warum dieser Clip:", "HOOK IM VIDEO:", "SCHNITT:",
                     "UNTERTITEL:", "TIKTOK TITEL:", "TIKTOK CAPTION:",
                     "HASHTAGS:", "INSTAGRAM REELS CAPTION:",
                     "YOUTUBE SHORTS TITEL:"):
            self.assertIn(feld, bericht, f"{feld} fehlt im Bericht")

        clip = daten["clips"][0]
        self.assertEqual(clip["stream_id"], "s-test")
        self.assertGreaterEqual(clip["score"], 0)
        self.assertIn(clip["kategorie"], kategorien.KATEGORIEN)
        self.assertTrue(5 <= len(clip["texte"]["hashtags"]) <= 8)

    def test_ohne_chat_laeuft_es_weiter(self):
        stream = _beispielstream(mit_chat=False)
        ergebnis = motor.analysiere(stream, schwelle=0)
        with TemporaryDirectory() as ordner:
            paket = ausgabe.schreibe_paket(ergebnis, stream, Path(ordner))
            bericht = paket["bericht"].read_text(encoding="utf-8")
        self.assertIn("Ohne Chat-Datei", bericht)


if __name__ == "__main__":
    unittest.main()
