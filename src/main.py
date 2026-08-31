"""Berisa Bau – täglicher Instagram-Post.

Beispiele:
    python src/main.py vorschau            7 Tage planen und als PNG rendern
    python src/main.py heute               Post für heute erzeugen (ohne Posten)
    python src/main.py heute --posten      erzeugen und veröffentlichen
    python src/main.py muster              alle Vorlagen einmal rendern
    python src/main.py zugang              Instagram-Verbindung prüfen
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

import shutil                # noqa: E402
import datetime as _dt       # noqa: E402
from config import OUT_DIR   # noqa: E402

# Nur für die Instagram-Beitragserzeugung nötig (jinja2/playwright). Die
# Google-Ads-Kanal-Befehle (ads-news/ads-kurzcheck/ads-empfehlung) brauchen
# das nicht und laufen in einer schlankeren GitHub-Actions-Umgebung ohne
# diese Abhängigkeiten - deshalb hier optional statt hart importiert.
try:
    import freigaben         # noqa: E402
    import planer            # noqa: E402
    import texter            # noqa: E402
    from renderer import kuerze_dateiname, rendere   # noqa: E402
except ImportError:
    freigaben = planer = texter = None
    kuerze_dateiname = rendere = None


def _erzeuge(plan: dict, format: str = "feed") -> Path:
    """Rendert den Beitrag. Bei Carousels die erste Slide (die sichtbare Kachel)."""
    # .jpg, weil die Instagram-API für image_url nur JPEG akzeptiert.
    name = f"{plan['datum']}_{plan['rubrik']}_{kuerze_dateiname(plan['id'])}.jpg"
    vorlage = plan.get("felder", {}).get("vorlage") or plan["vorlage"]
    return rendere(vorlage, plan["felder"], name, format=format)


def _erzeuge_alle(plan: dict, format: str = "feed") -> list[Path]:
    """Alle Bilder eines Beitrags – bei Einzelposts eins, bei Carousels alle Slides."""
    if plan.get("typ") != "carousel":
        return [_erzeuge(plan, format)]

    basis = f"{plan['datum']}_{plan['rubrik']}_{kuerze_dateiname(plan['id'])}"
    pfade = []
    for nr, slide in enumerate(plan["slides"], start=1):
        daten = {k: v for k, v in slide.items() if k != "vorlage"}
        pfade.append(rendere(slide["vorlage"], daten,
                             f"{basis}_{nr:02d}.jpg", format=format))
    return pfade


def _video_zielname(plan: dict) -> str:
    """Dateiname, unter dem das Reel-Video in out/ und docs/posts/ landet.

    Dieselbe Namensbildung wie beim Titelbild (_erzeuge) – nur so findet der
    Veröffentlichungsschritt später dieselbe Datei wieder, die der Render-
    Schritt schon öffentlich abgelegt hat.
    """
    quelle = Path(plan["video"])
    basis = f"{plan['datum']}_{plan['rubrik']}_{kuerze_dateiname(plan['id'])}"
    return f"{basis}{quelle.suffix.lower()}"


def _kopiere_video(plan: dict) -> Path:
    """Kopiert das Rohvideo aus content/medien/projekte/ nach out/.

    Das Original bleibt unangetastet im Projektordner; erst diese Kopie wird
    vom Workflow nach docs/posts/ übernommen und damit öffentlich erreichbar
    – genau wie das gerenderte Titelbild.
    """
    ziel = OUT_DIR / _video_zielname(plan)
    shutil.copy2(plan["video"], ziel)
    return ziel


def _schreibe_caption(plan: dict, bild: Path, mit_ki: bool) -> Path:
    caption = texter.baue_caption(plan, mit_ki=mit_ki)
    ziel = bild.with_suffix(".txt")
    ziel.write_text(caption, encoding="utf-8")
    # Facebook-Fassung immer mit ablegen – so lassen sich beide vergleichen,
    # auch wenn Facebook noch nicht eingerichtet ist.
    bild.with_suffix(".facebook.txt").write_text(
        texter.baue_caption_facebook(plan), encoding="utf-8")
    return ziel


# --------------------------------------------------------------------------- #
def cmd_vorschau(args) -> int:
    plaene = planer.vorschau(args.tage)
    print(f"\nPlan für die nächsten {args.tage} Tage:\n")
    for p in plaene:
        tag = date.fromisoformat(p["datum"])
        wochentag = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][tag.weekday()]
        print(f"  {wochentag} {p['datum']}  {p['rubrik']:<15} {p['id']}")
        if args.rendern:
            bild = _erzeuge(p)
            _schreibe_caption(p, bild, mit_ki=False)
            print(f"       -> {bild.name}")
    print()
    return 0


def _schon_veroeffentlicht(tag: date) -> bool:
    """Ob für dieses Datum bereits ein Post im Verlauf steht.

    Verhindert einen doppelten Post am selben Tag, wenn die Telegram-
    Freigabe schon veröffentlicht hat, bevor der planmäßige Cron-Lauf greift
    (oder umgekehrt bei manuellem Nachtriggern).
    """
    return any(e["datum"] == tag.isoformat() for e in planer.lade_verlauf()["eintraege"])


def _gesperrte_medien_melden() -> str:
    """Gibt eine Warnung zurueck, wenn Fotos ohne Einwilligung liegenbleiben.

    Ohne diese Meldung faellt der Planer stillschweigend auf einen Textbeitrag
    zurueck, und niemand merkt wochenlang, dass die Baustellenfotos gesperrt
    sind.
    """
    import einwilligung
    from config import MEDIEN_DIR
    medien = [p for p in MEDIEN_DIR.rglob("*")
              if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png",
                                                      ".mp4", ".mov"}
              and not p.name.startswith(".")] if MEDIEN_DIR.exists() else []
    gesperrt = einwilligung.gesperrte(medien)
    if not gesperrt:
        return ""
    motive = {p.name.split("_", 1)[-1] for p in gesperrt}
    return (f"\n⚠️  {len(motive)} Motiv(e) gesperrt - keine Einwilligung des "
            f"Kunden hinterlegt.\n    Eintragen: einwilligungen/"
            f"EINWILLIGUNG-EINTRAGEN.command\n")


def cmd_heute(args) -> int:
    tag = date.fromisoformat(args.datum) if args.datum else date.today()

    warnung = _gesperrte_medien_melden()
    if warnung:
        print(warnung)

    # Früh raus, bevor unnötig gerendert und nach docs/posts gepusht wird:
    # bei --posten zählt nur, ob für diesen Tag schon etwas draußen ist
    # (z. B. per Telegram-Freigabe) - eine reine Vorschau ohne --posten soll
    # trotzdem weiter funktionieren.
    if args.posten and _schon_veroeffentlicht(tag):
        print(f"\nFür {tag.isoformat()} wurde bereits veröffentlicht "
              f"(z. B. per Telegram-Freigabe). Kein weiterer Post.\n")
        return 0

    plan = planer.plane(tag)

    if plan is None:
        posttage_namen = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        geplant = sorted(planer.POSTTAGE)
        print(f"\nKein Posttag: {tag.strftime('%A, %d.%m.%Y')}. "
              f"Gepostet wird an {' und '.join(posttage_namen[t] for t in geplant)}.\n")
        return 0

    print(f"\nRubrik   : {plan['rubrik']}")
    print(f"Thema    : {plan['id']}")
    print(f"Gewerk   : {plan.get('gewerk')}")

    bild = _erzeuge(plan)
    caption_datei = _schreibe_caption(plan, bild, mit_ki=args.ki)
    print(f"Bild     : {bild}")
    print(f"Text     : {caption_datei}")
    if plan.get("typ") == "reel":
        video = _kopiere_video(plan)
        print(f"Video    : {video}")

    if not args.posten:
        print("\nNicht veröffentlicht (kein --posten). "
              "Bild und Text liegen in out/ zur Kontrolle.\n")
        return 0

    import telegram_bot
    from config import FREIGABE_PFLICHT

    # Ist Telegram eingerichtet, gilt dieselbe Sperre wie bei FREIGABE_PFLICHT:
    # erst wenn im Chat auf "Freigeben" getippt wurde, darf veröffentlicht
    # werden. So postet der planmäßige Cron-Lauf nichts Unbestätigtes.
    if not freigaben.ist_frei(plan["id"]) and (FREIGABE_PFLICHT or telegram_bot.aktiv()):
        if telegram_bot.aktiv():
            print(f"\nWartet auf Telegram-Freigabe für '{plan['id']}'. "
                  "Läuft automatisch mit 'telegram-abfragen', sobald bestätigt.\n")
        else:
            print(f"\nGESPERRT: '{plan['id']}' ist nicht freigegeben.\n"
                  f"Freigeben mit: python src/main.py freigeben {plan['id']}\n",
                  file=sys.stderr)
        return 2

    return _veroeffentliche(plan, tag, bild, caption_datei,
                            trocken=args.trocken, kein_facebook=args.kein_facebook)


def _veroeffentliche(plan: dict, tag: date, bild: Path, caption_datei: Path,
                     trocken: bool = False, kein_facebook: bool = False) -> int:
    """Veröffentlicht einen fertig gerenderten Post auf Instagram (und Facebook).

    Eigene Funktion statt Teil von cmd_heute: die Telegram-Freigabeschleife
    braucht denselben Ablauf, hat aber keine argparse-Namespace zur Hand.
    """
    import publisher

    caption = caption_datei.read_text(encoding="utf-8")
    alt_text = texter.baue_alt_text(plan)
    typ = plan.get("typ", "einzel")
    try:
        if typ == "reel":
            print(f"Typ      : Reel ({_video_zielname(plan)})")
            ergebnis = publisher.veroeffentliche_reel(
                _video_zielname(plan), caption,
                titelbild_dateiname=bild.name, trockenlauf=trocken)
        elif typ == "carousel":
            slides = _erzeuge_alle(plan)
            print(f"Typ      : Carousel mit {len(slides)} Slides")
            ergebnis = publisher.veroeffentliche_carousel(
                [p.name for p in slides], caption, trockenlauf=trocken)
        else:
            ergebnis = publisher.veroeffentliche(bild.name, caption, alt_text=alt_text,
                                                 trockenlauf=trocken)
    except publisher.KontingentErschoepft as fehler:
        # Kein Fehlschlag im eigentlichen Sinn – der Beitrag kommt morgen.
        print(f"\n{fehler}\n")
        publisher.protokolliere(plan["id"], bild.name, None, str(fehler))
        return 0
    except publisher.VeroeffentlichungsFehler as fehler:
        print(f"\nFEHLER beim Veröffentlichen: {fehler}", file=sys.stderr)
        if fehler.token_problem:
            print("Das ist ein Token-Problem. Schritt 4 in "
                  "docs/02-INSTAGRAM-EINRICHTEN.md wiederholen.", file=sys.stderr)
        print(file=sys.stderr)
        publisher.protokolliere(plan["id"], bild.name, None, str(fehler))
        return 1

    print(f"Instagram: {ergebnis.meldung} {ergebnis.id or ''}")
    if ergebnis.permalink:
        print(f"Link     : {ergebnis.permalink}")
    if not trocken:
        planer.vermerke(plan["id"], tag, bild.name, ergebnis.id)
        publisher.protokolliere(plan["id"], bild.name, ergebnis)
        print("Verlauf  : eingetragen")

    _auch_facebook(plan, bild, typ, trocken=trocken, kein_facebook=kein_facebook)
    print()
    return 0


def _auch_facebook(plan: dict, bild, typ: str, trocken: bool = False,
                   kein_facebook: bool = False) -> None:
    """Denselben Beitrag zusätzlich auf die Facebook-Seite stellen.

    Bewusst nach Instagram und in einem eigenen Fehlerkorridor: Klemmt
    Facebook, ist der Instagram-Beitrag trotzdem draußen und der Lauf gilt
    nicht als gescheitert.
    """
    import facebook

    if kein_facebook or not facebook.aktiv():
        return

    text = texter.baue_caption_facebook(plan)
    try:
        if typ == "reel":
            ergebnis = facebook.veroeffentliche_video(
                _video_zielname(plan), text,
                titel=plan["felder"].get("titel_stark", ""),
                trockenlauf=trocken)
        elif typ == "carousel":
            slides = _erzeuge_alle(plan)
            ergebnis = facebook.veroeffentliche_album(
                [s.name for s in slides], text, trockenlauf=trocken)
        else:
            ergebnis = facebook.veroeffentliche_bild(
                bild.name, text, trockenlauf=trocken)
    except facebook.FacebookFehler as fehler:
        print(f"Facebook : FEHLER – {fehler}", file=sys.stderr)
        if fehler.token_problem:
            print("           Seiten-Token erneuern, siehe "
                  "docs/03-FACEBOOK-EINRICHTEN.md", file=sys.stderr)
        return

    print(f"Facebook : {ergebnis.meldung}")
    if ergebnis.permalink:
        print(f"Link     : {ergebnis.permalink}")


def cmd_export(args) -> int:
    import export
    import monatsplan
    heute = date.today()
    jahr = args.jahr or heute.year
    monat = args.monat or heute.month

    print(f"\nErzeuge Beitragspaket {monatsplan.MONATE[monat - 1]} {jahr} …")
    if args.ohne_bilder:
        print("  (ohne Bilder – nur Tabelle und Texte)")
    ordner = export.exportiere(jahr, monat, bilder=not args.ohne_bilder)

    anzahl = len(list((ordner / "texte").glob("*.txt")))
    print(f"\nFertig: {anzahl} Beiträge in\n  {ordner}\n")
    print("  UEBERSICHT.html   die Tabelle – Doppelklick genügt")
    print("  tabelle.csv       dieselben Daten für Excel")
    print("  bilder/           die fertigen Beitragsbilder")
    print("  texte/            jeder Text als einzelne Datei")
    print("  LIESMICH.txt      Kurzerklärung\n")
    return 0


def cmd_fotos_verarbeiten(args) -> int:
    import fotoeingang
    ergebnis = fotoeingang.verarbeite_eingang()

    if not ergebnis["verarbeitet"] and not ergebnis["fehlgeschlagen"]:
        print("\nKeine neuen Fotos im Eingang "
              "(content/medien/eingang/).\n")
        return 0

    print(f"\n{len(ergebnis['verarbeitet'])} Foto(s) verarbeitet:")
    for e in ergebnis["verarbeitet"]:
        print(f"  {e['eingang']}  ->  pool/{e['pool']}")

    if ergebnis["fehlgeschlagen"]:
        print(f"\n{len(ergebnis['fehlgeschlagen'])} Foto(s) fehlgeschlagen:")
        for f in ergebnis["fehlgeschlagen"]:
            print(f"  {f['datei']}: {f['grund']}")

    print()
    return 1 if ergebnis["fehlgeschlagen"] else 0


WARTESCHLANGE_DATEI = Path(__file__).resolve().parent.parent / "content" / "telegram_warteschlange.json"


def _warteschlange_laden() -> dict:
    if WARTESCHLANGE_DATEI.exists():
        daten = json.loads(WARTESCHLANGE_DATEI.read_text(encoding="utf-8"))
        # Migration: altes Feld letzte_update_id galt für den einen,
        # gemeinsamen Bot - seit 28.08.2026 zwei getrennte Bots/Zähler.
        if "letzte_update_id" in daten and "letzte_update_id_social" not in daten:
            daten["letzte_update_id_social"] = daten.pop("letzte_update_id")
            daten.setdefault("letzte_update_id_ads", 0)
        return daten
    return {"letzte_update_id_social": 0, "letzte_update_id_ads": 0, "wartend": {}}


def _warteschlange_speichern(daten: dict) -> None:
    WARTESCHLANGE_DATEI.write_text(
        json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")


def _telegram_kurztext(plan: dict, caption: str) -> str:
    hook = caption.splitlines()[0] if caption else ""
    nummer = plan.get("felder", {}).get("nummer", "")
    return f"#{nummer}  {plan['rubrik']} · {plan['id']}\n\n{hook}"


def cmd_vorschlagen(args) -> int:
    """Rendert den nächsten Kandidaten und schickt ihn zur Freigabe an Telegram.

    Läuft eine Weile vor dem eigentlichen Posttermin (siehe
    .github/workflows/vorschlagen.yml), damit für Ablehnungen und einen
    neuen Vorschlag noch Zeit bleibt, bevor 'heute --posten' feuert.
    """
    import telegram_bot

    if not telegram_bot.aktiv():
        print("\nTelegram ist nicht eingerichtet (TELEGRAM_BOT_TOKEN_BERISABAUSOCIALMEDIA / "
              "TELEGRAM_CHAT_ID fehlen). Anleitung: "
              "docs/04-TELEGRAM-EINRICHTEN.md\n", file=sys.stderr)
        return 1

    tag = date.fromisoformat(args.datum) if args.datum else date.today()
    schlange = _warteschlange_laden()

    if schlange["wartend"].get(tag.isoformat()):
        print(f"\nFür {tag.isoformat()} liegt bereits ein offener Vorschlag in "
              "Telegram. Nichts erneut geschickt.\n")
        return 0

    if _schon_veroeffentlicht(tag):
        print(f"\nFür {tag.isoformat()} wurde bereits veröffentlicht.\n")
        return 0

    plan = planer.plane(tag)
    if plan is None:
        print(f"\nKein Posttag: {tag.strftime('%A, %d.%m.%Y')}.\n")
        return 0

    bild = _erzeuge(plan)
    caption_datei = _schreibe_caption(plan, bild, mit_ki=False)
    caption = caption_datei.read_text(encoding="utf-8")

    vorschlag = telegram_bot.sende_vorschlag(
        bild, _telegram_kurztext(plan, caption), caption, plan["id"])

    schlange["wartend"][tag.isoformat()] = {
        "plan_id": plan["id"],
        "nachricht_id": vorschlag.nachricht_id,
        "abgelehnt": [],
    }
    _warteschlange_speichern(schlange)
    print(f"\nVorschlag an Telegram geschickt: {plan['id']} ({plan['rubrik']})\n")
    return 0


def _verarbeite_ads_callback(aktion: str, hash_id: str, antwort: dict) -> None:
    """Merken/Mehr dazu/Ignorieren für den Google-Ads-Kanal - unabhängig von
    der Instagram-Warteschlange, Nachschlagen per URL-Hash statt plan_id."""
    import ads_verlauf
    import telegram_bot
    from config import TELEGRAM_CHAT_ID_ADS

    eintrag = ads_verlauf.hole_meldung(hash_id)
    if eintrag is None:
        telegram_bot.beantworte_callback(antwort["callback_query_id"],
                                         "Dazu liegt kein Eintrag mehr vor.", ads=True)
        return

    if aktion == "merken":
        ads_verlauf.merken(hash_id)
        telegram_bot.beantworte_callback(antwort["callback_query_id"], "Gemerkt.", ads=True)
    elif aktion == "mehr":
        telegram_bot.beantworte_callback(antwort["callback_query_id"], "Kommt …", ads=True)
        telegram_bot.sende_text(eintrag["volltext"], chat_id=TELEGRAM_CHAT_ID_ADS)
    elif aktion == "ignorieren":
        ads_verlauf.ignorieren(hash_id, eintrag["ueberschrift"])
        telegram_bot.beantworte_callback(antwort["callback_query_id"],
                                         "Ignoriert – kommt nicht wieder.", ads=True)
        telegram_bot.markiere_text(antwort["nachricht_id"],
                                   f"🚫 Ignoriert: {eintrag['ueberschrift']}",
                                   chat_id=TELEGRAM_CHAT_ID_ADS)


def _verarbeite_textbefehl(befehl: str, schlange: dict) -> None:
    """Getippte Befehle im Telegram-Chat.

    Der Bot war bis 29.08.2026 rein reaktiv: Vorschläge kamen nur nach Plan,
    reagieren konnte man nur mit den beiden Tasten. Wer zwischendurch etwas
    sehen wollte, hatte keine Möglichkeit dazu. Diese Befehle schließen die
    Lücke - der wichtigste ist /neu.
    """
    import telegram_bot

    if befehl in ("start", "hilfe", "help"):
        telegram_bot.sende_text(
            "Berisa Bau - Social-Bot\n\n"
            "/neu     - neuen Vorschlag schicken (jederzeit)\n"
            "/anders  - denselben Tag, anderes Thema\n"
            "/status  - was gerade offen ist\n"
            "/hilfe   - diese Übersicht\n\n"
            "Bei jedem Vorschlag: ✅ Freigeben oder ❌ Ablehnen.\n"
            "Abgelehnt heißt: es kommt sofort ein anderer.")
        return

    if befehl == "status":
        offen = schlange.get("wartend") or {}
        if not offen:
            zeilen = ["Gerade liegt nichts zur Freigabe."]
        else:
            zeilen = ["Offen zur Freigabe:"]
            for tag_iso, eintrag in sorted(offen.items()):
                abgelehnt = len(eintrag.get("abgelehnt") or [])
                zusatz = f", {abgelehnt} schon abgelehnt" if abgelehnt else ""
                zeilen.append(f"  {tag_iso}: {eintrag['plan_id']}{zusatz}")
        naechster = _naechster_posttag()
        if naechster:
            zeilen.append(f"\nNächster Posttag: {naechster.strftime('%A, %d.%m.%Y')}")
        telegram_bot.sende_text("\n".join(zeilen))
        return

    if befehl in ("neu", "vorschlag", "anders", "nochmal"):
        _schicke_vorschlag_auf_wunsch(schlange, anderes_thema=(befehl == "anders"))
        return

    telegram_bot.sende_text(
        f"Unbekannter Befehl /{befehl}. /hilfe zeigt, was geht.")


def _naechster_posttag(ab: date | None = None):
    """Der nächste Tag, für den der Planer überhaupt etwas vorsieht."""
    tag = ab or date.today()
    for i in range(0, 21):
        kandidat = tag + timedelta(days=i)
        if planer.plane(kandidat) is not None:
            return kandidat
    return None


def _schicke_vorschlag_auf_wunsch(schlange: dict, anderes_thema: bool = False) -> None:
    """Auf /neu bzw. /anders sofort einen Vorschlag rendern und schicken.

    /neu    - nächster Posttag; liegt dort schon etwas offen, wird es gezeigt
    /anders - ausdrücklich ein anderes Thema für denselben Tag
    """
    import telegram_bot

    tag = _naechster_posttag()
    if tag is None:
        telegram_bot.sende_text(
            "In den nächsten drei Wochen ist kein Posttag vorgesehen. "
            "Posttage stehen in content/themen.json.")
        return

    tag_iso = tag.isoformat()
    eintrag = (schlange.get("wartend") or {}).get(tag_iso)
    ausschluss = set(eintrag["abgelehnt"]) if eintrag else set()

    if eintrag:
        # Liegt schon ein Vorschlag offen, will der Nutzer per /neu ausdrücklich
        # etwas ANDERES sehen - sonst käme derselbe Beitrag noch einmal und es
        # sähe aus, als sei nichts passiert.
        ausschluss.add(eintrag["plan_id"])
        telegram_bot.markiere(eintrag["nachricht_id"], "↩︎ ersetzt")

    plan = planer.plane(tag, ausschluss=ausschluss)
    if plan is None:
        telegram_bot.sende_text(
            f"Für {tag_iso} sind alle Themen dieser Rubrik durch. "
            "Neue Themen in content/themen.json ergänzen oder frische Fotos "
            "in content/medien/eingang/ legen.")
        return

    print(f"\nVorschlag auf Wunsch für {tag_iso}: {plan['id']}")
    bild = _erzeuge(plan)
    caption_datei = _schreibe_caption(plan, bild, mit_ki=False)
    caption = caption_datei.read_text(encoding="utf-8")
    vorschlag = telegram_bot.sende_vorschlag(
        bild, _telegram_kurztext(plan, caption), caption, plan["id"])

    schlange.setdefault("wartend", {})[tag_iso] = {
        "plan_id": plan["id"],
        "nachricht_id": vorschlag.nachricht_id,
        "abgelehnt": sorted(ausschluss),
    }


def cmd_vorrat(args) -> int:
    """Rendert mehrere Kandidaten auf Vorrat und legt sie öffentlich ab.

    Damit der Cloudflare Worker auf /neu in ein bis zwei Sekunden antworten
    kann, muss das Bild schon fertig sein. Rendern dauert im Actions-Lauf
    rund eine Minute - viel zu lang für einen Chat. Also einmal nachts alles
    vorbereiten, tagsüber nur noch ausliefern.

    Ergebnis: docs/vorrat/<id>.jpg samt docs/vorrat/index.json.
    """
    from config import MEDIA_BASE_URL

    ziel = Path(__file__).resolve().parent.parent / "docs" / "vorrat"
    ziel.mkdir(parents=True, exist_ok=True)

    tag = date.fromisoformat(args.datum) if args.datum else _naechster_posttag()
    if tag is None:
        print("\nKein Posttag in den nächsten drei Wochen.\n")
        return 0

    eintraege = []
    ausschluss: set[str] = set()
    for _ in range(args.anzahl):
        plan = planer.plane(tag, ausschluss=ausschluss)
        if plan is None:
            break
        ausschluss.add(plan["id"])

        bild = _erzeuge(plan)
        caption_datei = _schreibe_caption(plan, bild, mit_ki=False)
        caption = caption_datei.read_text(encoding="utf-8")

        name = f"{plan['id']}.jpg"
        shutil.copy2(bild, ziel / name)
        eintraege.append({
            "id": plan["id"],
            "tag": tag.isoformat(),
            "saeule": plan.get("saeule") or plan.get("rubrik", ""),
            "thema": plan.get("thema", ""),
            "bild": name,
            "bild_url": f"{MEDIA_BASE_URL.rsplit('/', 1)[0]}/vorrat/{name}" if MEDIA_BASE_URL else "",
            "kurztext": _telegram_kurztext(plan, caption),
            "caption": caption,
        })
        print(f"  {plan['id']:<22} {plan.get('saeule', '')}")

    index = {
        "erzeugt": _dt.datetime.now().isoformat(timespec="seconds"),
        "tag": tag.isoformat(),
        "eintraege": eintraege,
    }
    (ziel / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{len(eintraege)} Kandidat(en) auf Vorrat für {tag.isoformat()}.")
    print(f"Abgelegt in docs/vorrat/\n")
    return 0


def cmd_telegram_abfragen(args) -> int:
    """Wertet Tastendrücke aus Telegram aus.

    Instagram-Kanal: freigeben -> veröffentlichen, ablehnen -> neuen
    Kandidaten rendern und erneut schicken.
    Ads-Kanal: merken/mehr dazu/ignorieren, siehe _verarbeite_ads_callback().
    Ein Poll-Job für beide Kanäle - getUpdates liefert ohnehin alle
    Tastendrücke des Bots über beide Chats hinweg in einem Aufruf.
    """
    import telegram_bot

    if not (telegram_bot.aktiv() or telegram_bot.aktiv_ads()):
        print("\nTelegram ist nicht eingerichtet.\n", file=sys.stderr)
        return 1

    from config import TELEGRAM_BOT_TOKEN_SOCIAL, TELEGRAM_BOT_TOKEN_ADS

    schlange = _warteschlange_laden()
    antworten: list[dict] = []
    # Getrennt abgesichert: ein toter/ungueltiger Token in einem Kanal (z. B.
    # der Ads-Bot) darf den anderen, funktionierenden Kanal nicht blockieren.
    if telegram_bot.aktiv():
        try:
            social_antworten, neue_id = telegram_bot.hole_antworten(
                schlange.get("letzte_update_id_social", 0), bot_token=TELEGRAM_BOT_TOKEN_SOCIAL)
            schlange["letzte_update_id_social"] = neue_id
            antworten.extend(social_antworten)
        except telegram_bot.TelegramFehler as fehler:
            print(f"\nSocial-Bot: Antworten konnten nicht abgeholt werden – {fehler}\n", file=sys.stderr)
    if telegram_bot.aktiv_ads():
        try:
            ads_antworten, neue_id = telegram_bot.hole_antworten(
                schlange.get("letzte_update_id_ads", 0), bot_token=TELEGRAM_BOT_TOKEN_ADS)
            schlange["letzte_update_id_ads"] = neue_id
            antworten.extend(ads_antworten)
        except telegram_bot.TelegramFehler as fehler:
            print(f"\nAds-Bot: Antworten konnten nicht abgeholt werden – {fehler}\n", file=sys.stderr)
    freigegeben: list[dict] = []

    if not antworten:
        print("\nKeine neuen Antworten.\n")
        _warteschlange_speichern(schlange)
        return 0

    for antwort in antworten:
        aktion, _, rest = antwort["daten"].partition(":")

        if aktion == "befehl":
            _verarbeite_textbefehl(rest, schlange)
            continue

        if aktion in ("merken", "mehr", "ignorieren"):
            _verarbeite_ads_callback(aktion, rest, antwort)
            continue

        treffer = next((kv for kv in schlange["wartend"].items()
                        if kv[1]["nachricht_id"] == antwort["nachricht_id"]), None)

        if treffer is None:
            telegram_bot.beantworte_callback(
                antwort["callback_query_id"],
                "Dazu liegt kein offener Vorgang mehr vor.")
            continue

        tag_iso, eintrag = treffer
        tag = date.fromisoformat(tag_iso)

        if aktion == "ok":
            telegram_bot.beantworte_callback(antwort["callback_query_id"],
                                             "Freigegeben – wird veröffentlicht …")
            telegram_bot.markiere(eintrag["nachricht_id"],
                                  "✅ Freigegeben – wird veröffentlicht")
            freigaben.freigeben(eintrag["plan_id"])

            # Gleicher Tag, gleiche Ausschlussliste wie beim letzten Vorschlag –
            # plane() ist deterministisch, das liefert wieder denselben Kandidaten.
            plan = planer.plane(tag, ausschluss=set(eintrag["abgelehnt"]))
            if plan is None or plan["id"] != eintrag["plan_id"]:
                telegram_bot.sende_text(
                    f"FEHLER: Kandidat für {tag_iso} hat sich zwischenzeitlich "
                    "geändert – nichts veröffentlicht. Bitte 'heute --posten' "
                    "von Hand prüfen.")
                del schlange["wartend"][tag_iso]
                continue

            # Noch nicht wirklich veröffentlichen: Instagram lädt das Bild
            # selbst von einer öffentlichen URL - die entsteht erst, wenn der
            # Workflow es nach docs/posts kopiert und pusht. Bis dahin nur
            # rendern und für den zweiten Schritt (telegram-veroeffentlichen)
            # vormerken, exakt wie beim planmäßigen Cron-Lauf in
            # .github/workflows/vorschlagen.yml + taeglich-posten.yml.
            print(f"\nGerendert, wartet auf Veröffentlichung: {plan['id']} ({tag_iso})")
            bilder = (_erzeuge_alle(plan) if plan.get("typ") == "carousel" else [_erzeuge(plan)])
            _schreibe_caption(plan, bilder[0], mit_ki=False)
            dateinamen = [b.name for b in bilder]
            if plan.get("typ") == "reel":
                # Läuft über dieselbe "bilder"-Liste wie die Bilder – der
                # Workflow kopiert/prüft jede Datei darin gleich, ob Bild
                # oder Video.
                dateinamen.append(_kopiere_video(plan).name)
            freigegeben.append({
                "tag": tag_iso,
                "plan_id": plan["id"],
                "abgelehnt": eintrag["abgelehnt"],
                "bilder": dateinamen,
                "hauptbild": bilder[0].name,
            })
            del schlange["wartend"][tag_iso]

        elif aktion == "nein":
            telegram_bot.beantworte_callback(antwort["callback_query_id"],
                                             "Abgelehnt – neuer Vorschlag folgt …")
            telegram_bot.markiere(eintrag["nachricht_id"], "❌ Abgelehnt")
            eintrag["abgelehnt"].append(eintrag["plan_id"])

            neuer_plan = planer.plane(tag, ausschluss=set(eintrag["abgelehnt"]))
            if neuer_plan is None:
                telegram_bot.sende_text(
                    f"Keine weitere Alternative für {tag_iso} verfügbar – alle "
                    "Kandidaten dieser Rubrik wurden abgelehnt. Bitte "
                    "content/themen.json ergänzen oder neue Fotos in "
                    "content/medien/eingang/ legen.")
                del schlange["wartend"][tag_iso]
                continue

            print(f"\nNeuer Kandidat für {tag_iso}: {neuer_plan['id']}")
            bild = _erzeuge(neuer_plan)
            caption_datei = _schreibe_caption(neuer_plan, bild, mit_ki=False)
            caption = caption_datei.read_text(encoding="utf-8")
            vorschlag = telegram_bot.sende_vorschlag(
                bild, _telegram_kurztext(neuer_plan, caption), caption, neuer_plan["id"])
            schlange["wartend"][tag_iso] = {
                "plan_id": neuer_plan["id"],
                "nachricht_id": vorschlag.nachricht_id,
                "abgelehnt": eintrag["abgelehnt"],
            }

    _warteschlange_speichern(schlange)
    (OUT_DIR / "_freigegeben.json").write_text(
        json.dumps(freigegeben, ensure_ascii=False, indent=2), encoding="utf-8")
    if freigegeben:
        print(f"\n{len(freigegeben)} Beitrag/Beiträge gerendert und bereit für "
              f"'telegram-veroeffentlichen' (nach dem Veröffentlichen der Bilder).\n")
    else:
        print()
    return 0


def cmd_telegram_veroeffentlichen(args) -> int:
    """Zweiter Schritt nach einer Telegram-Freigabe: veröffentlicht, was
    'telegram-abfragen' gerendert hat - erst NACHDEM der Workflow die Bilder
    nach docs/posts kopiert, gepusht und ihre Erreichbarkeit geprüft hat.
    Ohne diesen zweiten Schritt lehnt Instagram die Bild-URL als nicht
    erreichbar ab, weil sie zum Render-Zeitpunkt noch nicht online ist.
    """
    datei = OUT_DIR / "_freigegeben.json"
    if not datei.exists():
        print("\nNichts zu veröffentlichen.\n")
        return 0

    eintraege = json.loads(datei.read_text(encoding="utf-8"))
    if not eintraege:
        print("\nNichts zu veröffentlichen.\n")
        return 0

    fehler_anzahl = 0
    for e in eintraege:
        tag = date.fromisoformat(e["tag"])
        plan = planer.plane(tag, ausschluss=set(e["abgelehnt"]))
        if plan is None or plan["id"] != e["plan_id"]:
            print(f"FEHLER: Kandidat für {e['tag']} hat sich geändert – übersprungen.",
                  file=sys.stderr)
            fehler_anzahl += 1
            continue

        bild = OUT_DIR / e["hauptbild"]
        caption_datei = bild.with_suffix(".txt")
        print(f"\nVeröffentliche {plan['id']} für {e['tag']} …")
        fehler_anzahl += _veroeffentliche(plan, tag, bild, caption_datei)

    datei.write_text("[]", encoding="utf-8")
    return 1 if fehler_anzahl else 0


def cmd_ads_news(args) -> int:
    """Täglicher Google-Ads-News-Check: Quellen prüfen, filtern, an den
    Ads-Kanal schicken. Siehe ads_news.py für den Ablauf."""
    import ads_news

    try:
        ergebnis = ads_news.pruefe_und_melde()
    except ads_news.NewsFehler as fehler:
        print(f"\nFEHLER: {fehler}\n", file=sys.stderr)
        return 1

    print(f"\nQuellen geprüft: {', '.join(ergebnis['geprueft_quellen'])}")
    if ergebnis["verschickt"]:
        print(f"Verschickt ({len(ergebnis['verschickt'])}):")
        for titel in ergebnis["verschickt"]:
            print(f"  - {titel}")
    else:
        print("Nichts Relevantes gefunden.")
    print()
    return 0


def _ads_kanal_bereit() -> bool:
    """Gemeinsame Voraussetzungsprüfung für Kurzcheck und Empfehlung: beide
    brauchen sowohl den Ads-Kanal als auch den Google-Ads-Zugang."""
    import google_ads_client
    import telegram_bot

    if not telegram_bot.aktiv_ads():
        print("\nAds-Kanal ist nicht eingerichtet (TELEGRAM_CHAT_ID_ADS "
              "fehlt).\n", file=sys.stderr)
        return False
    if not google_ads_client.aktiv():
        print("\nGoogle-Ads-Zugang fehlt (GOOGLE_ADS_* in .env bzw. "
              "GitHub Secrets). Anleitung: docs/05-ADS-KANAL-EINRICHTEN.md\n",
              file=sys.stderr)
        return False
    return True


def cmd_ads_kurzcheck(args) -> int:
    """Dienstags-Kurzcheck: Kampagnentabelle der letzten 7 Tage an den
    Ads-Kanal schicken."""
    import ads_stats
    import telegram_bot
    from config import TELEGRAM_CHAT_ID_ADS

    if not _ads_kanal_bereit():
        return 1

    try:
        bericht = ads_stats.baue_bericht()
    except Exception as fehler:  # noqa: BLE001
        print(f"\nFEHLER beim Abruf der Google-Ads-Daten: {fehler}\n", file=sys.stderr)
        return 1

    print(f"\n{bericht}\n")
    telegram_bot.sende_text(bericht, chat_id=TELEGRAM_CHAT_ID_ADS, markdown=True)
    return 0


def cmd_ads_empfehlung(args) -> int:
    """Donnerstags-Optimierungsvorschlag: ein konkreter, zahlenbasierter
    Punkt an den Ads-Kanal."""
    import ads_empfehlung
    import telegram_bot
    from config import TELEGRAM_CHAT_ID_ADS

    if not _ads_kanal_bereit():
        return 1

    try:
        vorschlag = ads_empfehlung.baue_vorschlag()
    except Exception as fehler:  # noqa: BLE001
        print(f"\nFEHLER beim Abruf der Google-Ads-Daten: {fehler}\n", file=sys.stderr)
        return 1

    print(f"\n{vorschlag}\n")
    telegram_bot.sende_text(vorschlag, chat_id=TELEGRAM_CHAT_ID_ADS)
    return 0


def cmd_ki_thema(args) -> int:
    """Lässt die KI ein Thema schreiben, prüft es mechanisch, zeigt das Bild."""
    import ki_schreiber
    import pruefung
    from config import ANTHROPIC_API_KEY, OPENAI_API_KEY

    try:
        thema = ki_schreiber.schreibe_thema(
            args.saeule, args.gewerk, args.stichwort,
            anbieter=args.anbieter,
            openai_key=OPENAI_API_KEY, anthropic_key=ANTHROPIC_API_KEY)
    except ki_schreiber.SchreibFehler as fehler:
        print(f"\nFEHLER: {fehler}\n", file=sys.stderr)
        return 1

    anbieter = thema.pop("_ki_anbieter", "?")
    print(f"\nGeschrieben von: {anbieter}")
    print(f"ID   : {thema['id']}")
    print(f"Hook : {thema['caption'].splitlines()[0]}\n")

    befunde = pruefung.pruefe_thema(thema)
    if befunde:
        print(f"SELBSTPRÜFUNG: {len(befunde)} Punkt(e) – NICHT automatisch übernommen:")
        for b in befunde:
            print(f"  - {b}")
        print("\nManuell nachbessern oder erneut generieren. Nichts wurde "
              "in content/themen.json geschrieben.\n")
    else:
        print("Selbstprüfung: keine Beanstandungen.")

    ziel = OUT_DIR / f"ki-entwurf_{thema['id']}.json"
    ziel.write_text(json.dumps(thema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Entwurf gespeichert: {ziel}")

    bild = rendere(thema["vorlage"], dict(thema["felder"], gewerk=thema.get("gewerk", "")),
                   f"ki-entwurf_{thema['id']}.jpg")
    print(f"Bild             : {bild}")

    if not befunde:
        print(f"\nÜbernehmen mit: python src/main.py einpflegen {ziel}\n")
    return 1 if befunde else 0


def cmd_einpflegen(args) -> int:
    import einpflegen
    dateien = [Path(p) for p in args.dateien]
    ergebnis = einpflegen.einpflegen(dateien, trockenlauf=args.trocken)

    print(f"\nNeu aufgenommen: {len(ergebnis['neu'])}")
    for i in ergebnis["neu"]:
        print(f"  + {i}")
    if ergebnis["doppelt"]:
        print(f"\nÜbersprungen, ID existiert bereits: {len(ergebnis['doppelt'])}")
        for i in ergebnis["doppelt"]:
            print(f"  = {i}")
    if ergebnis["abgelehnt"]:
        print(f"\nAbgelehnt: {len(ergebnis['abgelehnt'])}")
        for kennung, probleme in ergebnis["abgelehnt"]:
            print(f"  - {kennung}: {'; '.join(probleme)}")

    if args.trocken:
        print("\nTrockenlauf – nichts geschrieben.\n")
        return 0

    print("\nJetzt prüfen mit: python src/main.py pruefen\n")
    return 0


def cmd_auswerten(args) -> int:
    import analyse
    import publisher
    try:
        print("\n" + analyse.bericht(args.tage) + "\n")
    except publisher.VeroeffentlichungsFehler as fehler:
        print(f"\nFEHLER: {fehler}\n", file=sys.stderr)
        return 1

    if args.vergleich:
        print(f"Vergleich mit @{args.vergleich.lstrip('@')}:")
        v = analyse.vergleiche_konto(args.vergleich.lstrip("@"))
        if not v["verfuegbar"]:
            print("  Nicht verfügbar über den aktuellen Zugangsweg.")
            print("  Fremde Konten lassen sich nur über 'Instagram API mit")
            print("  Facebook-Login' abfragen – dafür wäre eine verknüpfte")
            print("  Facebook-Seite nötig. Grund laut Meta:")
            print(f"  {v['grund']}\n")
            return 0
        print(f"  {v['follower']} Follower · {v['beitraege']} Beiträge · "
              f"Median {v['median_interaktionen']} Interaktionen")
        for a in v["ausreisser"]:
            print(f"    {a['interaktionen']:>5}  {a['hook']}")
        print()
    return 0


def cmd_monatsplan(args) -> int:
    import monatsplan
    heute = date.today()
    jahr = args.jahr or heute.year
    monat = args.monat or heute.month

    md, ht = monatsplan.schreibe(jahr, monat)
    eintraege = monatsplan.sammle(jahr, monat)

    print(f"\nRedaktionsplan {monatsplan.MONATE[monat - 1]} {jahr} "
          f"· {len(eintraege)} Beiträge\n")
    for e in eintraege:
        marke = " *" if e["saeule_ist"] != e["saeule_geplant"] else "  "
        print(f"  {e['datum'].strftime('%d.%m.')} {e['wochentag'][:2]}{marke} "
              f"{e['saeule_ist']:<15} {e['hook'][:58]}")

    print(f"\n  * = Ersatz, weil für die geplante Säule kein Foto vorliegt\n")
    print(f"  Markdown: {md}")
    print(f"  HTML    : {ht}\n")
    return 0


def cmd_fotobedarf(args) -> int:
    """Sagt konkret, welche Fotos welchen Tag retten würden."""
    import monatsplan
    heute = date.today()
    eintraege = monatsplan.sammle(args.jahr or heute.year, args.monat or heute.month)
    ersatz = [e for e in eintraege if e["saeule_ist"] != e["saeule_geplant"]]

    if not ersatz:
        print("\nKein Fotobedarf – alle geplanten Säulen haben Material.\n")
        return 0

    anleitung = {
        "vorher-nachher": ("Je Projekt zwei Bilder aus demselben Blickwinkel: "
                           "vorher.jpg und nachher.jpg"),
        "detail": ("Nahaufnahmen: Fugenbild, Gehrungsschnitt, Gefälle zur Rinne, "
                   "Abdichtungsecke, Übergänge. Scharf, gut ausgeleuchtet."),
        "mensch": ("Arbeitssituationen: Werkzeug im Einsatz, Staubschutzwand, "
                   "Aufmaß. Keine gestellte Gruppe vor dem Firmenwagen."),
    }

    fehlt_bild: dict[str, list] = {}
    fehlt_thema: dict[str, list] = {}
    for e in ersatz:
        ziel = fehlt_bild if e["saeule_geplant"] in anleitung else fehlt_thema
        ziel.setdefault(e["saeule_geplant"], []).append(e["datum"])

    def zeige(titel: str, gruppen: dict, mit_anleitung: bool) -> None:
        if not gruppen:
            return
        print(titel)
        for saeule, tage in sorted(gruppen.items(), key=lambda x: -len(x[1])):
            print(f"  {saeule}  –  {len(tage)} Tag(e)")
            if mit_anleitung:
                print(f"    {anleitung[saeule]}")
            print("    Betroffen: " + ", ".join(t.strftime("%d.%m.") for t in tage[:8])
                  + (" …" if len(tage) > 8 else ""))
            print()

    print(f"\n{len(ersatz)} von {len(eintraege)} Tagen laufen als Ersatz.\n")
    zeige("FOTOS FEHLEN – diese Aufnahmen würden die Tage füllen:", fehlt_bild, True)
    zeige("THEMEN FEHLEN – hier reicht das Material der Säule nicht:",
          fehlt_thema, False)

    if fehlt_bild:
        print("  Ablage: content/medien/projekte/<name>/  bzw.  content/medien/pool/")
        print("  Anleitung: content/medien/LIESMICH.md")
    if fehlt_thema:
        print("  Neue Themen: content/themen.json ergänzen "
              "(Agent: berisabau-redaktion)")
    print()
    return 0


def cmd_seo(args) -> int:
    import pruefung
    a = pruefung.seo_audit()
    print(f"\n{a['mit_keyword']} von {a['gesamt']} Themen ({a['anteil']} %) "
          "tragen einen lokalen/fachlichen Suchbegriff im Fließtext.")
    if a["ohne_keyword"]:
        print(f"\nOhne Keyword im Text (Hashtags zählen hier nicht mit):")
        for tid in a["ohne_keyword"]:
            print(f"  {tid}")
        print("\nKein Fehler – Hashtags decken die lokale Auffindbarkeit "
              "meistens mit ab. Aber ein Begriff im Fließtext hilft "
              "zusätzlich bei öffentlich indexierten Facebook-Beiträgen "
              "und der Instagram-Suche.")
    print()
    return 0


def cmd_pruefen(args) -> int:
    import pruefung
    geprueft, befunde = pruefung.alles()
    print(f"\n{geprueft} freigegebene Themen geprüft.\n")
    if not befunde:
        print("Keine Beanstandungen.\n")
        return 0
    for b in befunde:
        print(f"  {b}")
    print(f"\n{len(befunde)} Punkt(e) zu klären.\n")
    return 1


def cmd_raster(args) -> int:
    """Zeigt die nächsten Posts als Profil-Raster.

    Niemand folgt einem einzelnen Beitrag – gefolgt wird dem Profil. Die
    ersten drei Reihen entscheiden. Diese Vorschau macht sichtbar, ob die
    Kacheln nebeneinander funktionieren oder sich totschlagen.
    """
    from config import OUT_DIR as _out

    plaene = planer.naechste_termine(args.anzahl)
    kacheln = []
    for p in plaene:
        bild = _erzeuge(p)
        kopf = "".join(str(p["felder"].get(k, ""))
                       for k in ("titel_vor", "titel_stark", "titel_nach")) \
            or p["felder"].get("frage", "") or p["felder"].get("zitat", "")
        # relativer Pfad: raster.html liegt im selben Ordner wie die Bilder
        kacheln.append({"datei": bild.name, "rubrik": p["rubrik"],
                        "datum": p["datum"], "titel": kopf.strip()})
        print(f"  {p['datum']}  {p['rubrik']:<15} {bild.name}")

    # Instagram zeigt im Raster quadratische Ausschnitte der 4:5-Bilder.
    zellen = "\n".join(
        f'<figure><img src="{k["datei"]}" alt=""><figcaption>'
        f'<b>{k["rubrik"]}</b><span>{k["datum"]}</span></figcaption></figure>'
        for k in kacheln
    )
    html = f"""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<title>Rasteransicht @berisabau</title><style>
