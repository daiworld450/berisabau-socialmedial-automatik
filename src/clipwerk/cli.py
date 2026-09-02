"""Befehlszeile des Clip-Werks.

Erreichbar auf zwei Wegen, mit identischem Verhalten:

    python src/main.py clip analyse ...      (über die Haupt-Automatik)
    python -m clipwerk analyse ...           (Paket allein, ohne den Rest)

Der zweite Weg ist Absicht: das Clip-Werk soll auch dort laufen, wo weder
Instagram-Zugang noch Markenordner vorhanden sind - etwa auf dem Rechner,
auf dem geschnitten wird.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import AUSGABE, HASHTAG_DATEI, LEXIKON_DATEI, VERLAUF_DATEI
from . import (ausgabe, bewertung, lernkurve, motor, plan, quellen,
               render, verlauf)


def _stream_aus_argumenten(args) -> quellen.Stream:
    return quellen.lade_stream(
        stream_id=args.stream_id,
        datum=args.datum or date.today().isoformat(),
        streamer=args.streamer,
        transkript=Path(args.transkript) if args.transkript else None,
        chat=Path(args.chat) if args.chat else None,
        spiel=args.spiel or "",
        video=Path(args.video) if args.video else None,
    )


# --------------------------------------------------------------------------- #
def cmd_analyse(args) -> int:
    if not args.transkript and not args.chat:
        print("Weder --transkript noch --chat angegeben. Mindestens eine "
              "der beiden Quellen wird gebraucht.", file=sys.stderr)
        return 2
    stream = _stream_aus_argumenten(args)

    # Die Schwelle wandert mit der Betriebsart, wenn sie nicht vorgegeben
    # wurde - siehe bewertung.schwelle_fuer.
    if args.schwelle is None:
        args.schwelle = bewertung.schwelle_fuer(stream)
    if stream.nur_chat:
        print(f"Ohne Transkript: Momente kommen allein aus dem Chat. Keine "
              f"Untertitel, gröberer Zuschnitt, Schwelle {args.schwelle} "
              f"statt {bewertung.SCHWELLE_VERWERFEN} – Näheres im Bericht.")
    elif not stream.chat:
        print(f"Ohne Chat: Momente kommen allein aus der Sprache. Das "
              f"stärkste Signal fehlt, Schwelle {args.schwelle} statt "
              f"{bewertung.SCHWELLE_VERWERFEN} – Näheres im Bericht.")
    faktoren = {} if args.ohne_lernen else lernkurve.faktoren(Path(args.datenbank))
    if faktoren:
        print(f"Gelernte Gewichtung aktiv für: {', '.join(sorted(faktoren))}")

    ergebnis = motor.analysiere(
        stream, schwelle=args.schwelle, hoechstens=args.hoechstens,
        layout=args.layout or "", hat_facecam=not args.ohne_facecam,
        faktoren=faktoren, lexikon_datei=Path(args.lexikon),
        hashtag_datei=Path(args.hashtags))

    ziel = Path(args.ziel) if args.ziel else AUSGABE / f"{stream.stream_id}"
    facecam = render.Facecam.aus_text(args.facecam) if args.facecam else None
    paket = ausgabe.schreibe_paket(ergebnis, stream, ziel, facecam)

    print(f"\n{ergebnis.geprueft} Momente geprüft, "
          f"{len(ergebnis.clips)} Clips über {args.schwelle} Punkten.")
    for clip in ergebnis.clips:
        marke = "★" if clip.note.vorrang else " "
        print(f" {marke} {clip.nummer:02d}  {clip.note.punkte:3d}  "
              f"{clip.note.kategorie:<14} {clip.kandidat.dauer:4.0f}s  "
              f"{quellen.stempel(clip.kandidat.start, True)}  {clip.texte.hook}")

    print(f"\nBericht:  {paket['bericht']}")
    print(f"Rohdaten: {paket['json']}")
    if paket["skript"]:
        print(f"Rendern:  sh {paket['skript']}")
    elif stream.video is None:
        print("Kein --video angegeben – es wurde kein Renderskript erzeugt.")

    if args.aufnehmen and ergebnis.clips:
        eintraege = [c.verlaufseintrag(stream) for c in ergebnis.clips]
        bericht = verlauf.aufnehmen(eintraege, Path(args.datenbank),
                                    trockenlauf=args.trocken)
        print(f"\nDatenbank: {len(bericht['aufgenommen'])} neu, "
              f"{len(bericht['abgewiesen'])} als Doppelung abgewiesen, "
              f"{bericht['gesamt']} gesamt.")
        for neu, alt in bericht["abgewiesen"]:
            print(f"  = {neu} liegt schon als {alt} vor")
        if args.trocken:
            print("  (Trockenlauf – nichts geschrieben)")
    return 0


def cmd_diagnose(args) -> int:
    """Die nackten Zahlen hinter einer Auswertung - ohne Clips, ohne Texte.

    Gebaut, weil ein Lauf über Stream 2862735566 aus 1549 Sprachsegmenten
    null Clips ergab und der Bericht dazu nur sagen konnte "kein Moment hat
    die Schwelle erreicht". Das ist wahr und nutzlos: es unterscheidet
    einen langweiligen Stream nicht von einer falsch geeichten Kurve.

    Ausgegeben wird deshalb, woran sich das unterscheiden lässt: welche
    Signalreihen überhaupt tragen, wie hoch die Kurve tatsächlich liegt,
    wo die Spitzenschwelle steht - und wie sich die Punkte der gefundenen
    Momente verteilen. Bewusst keine Zitate: die Ausgabe soll in ein
    öffentliches Protokoll dürfen.
    """
    from . import kandidaten as kand
    from . import kategorien as kat
    from . import signale as sig

    stream = _stream_aus_argumenten(args)
    lexikon = sig.lade_lexikon(Path(args.lexikon))
    kurve = sig.kurve(stream, lexikon)

    def quantil(werte: list[float], anteil: float) -> float:
        if not werte:
            return 0.0
        sortiert = sorted(werte)
        return sortiert[min(len(sortiert) - 1, int(anteil * len(sortiert)))]

    print(f"Stream {stream.stream_id} · {quellen.stempel(stream.laenge, True)} "
          f"· {len(stream.segmente)} Sprachsegmente · {len(stream.chat)} Chat")
    print(f"Sensorbezug: {kurve.bezug}  "
          f"(1,0 = voller Sensorsatz; ohne Chat rund 0,53)")

    print("\nReihe                 belegt    Median>0     Höchstwert   Gewicht")
    for name in sig.GEWICHTE:
        reihe = kurve.reihen.get(name) or []
        aktiv = [w for w in reihe if w > 0]
        if not aktiv:
            continue
        import statistics as st
        print(f"  {name:<20} {len(aktiv)/len(reihe)*100:5.1f} %  "
              f"{st.median(aktiv):9.3f}  {max(aktiv):12.3f}  "
              f"{sig.GEWICHTE[name]:7.2f}")
    leer = [n for n in sig.GEWICHTE if not any(kurve.reihen.get(n) or [])]
    if leer:
        print(f"  ohne Daten: {', '.join(leer)}")

    print("\nKurve (gewichtete Summe über alle Reihen):")
    for anteil in (0.50, 0.90, 0.99, 0.999):
        print(f"  {anteil*100:6.1f} %   {quantil(kurve.gesamt, anteil):.3f}")
    print(f"  Höchstwert  {max(kurve.gesamt) if kurve.gesamt else 0:.3f}")

    schwelle_kurve = sig.SPITZENSCHWELLE * kurve.bezug
    ueber = sum(1 for w in kurve.gesamt if w >= schwelle_kurve)
    print(f"\nSpitzenschwelle {schwelle_kurve:.3f} "
          f"({sig.SPITZENSCHWELLE} × {kurve.bezug}) – "
          f"{ueber} von {len(kurve.gesamt)} Sekunden darüber.")

    spitzen = sig.spitzen(kurve, hoechstens=args.hoechstens * 3)
    print(f"{len(spitzen)} Spitzen mit Mindestabstand.")

    fuellwoerter = {w.lower() for w in lexikon.get("fuellwoerter", [])}
    rohe = []
    for spitze in spitzen:
        kandidat = kand.baue(stream, kurve, spitze, "", fuellwoerter)
        if kandidat:
            rohe.append(kandidat)
    rohe = kand.entdoppeln(rohe)
    print(f"{len(rohe)} Momente daraus gebaut.")
    if not rohe:
        return 0

    noten = [(bewertung.bewerte(k, kurve), k) for k in rohe]
    punkte = sorted(n.punkte for n, _ in noten)
    print(f"Punkte: tiefster {punkte[0]}, Median {punkte[len(punkte)//2]}, "
          f"höchster {punkte[-1]}; "
          f"{sum(1 for p in punkte if p >= 65)} ab 65, "
          f"{sum(1 for p in punkte if p >= 80)} ab 80.")

    noten.sort(key=lambda paar: -paar[0].punkte)
    print("\n  Punkte  Kategorie        Dauer  Zeit       "
          "Hook Unt Wat Sha Kom Fol   Stärke")
    for note, kandidat in noten[:args.zeigen]:
        print(f"  {note.punkte:6d}  {note.kategorie:<15} "
              f"{kandidat.dauer:4.0f}s  {quellen.stempel(kandidat.start, True):>9}  "
              f"{note.hook:4.0f}{note.unterhaltung:4.0f}{note.watchtime:4.0f}"
              f"{note.share:4.0f}{note.kommentar:4.0f}{note.follower:4.0f}   "
              f"{kandidat.staerke:6.2f}")
    return 0


def cmd_plan(args) -> int:
    if args.clips:
        daten = json.loads(Path(args.clips).read_text(encoding="utf-8"))
        clips = daten.get("clips", daten if isinstance(daten, list) else [])
    else:
        clips = verlauf.offen(Path(args.datenbank))
        for clip in clips:      # Datenbankeinträge tragen die Texte flach
            clip.setdefault("texte", {
                "hook": clip.get("hook", ""),
                "tiktok_titel": clip.get("hook", ""),
                "tiktok_caption": clip.get("caption", ""),
                "instagram_caption": clip.get("caption", ""),
                "youtube_titel": clip.get("hook", ""),
                "hashtags": clip.get("hashtags", []),
            })
    if not clips:
        print("Keine Clips zu planen.")
        return 0

    ab = date.fromisoformat(args.ab) if args.ab else date.today()
    plattformen = tuple(args.plattformen.split(","))
    zeitplan = plan.baue(clips, ab=ab, plattformen=plattformen)

    if args.json:
        print(json.dumps(plan.als_json(zeitplan), ensure_ascii=False, indent=2))
    else:
        print(plan.als_text(zeitplan))
        print(f"\n{len(zeitplan)} Veröffentlichungen, "
              f"{len({e.clip_id for e in zeitplan})} Clips, "
              f"ab {ab.isoformat()}.")
    return 0


def cmd_verlauf(args) -> int:
    pfad = Path(args.datenbank)
    if args.veroeffentlicht:
        kennung, plattform = args.veroeffentlicht
        erfolg = verlauf.veroeffentlicht(pfad, kennung, plattform,
                                         am=args.am, post_id=args.post_id or "")
        if erfolg:
            print(f"{kennung} auf {plattform} eingetragen.")
            return 0
        print(f"Nicht eingetragen: {kennung} gibt es nicht, oder er lief auf "
              f"{plattform} bereits (Abschnitt 13 – kein zweiter identischer "
              f"Post).")
        return 1

    daten = verlauf.lade(pfad)
    clips = daten["clips"]
    if args.offen:
        clips = [c for c in clips if not c.get("veroeffentlichungen")]
    if not clips:
        print("Datenbank ist leer." if not args.offen
              else "Alle Clips sind veröffentlicht.")
        return 0
    for clip in sorted(clips, key=lambda c: -c.get("score", 0)):
        laeufe = clip.get("veroeffentlichungen", [])
        wo = ", ".join(f"{l['plattform']}@{l['datum']}" for l in laeufe) or "—"
        print(f"{clip['clip_id']:<20} {clip.get('score', 0):>3}  "
              f"{clip.get('kategorie', ''):<14} {wo}")
    print(f"\n{len(clips)} Clips.")
    return 0


def cmd_kennzahlen(args) -> int:
    zahlen = {}
    for name in ("views", "watchtime_sekunden", "completion", "likes",
                 "kommentare", "shares", "saves", "follower"):
        wert = getattr(args, name)
        if wert is not None:
            zahlen[name] = wert
    if not zahlen:
        print("Keine Kennzahl angegeben – nichts einzutragen.")
        return 1
    erfolg = verlauf.performance(Path(args.datenbank), args.clip_id,
                                 args.plattform, zahlen)
    if not erfolg:
        print(f"{args.clip_id} auf {args.plattform} nicht gefunden. "
              f"Erst mit `verlauf --veroeffentlicht` eintragen.")
        return 1
    print(f"{args.clip_id} / {args.plattform}: "
          + ", ".join(f"{k}={v}" for k, v in zahlen.items()))
    return 0


def cmd_lernen(args) -> int:
    print(lernkurve.bericht(Path(args.datenbank)))
    return 0


def cmd_rendern(args) -> int:
    daten = json.loads(Path(args.clips).read_text(encoding="utf-8"))
    if not daten.get("clips"):
        print("Keine Clips in der Datei.")
        return 1

    video = Path(args.video)
    if not video.exists():
        print(f"Quellvideo nicht gefunden: {video}")
        return 1
    ordner = Path(args.clips).parent
    facecam = render.Facecam.aus_text(args.facecam) if args.facecam else None

    befehle = []
    for eintrag in daten["clips"]:
        kandidat = _kandidat_aus_dict(eintrag)
        name = f"clip-{eintrag['nummer']:02d}"
        ass = ordner / "untertitel" / f"{name}.ass"
        befehle.append(render.ffmpeg_befehl(
            video, kandidat, eintrag.get("layout", "vollbild"),
            ordner / f"{name}.mp4",
            untertitel=ass if ass.exists() else None,
            facecam=facecam,
            punch_fenster=_punch_aus_dict(eintrag)))

    skript = render.schreibe_skript(befehle, ordner / "rendern.sh")
    print(f"{len(befehle)} Befehle geschrieben: {skript}")
    if args.ausfuehren:
        if not render.ffmpeg_vorhanden():
            print("ffmpeg fehlt – nur das Skript wurde geschrieben.")
            return 1
        for nummer, befehl in enumerate(befehle, start=1):
            erfolg, fehler = render.rendere(befehl)
            print(f"  {nummer:02d} {'fertig' if erfolg else 'FEHLER: ' + fehler}")
    return 0


def _kandidat_aus_dict(eintrag: dict):
    """Nur so viel Kandidat, wie der Renderer braucht."""
    from .kandidaten import Kandidat
    return Kandidat(
        start=float(eintrag["start"]), ende=float(eintrag["ende"]),
        hoehepunkt=float(eintrag.get("hoehepunkt", eintrag["start"])),
        staerke=0.0, anteile={},
        auslassungen=[(float(a), float(b))
                      for a, b in eintrag.get("auslassungen", [])])


def _punch_aus_dict(eintrag: dict) -> list[tuple[float, float]]:
    fenster = []
    for zeile in eintrag.get("schnitt", []):
        if "Punch-In" not in zeile:
            continue
        marke = zeile.split(" ", 1)[0]
        if "–" not in marke:
            continue
        von, bis = marke.split("–")
        fenster.append((_sek(von), _sek(bis)))
    return fenster


def _sek(mmss: str) -> float:
    minute, sek = mmss.split(":")
    return int(minute) * 60 + int(sek)


# --------------------------------------------------------------------------- #
def baue_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clip", description="Clip-Werk – Twitch-Stream zu Shorts")
    unter = p.add_subparsers(dest="befehl", required=True)

    a = unter.add_parser("analyse", help="Stream analysieren und Clips erzeugen")
    a.add_argument("--transkript",
                   help="SRT, VTT oder Whisper-JSON; ohne das läuft der "
                        "Chat-Modus (schneller, aber ohne Untertitel)")
    a.add_argument("--chat", help="Chat als VOD-Export, JSONL oder IRC-Mitschnitt")
    a.add_argument("--stream-id", required=True, help="z. B. die Twitch-VOD-ID")
    a.add_argument("--datum", help="Streamdatum, Vorgabe: heute")
    a.add_argument("--streamer", required=True)
    a.add_argument("--spiel", help="für Hashtags und Layoutwahl")
    a.add_argument("--video", help="Quellvideo – ohne das kein Renderskript")
    a.add_argument("--facecam", help="Webcam im Quellbild als x:y:breite:höhe")
    a.add_argument("--ohne-facecam", action="store_true",
                   help="reines Vollbild, kein geteiltes Layout")
    a.add_argument("--layout", help="Layout erzwingen statt je Kategorie wählen")
    a.add_argument("--schwelle", type=int,
                   help="Mindestpunktzahl (Vorgabe 65, im Chat-Modus 58)")
    a.add_argument("--hoechstens", type=int, default=30,
                   help="Höchstzahl Clips (Vorgabe 30)")
    a.add_argument("--ziel", help="Ausgabeordner")
    a.add_argument("--aufnehmen", action="store_true",
                   help="Clips in die Datenbank gegen Doppelungen eintragen")
    a.add_argument("--trocken", action="store_true")
    a.add_argument("--ohne-lernen", action="store_true",
                   help="gelernte Gewichtung nicht anwenden")
    a.add_argument("--lexikon", default=str(LEXIKON_DATEI))
    a.add_argument("--hashtags", default=str(HASHTAG_DATEI))
    a.add_argument("--datenbank", default=str(VERLAUF_DATEI))
    a.set_defaults(func=cmd_analyse)

    d = unter.add_parser("diagnose",
                         help="Zahlen hinter einer Auswertung, ohne Clips")
    d.add_argument("--transkript")
    d.add_argument("--chat")
    d.add_argument("--stream-id", required=True)
    d.add_argument("--datum")
    d.add_argument("--streamer", default="")
    d.add_argument("--spiel", default="")
    d.add_argument("--video")
    d.add_argument("--lexikon", default=str(LEXIKON_DATEI))
    d.add_argument("--hoechstens", type=int, default=30)
    d.add_argument("--zeigen", type=int, default=15,
                   help="wie viele Momente einzeln aufgelistet werden")
    d.set_defaults(func=cmd_diagnose)

    pl = unter.add_parser("plan", help="Veröffentlichungsplan bauen")
    pl.add_argument("--clips", help="clips.json aus der Analyse")
    pl.add_argument("--ab", help="erster Tag, Vorgabe heute")
    pl.add_argument("--plattformen", default="tiktok,instagram,youtube")
    pl.add_argument("--json", action="store_true")
    pl.add_argument("--datenbank", default=str(VERLAUF_DATEI))
    pl.set_defaults(func=cmd_plan)

    v = unter.add_parser("verlauf", help="Clip-Datenbank ansehen und pflegen")
    v.add_argument("--offen", action="store_true",
                   help="nur Clips, die noch nirgends liefen")
    v.add_argument("--veroeffentlicht", nargs=2, metavar=("CLIP_ID", "PLATTFORM"))
    v.add_argument("--am", help="Veröffentlichungsdatum, Vorgabe heute")
    v.add_argument("--post-id")
    v.add_argument("--datenbank", default=str(VERLAUF_DATEI))
    v.set_defaults(func=cmd_verlauf)

    k = unter.add_parser("kennzahlen", help="Leistung eines Clips eintragen")
    k.add_argument("clip_id")
    k.add_argument("plattform")
    for name, typ in (("views", int), ("watchtime_sekunden", float),
                      ("completion", float), ("likes", int),
                      ("kommentare", int), ("shares", int), ("saves", int),
                      ("follower", int)):
        k.add_argument(f"--{name.replace('_', '-')}", dest=name, type=typ)
    k.add_argument("--datenbank", default=str(VERLAUF_DATEI))
    k.set_defaults(func=cmd_kennzahlen)

    l = unter.add_parser("lernen", help="was aus den Zahlen gelernt wurde")
    l.add_argument("--datenbank", default=str(VERLAUF_DATEI))
    l.set_defaults(func=cmd_lernen)

    r = unter.add_parser("rendern", help="ffmpeg-Skript aus clips.json bauen")
    r.add_argument("--clips", required=True)
    r.add_argument("--video", required=True)
    r.add_argument("--facecam")
    r.add_argument("--ausfuehren", action="store_true",
                   help="Befehle sofort ausführen statt nur zu schreiben")
    r.set_defaults(func=cmd_rendern)

    return p


def main(argv: list[str] | None = None) -> int:
    args = baue_parser().parse_args(argv)
    try:
        return args.func(args)
    except (quellen.QuellenFehler, ValueError, FileNotFoundError) as fehler:
        print(f"Abbruch: {fehler}", file=sys.stderr)
        return 2
