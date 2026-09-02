"""Die Kette von der Rohdatei bis zum fertigen Clip-Datensatz.

Ein Aufruf, ein Stream, eine Liste Clips. Was hier passiert, ist genau die
Reihenfolge der Betriebsanweisung: erst den *ganzen* Stream ansehen
(Abschnitt 1), dann bewerten (2), dann kürzen (3), dann Einstieg, Schnitt,
Untertitel und Texte (4-7, 10).

Die Reihenfolge hat einen Grund, der leicht übersehen wird: die Kategorie
steht vor dem endgültigen Fenster. Ein STORY-Clip darf 60 Sekunden lang
sein, ein FUNNY-Clip nicht - also wird erst grob eingeschätzt, dann
zugeschnitten, dann endgültig bewertet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import HASHTAG_DATEI, LEXIKON_DATEI
from . import bewertung as bew
from . import kandidaten as kand
from . import kategorien as kat
from . import schnitt as schn
from . import signale as sig
from . import texte as txt
from . import untertitel as unt
from . import verlauf
from .quellen import Stream, stempel


@dataclass
class Clip:
    """Ein fertig ausgearbeiteter Clip - alles, was Abschnitt 10 verlangt."""
    nummer: int
    kandidat: kand.Kandidat
    note: bew.Bewertung
    plan: schn.Schnittplan
    texte: txt.Texte
    zeilen: list[unt.Zeile] = field(default_factory=list)
    clip_id: str = ""

    def als_dict(self, stream: Stream) -> dict:
        k, n = self.kandidat, self.note
        return {
            "nummer": self.nummer,
            "clip_id": self.clip_id,
            "stream_id": stream.stream_id,
            "datum": stream.datum,
            "streamer": stream.streamer,
            "spiel": stream.spiel,
            "start": round(k.start, 2),
            "ende": round(k.ende, 2),
            "start_stempel": stempel(k.start),
            "ende_stempel": stempel(k.ende),
            "dauer": round(k.dauer, 1),
            "roh_dauer": round(k.roh_dauer, 1),
            "auslassungen": [[round(a, 2), round(b, 2)] for a, b in k.auslassungen],
            "hoehepunkt": round(k.hoehepunkt, 2),
            "kategorie": n.kategorie,
            "score": n.punkte,
            "vorrang": n.vorrang,
            "punkte": {"hook": n.hook, "unterhaltung": n.unterhaltung,
                       "watchtime": n.watchtime, "share": n.share,
                       "kommentar": n.kommentar, "follower": n.follower},
            "teilnoten": n.teilnoten,
            "begruendung": n.begruendung,
            "thema": k.text,
            "layout": self.plan.layout,
            "schnitt": [a.zeile() for a in self.plan.anweisungen],
            "loop": self.plan.loop,
            "loop_hinweis": self.plan.loop_hinweis,
            "untertitel": unt.als_text(self.zeilen),
            "untertitel_zeilen": [{"start": z.start, "ende": z.ende,
                                   "text": z.text} for z in self.zeilen],
            "texte": {
                "hook": self.texte.hook,
                "kernzitat": self.texte.kernzitat,
                "tiktok_titel": self.texte.tiktok_titel,
                "tiktok_caption": self.texte.tiktok_caption,
                "instagram_caption": self.texte.instagram_caption,
                "youtube_titel": self.texte.youtube_titel,
                "hashtags": self.texte.hashtags,
            },
            "hook_varianten": {
                "tiktok": txt.variante(self.texte, "tiktok"),
                "instagram": txt.variante(self.texte, "instagram"),
                "youtube": txt.variante(self.texte, "youtube"),
            },
        }

    def verlaufseintrag(self, stream: Stream) -> dict:
        """Der schlanke Datensatz für die Clip-Datenbank (Abschnitt 13)."""
        return {
            "clip_id": self.clip_id,
            "stream_id": stream.stream_id,
            "datum": stream.datum,
            "start": round(self.kandidat.start, 2),
            "ende": round(self.kandidat.ende, 2),
            "dauer": round(self.kandidat.dauer, 1),
            "thema": self.kandidat.text[:400],
            "kategorie": self.note.kategorie,
            "caption": self.texte.tiktok_caption,
            "hook": self.texte.hook,
            "score": self.note.punkte,
            "hashtags": self.texte.hashtags,
            "veroeffentlichungen": [],
        }


@dataclass
class Ergebnis:
    clips: list[Clip] = field(default_factory=list)
    verworfen: list[tuple[float, int, str]] = field(default_factory=list)
    kurve: sig.Signalkurve | None = None
    geprueft: int = 0
    schwelle: int = bew.SCHWELLE_VERWERFEN


def analysiere(stream: Stream, *, schwelle: int = bew.SCHWELLE_VERWERFEN,
               hoechstens: int = 30, layout: str = "",
               hat_facecam: bool = True,
               faktoren: dict | None = None,
               lexikon_datei: Path = LEXIKON_DATEI,
               hashtag_datei: Path = HASHTAG_DATEI) -> Ergebnis:
    lexikon = sig.lade_lexikon(lexikon_datei)
    hashtag_saetze = kat.lade_hashtags(hashtag_datei)

    kurve = sig.kurve(stream, lexikon)
    # Großzügig suchen und hart aussortieren ist billiger als andersherum:
    # ein verworfener Kandidat kostet Rechenzeit, ein übersehener Moment
    # kostet einen Clip.
    spitzen = sig.spitzen(kurve, hoechstens=max(60, hoechstens * 3))

    fuellwoerter = {w.lower() for w in lexikon.get("fuellwoerter", [])}

    rohe: list[kand.Kandidat] = []
    for spitze in spitzen:
        # Zwei Durchgänge: der erste liefert überhaupt erst ein Fenster, aus
        # dem sich die Kategorie ablesen lässt. Erst wenn dabei eine
        # erzählende Kategorie herauskommt, darf der Clip die 60 Sekunden
        # aus Abschnitt 3 nutzen - und wird dafür neu geschnitten.
        kandidat = kand.baue(stream, kurve, spitze, "", fuellwoerter)
        if not kandidat:
            continue
        kategorie, _ = kat.bestimme(kandidat.anteile, kandidat.text)
        if kategorie in kand.ERZAEHLEND:
            laenger = kand.baue(stream, kurve, spitze, kategorie, fuellwoerter)
            if laenger:
                kandidat = laenger
        rohe.append(kandidat)
    rohe = kand.entdoppeln(rohe)

    ergebnis = Ergebnis(kurve=kurve, geprueft=len(rohe), schwelle=int(schwelle))
    bewertet: list[tuple[bew.Bewertung, kand.Kandidat]] = []
    for kandidat in rohe:
        note = bew.bewerte(kandidat, kurve, faktoren)
        if note.punkte < schwelle:
            ergebnis.verworfen.append((kandidat.start, note.punkte, note.kategorie))
            continue
        bewertet.append((note, kandidat))

    # Bestes zuerst auswählen, danach wieder nach Streamzeit sortieren -
    # so bleibt die Nummerierung im Bericht chronologisch lesbar.
    bewertet.sort(key=lambda p: -p[0].punkte)
    bewertet = bewertet[:hoechstens]
    bewertet.sort(key=lambda p: p[1].start)

    # Über alle Clips eines Streams hinweg gemerkt: kein Aufmacher soll
    # zweimal dastehen, solange es noch eine ungenutzte Fassung gibt.
    benutzte_hooks: set[str] = set()
    for nummer, (note, kandidat) in enumerate(bewertet, start=1):
        plan = schn.plane(kandidat, note, kurve, stream, layout, hat_facecam)
        texte = txt.baue(kandidat, note, stream.streamer, stream.spiel,
                         hashtag_saetze, benutzte_hooks=benutzte_hooks)
        zeilen = unt.zeilen(kandidat, lexikon)
        ergebnis.clips.append(Clip(
            nummer=nummer, kandidat=kandidat, note=note, plan=plan,
            texte=texte, zeilen=zeilen,
            clip_id=verlauf.clip_id(stream.stream_id, kandidat.start),
        ))
    return ergebnis


def punch_fenster(clip: Clip) -> list[tuple[float, float]]:
    """Die Zeitfenster aus dem Schnittplan, in denen gezoomt wird."""
    return [(a.von, a.bis) for a in clip.plan.anweisungen
            if "Punch-In" in a.text and a.bis > a.von]