body{{background:#000;color:#fff;font-family:system-ui,sans-serif;margin:0;padding:32px}}
h1{{font-size:20px;font-weight:600;margin:0 0 6px}}
p.hint{{color:#8a8a8a;font-size:14px;margin:0 0 28px;max-width:60ch}}
.raster{{display:grid;grid-template-columns:repeat(3,1fr);gap:3px;max-width:840px}}
figure{{margin:0;position:relative;aspect-ratio:1;overflow:hidden;background:#111}}
figure img{{width:100%;height:100%;object-fit:cover;display:block}}
figcaption{{position:absolute;left:0;right:0;bottom:0;padding:6px 8px;
  background:linear-gradient(0deg,rgba(0,0,0,.85),transparent);
  font-size:11px;display:flex;justify-content:space-between;opacity:0;transition:.15s}}
figure:hover figcaption{{opacity:1}}
figcaption span{{color:#9a9a9a}}
</style></head><body>
<h1>Rasteransicht @berisabau &middot; nächste {len(kacheln)} Beiträge</h1>
<p class="hint">So sieht das Profil aus, wenn jemand draufklickt. Instagram
schneidet die 4:5-Bilder im Raster quadratisch zu – genau das ist hier
simuliert. Prüfen: Wirken die Kacheln nebeneinander ruhig? Wiederholt sich
ein Motiv zu früh? Ist die erste Reihe stark genug?</p>
<div class="raster">
{zellen}
</div></body></html>"""

    ziel = _out / "raster.html"
    ziel.write_text(html, encoding="utf-8")
    print(f"\nRasteransicht: {ziel}\n")
    return 0


def cmd_carousel(args) -> int:
    """Carousel rendern und optional veröffentlichen."""
    import json as _json

    from config import CONTENT_DIR
    from renderer import rendere_carousel

    daten = _json.loads((CONTENT_DIR / "carousels.json").read_text(encoding="utf-8"))
    alle = {c["id"]: c for c in daten["carousels"]}

    if not args.id:
        print("\nVerfügbare Carousels:\n")
        for cid, c in alle.items():
            print(f"  {cid:<22} {len(c['slides'])} Slides · {c.get('gewerk', '')}")
        print()
        return 0

    if args.id not in alle:
        print(f"Unbekannt: {args.id}. Ohne Argument aufrufen zeigt die Liste.",
              file=sys.stderr)
        return 1

    carousel = alle[args.id]
    tag = date.fromisoformat(args.datum) if args.datum else date.today()
    praefix = f"{tag.isoformat()}_carousel_{kuerze_dateiname(args.id)}"

    pfade = rendere_carousel(carousel, praefix)
    print(f"\n{len(pfade)} Slides gerendert:")
    for p in pfade:
        print(f"  {p.name}")

    plan = {"datum": tag.isoformat(), "rubrik": "carousel", "id": carousel["id"],
            "gewerk": carousel.get("gewerk", ""),
            "hashtags": carousel.get("hashtags", "allgemein"),
            "caption": carousel["caption"], "felder": {}}
    caption = texter.baue_caption(plan)
    caption_datei = OUT_DIR / f"{praefix}.txt"
    caption_datei.write_text(caption, encoding="utf-8")
    print(f"Text  : {caption_datei.name}")

    if not args.posten:
        print("\nNicht veröffentlicht (kein --posten).\n")
        return 0

    import publisher
    alt_texte = [texter.baue_alt_text({"felder": s, "rubrik": "carousel"})
                 for s in carousel["slides"]]
    try:
        ergebnis = publisher.veroeffentliche_carousel(
            [p.name for p in pfade], caption, alt_texte, trockenlauf=args.trocken)
    except publisher.VeroeffentlichungsFehler as fehler:
        print(f"\nFEHLER: {fehler}\n", file=sys.stderr)
        publisher.protokolliere(carousel["id"], praefix, None, str(fehler))
        return 1

    print(f"Instagram: {ergebnis.meldung}")
    if ergebnis.permalink:
        print(f"Link     : {ergebnis.permalink}")
    if not args.trocken:
        planer.vermerke(carousel["id"], tag, praefix, ergebnis.id)
        publisher.protokolliere(carousel["id"], praefix, ergebnis)
    return 0


def cmd_freigeben(args) -> int:
    for thema_id in args.ids:
        freigaben.freigeben(thema_id)
        print(f"freigegeben: {thema_id}")
    return 0


def cmd_protokoll(args) -> int:
    from config import LOG_DATEI
    if not LOG_DATEI.exists():
        print("Noch kein Protokoll vorhanden.")
        return 0
    zeilen = LOG_DATEI.read_text(encoding="utf-8").strip().splitlines()
    for zeile in zeilen[-args.anzahl:]:
        e = json.loads(zeile)
        zeichen = "OK  " if e["erfolg"] else "FEHL"
        print(f"{zeichen} {e['zeitpunkt']}  {e['thema']}")
        if e.get("permalink"):
            print(f"      {e['permalink']}")
        if e.get("fehler"):
            print(f"      {e['fehler']}")
    return 0


def cmd_muster(args) -> int:
    """Rendert von jeder Rubrik ein Beispiel – zum Prüfen des Designs."""
    from config import THEMEN
    gesehen = set()
    ziel_ordner = OUT_DIR / "muster"
    for thema in THEMEN["themen"]:
        if thema["rubrik"] in gesehen:
            continue
        gesehen.add(thema["rubrik"])
        felder = dict(thema["felder"], gewerk=thema.get("gewerk", ""))
        pfad = rendere(thema["vorlage"], felder,
                       ziel_ordner / f"{thema['rubrik']}.png", format="feed")
        print(f"  {thema['rubrik']:<16} -> {pfad}")

    # zusätzlich eine Story
    story = {
        "gewerk": "Badsanierung", "eyebrow": "Kostenlose Besichtigung",
        "titel_vor": "Ihr Bad. ", "titel_stark": "Aus einer Hand", "titel_nach": ".",
        "lead": "Abbruch, Abdichtung, Fliesen, Sanitär und Elektro – ein Ansprechpartner.",
        "punkte": ["Angebot in 24 Stunden", "Termintreu und dokumentiert",
                   "Gewährleistung nach BGB/VOB"],
        "wisch": "Link in Bio",
    }
    pfad = rendere("story.html", story, ziel_ordner / "story.png", format="story")
    print(f"  {'story':<16} -> {pfad}")
    return 0


def cmd_fb_seiten(args) -> int:
    """Listet die Facebook-Seiten samt Seiten-Token auf.

    Hilfsschritt bei der Einrichtung – der Nutzer-Token aus dem Graph-Explorer
    ist kurzlebig, der daraus abgeleitete Seiten-Token nicht.
    """
    import facebook
    try:
        seiten = facebook.seiten_auflisten(args.token)
    except facebook.FacebookFehler as fehler:
        print(f"FEHLER: {fehler}", file=sys.stderr)
        return 1

    if not seiten:
        print("\nKeine Seiten gefunden. Ist der Token für das richtige Konto, "
              "und war 'pages_show_list' angehakt?\n", file=sys.stderr)
        return 1

    print("\nSeiten an diesem Zugang:\n")
    for s in seiten:
        print(f"  {s.get('name')}")
        print(f"    FB_PAGE_ID    = {s.get('id')}")
        print(f"    FB_PAGE_TOKEN = {s.get('access_token')}")
        print()
    print("Beides in die .env übernehmen. Anleitung: "
          "docs/03-FACEBOOK-EINRICHTEN.md\n")
    return 0


def cmd_zugang(args) -> int:
    """Beide Kanäle unabhängig prüfen.

    Ein fehlender Instagram-Zugang darf die Facebook-Prüfung nicht verdecken –
    sonst sucht man an der falschen Stelle.
    """
    import facebook
    import publisher

    instagram_ok = False
    try:
        ergebnis = publisher.pruefe_zugang()
        instagram_ok = ergebnis.ok
        print("Instagram: " + ("OK  " if ergebnis.ok else "FEHLER  ") + ergebnis.meldung)
        if ergebnis.ok:
            print("           Kontingent " + publisher.verbleibendes_kontingent())
    except publisher.VeroeffentlichungsFehler as fehler:
        print(f"Instagram: FEHLER  {fehler}")

    if not facebook.aktiv():
        print("Facebook : nicht eingerichtet – FB_PAGE_ID und FB_PAGE_TOKEN fehlen")
        print("           Anleitung: docs/03-FACEBOOK-EINRICHTEN.md")
    else:
        try:
            fb = facebook.pruefe_zugang()
            print("Facebook : " + ("OK  " if fb.ok else "FEHLER  ") + fb.meldung)
        except facebook.FacebookFehler as fehler:
            print(f"Facebook : FEHLER  {fehler}")

    import telegram_bot
    if not telegram_bot.aktiv():
        print("Telegram : nicht eingerichtet – Automatik postet ohne Freigabeschleife")
        print("           Anleitung: docs/04-TELEGRAM-EINRICHTEN.md")
    else:
        try:
            bot = telegram_bot.pruefe_zugang()
            print(f"Telegram : OK  {bot}")
        except telegram_bot.TelegramFehler as fehler:
            print(f"Telegram : FEHLER  {fehler}")

    if not telegram_bot.aktiv_ads():
        print("Ads-Kanal: nicht eingerichtet – TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID_ADS fehlt")
        print("           Anleitung: docs/05-ADS-KANAL-EINRICHTEN.md")
    else:
        try:
            ads_bot = telegram_bot.pruefe_zugang(ads=True)
            print(f"Ads-Kanal: OK  {ads_bot} (eigener Bot, seit 28.08.2026 getrennt vom Social-Bot)")
        except telegram_bot.TelegramFehler as fehler:
            print(f"Ads-Kanal: FEHLER  {fehler}")

    try:
        import google_ads_client
    except ImportError:
        pass
    else:
        if not google_ads_client.aktiv():
            print("Google Ads: nicht eingerichtet – GOOGLE_ADS_* fehlen")
            print("           Anleitung: docs/05-ADS-KANAL-EINRICHTEN.md")
        else:
            try:
                zeilen = google_ads_client.wochenvergleich()
                print(f"Google Ads: OK  {len(zeilen)} Kampagne(n) mit Daten in den letzten 7 Tagen")
            except Exception as fehler:  # noqa: BLE001 - Zugangsprüfung, jeder Fehler zählt
                print(f"Google Ads: FEHLER  {fehler}")

    return 0 if instagram_ok else 1


def cmd_plan_json(args) -> int:
    print(json.dumps(planer.vorschau(args.tage), ensure_ascii=False, indent=2))
    return 0


# --------------------------------------------------------------------------- #
def main() -> int:
    p = argparse.ArgumentParser(description="Berisa Bau – Instagram-Automatik")
    unter = p.add_subparsers(dest="befehl", required=True)

    v = unter.add_parser("vorschau", help="kommende Tage planen")
    v.add_argument("--tage", type=int, default=7)
    v.add_argument("--rendern", action="store_true", help="Bilder direkt erzeugen")
    v.set_defaults(func=cmd_vorschau)

    h = unter.add_parser("heute", help="Post für heute erzeugen")
    h.add_argument("--datum", help="abweichendes Datum, z. B. 2026-08-20")
    h.add_argument("--posten", action="store_true", help="wirklich veröffentlichen")
    h.add_argument("--trocken", action="store_true", help="Veröffentlichung nur simulieren")
    h.add_argument("--ki", action="store_true", help="Text von Claude glätten lassen (kostenpflichtig)")
    h.add_argument("--kein-facebook", action="store_true",
                   help="nur Instagram, Facebook auslassen")
    h.set_defaults(func=cmd_heute)

    m = unter.add_parser("muster", help="alle Vorlagen einmal rendern")
    m.set_defaults(func=cmd_muster)

    fbs = unter.add_parser("fb-seiten",
                           help="Facebook-Seiten und Seiten-Token auflisten")
    fbs.add_argument("--token", required=True, help="Nutzer-Token aus dem Graph-Explorer")
    fbs.set_defaults(func=cmd_fb_seiten)

    z = unter.add_parser("zugang", help="Verbindung zu Instagram und Facebook prüfen")
    z.set_defaults(func=cmd_zugang)

    j = unter.add_parser("plan-json", help="Plan als JSON ausgeben")
    j.add_argument("--tage", type=int, default=30)
    j.set_defaults(func=cmd_plan_json)

    ex = unter.add_parser("export", help="Monat als Ordner mit Tabelle, Bildern und Texten")
    ex.add_argument("--jahr", type=int)
    ex.add_argument("--monat", type=int)
    ex.add_argument("--ohne-bilder", action="store_true",
                    help="nur Tabelle und Texte, spart Zeit beim Korrekturlesen")
    ex.set_defaults(func=cmd_export)

    kt = unter.add_parser("ki-thema", help="ein neues Thema von der KI schreiben lassen")
    kt.add_argument("--saeule", required=True, choices=["wissen", "fehler", "detail", "mensch"])
    kt.add_argument("--gewerk", required=True)
    kt.add_argument("--stichwort", help="konkretes Thema; ohne wählt die KI selbst")
    kt.add_argument("--anbieter", choices=["openai", "anthropic"],
                    help="Standard: OpenAI zuerst, dann Anthropic")
    kt.set_defaults(func=cmd_ki_thema)

    fv = unter.add_parser("fotos-verarbeiten",
                          help="Eingang sichten: ausrichten, korrigieren, in den Pool legen")
    fv.set_defaults(func=cmd_fotos_verarbeiten)

    vs = unter.add_parser("vorschlagen",
                          help="nächsten Kandidaten rendern und zur Freigabe an Telegram schicken")
    vs.add_argument("--datum", help="abweichendes Datum, z. B. 2026-08-20")
    vs.set_defaults(func=cmd_vorschlagen)

    vr = unter.add_parser("vorrat",
                          help="Kandidaten auf Vorrat rendern (für den Worker)")
    vr.add_argument("--anzahl", type=int, default=5)
    vr.add_argument("--datum", default="")
    vr.set_defaults(func=cmd_vorrat)

    ta = unter.add_parser("telegram-abfragen",
                          help="Telegram-Antworten abholen: freigeben -> posten, ablehnen -> neu vorschlagen")
    ta.set_defaults(func=cmd_telegram_abfragen)

    an = unter.add_parser("ads-news",
                          help="Google-Ads-Quellen prüfen und Neuigkeiten an den Ads-Kanal schicken")
    an.set_defaults(func=cmd_ads_news)

    ak = unter.add_parser("ads-kurzcheck",
                          help="Dienstags-Kampagnentabelle an den Ads-Kanal schicken")
    ak.set_defaults(func=cmd_ads_kurzcheck)

    ae = unter.add_parser("ads-empfehlung",
                          help="Donnerstags-Optimierungsvorschlag an den Ads-Kanal schicken")
    ae.set_defaults(func=cmd_ads_empfehlung)

    tv = unter.add_parser("telegram-veroeffentlichen",
                          help="zweiter Schritt: das per Telegram Freigegebene tatsächlich posten "
                               "(erst nachdem die Bilder öffentlich erreichbar sind)")
    tv.set_defaults(func=cmd_telegram_veroeffentlichen)

    ep = unter.add_parser("einpflegen", help="geprüfte Themen aus JSON aufnehmen")
    ep.add_argument("dateien", nargs="+")
    ep.add_argument("--trocken", action="store_true")
    ep.set_defaults(func=cmd_einpflegen)

    aw = unter.add_parser("auswerten", help="eigene Beiträge auswerten (braucht Zugang)")
    aw.add_argument("--tage", type=int, default=30)
    aw.add_argument("--vergleich", help="fremdes Profikonto, z. B. @betrieb")
    aw.set_defaults(func=cmd_auswerten)

    mp = unter.add_parser("monatsplan", help="Redaktionsplan für einen Monat erzeugen")
    mp.add_argument("--jahr", type=int)
    mp.add_argument("--monat", type=int)
    mp.set_defaults(func=cmd_monatsplan)

    fb = unter.add_parser("fotobedarf", help="welche Fotos welchen Tag retten würden")
    fb.add_argument("--jahr", type=int)
    fb.add_argument("--monat", type=int)
    fb.set_defaults(func=cmd_fotobedarf)

    so = unter.add_parser("seo-check", help="Anteil lokaler Suchbegriffe im Fließtext (informativ)")
    so.set_defaults(func=cmd_seo)

    pf = unter.add_parser("pruefen", help="Selbstprüfung nach CONTENT-PROMPT.md")
    pf.set_defaults(func=cmd_pruefen)

    r = unter.add_parser("raster", help="Profil-Rasteransicht der nächsten Beiträge")
    r.add_argument("--anzahl", type=int, default=9, help="Anzahl Beiträge, nicht Kalendertage")
    r.set_defaults(func=cmd_raster)

    c = unter.add_parser("carousel", help="Carousel rendern (ohne ID: Liste zeigen)")
    c.add_argument("id", nargs="?", help="Carousel-ID aus content/carousels.json")
    c.add_argument("--datum")
    c.add_argument("--posten", action="store_true")
    c.add_argument("--trocken", action="store_true")
    c.set_defaults(func=cmd_carousel)

    fg = unter.add_parser("freigeben", help="Themen für die Automatik freigeben")
    fg.add_argument("ids", nargs="+", help="Themen-IDs, z. B. t-grossformat")
    fg.set_defaults(func=cmd_freigeben)

    pr = unter.add_parser("protokoll", help="letzte Post-Versuche anzeigen")
    pr.add_argument("--anzahl", type=int, default=15)
    pr.set_defaults(func=cmd_protokoll)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
