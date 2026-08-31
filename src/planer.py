"""Wählt aus, was gepostet wird – zweimal pro Woche, nicht täglich.

Regeln:
  1. content/themen.json -> "posttage" legt fest, an welchen Wochentagen
     überhaupt gepostet wird (0=Montag). An allen anderen Tagen liefert
     plane() None – der Aufrufer postet dann schlicht nichts.
  2. "rotation" ist eine Säulen-Reihenfolge, die über die tatsächlichen
     Post-Termine läuft (nicht über Kalendertage): jeder Post-Slot einer
     ISO-Kalenderwoche bekommt seinen Index in dieser Liste. So bekommt
     jede Säule über mehrere Wochen ihren Anteil, unabhängig davon, wie
     viele Tage zwischen zwei Posts liegen.
  3. Innerhalb der Rubrik gewinnt das Thema, das am längsten nicht dran war.
  4. Foto-Rubriken (vorher-nachher, detail, mensch) fallen automatisch auf
     eine Text-Rubrik zurück, wenn keine passenden Bilder im Medienordner
     liegen. Die Nachbarschafts-Prüfung dabei schaut auf den vorherigen und
     nächsten tatsächlichen Post-Termin, nicht auf den Kalendertag davor/danach.
Damit läuft das System auch dann weiter, wenn wochenlang keine neuen
Baustellenfotos nachgelegt werden.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import einwilligung
from config import MEDIEN_DIR, STATE_DATEI, THEMEN

PROJEKTE_DIR = MEDIEN_DIR / "projekte"
POOL_DIR = MEDIEN_DIR / "pool"

BILDENDUNGEN = {".jpg", ".jpeg", ".png", ".webp"}
VIDEOENDUNGEN = {".mp4", ".mov"}

# Ab so vielen Fotos in einem Projektordner wird daraus ein Carousel statt
# eines Einzelbilds. Instagram erlaubt bis zu 10 Slides.
AB_CAROUSEL = 2
MAX_SLIDES = 10

# Säulen, die zwingend eigenes Bildmaterial brauchen.
FOTO_SAEULEN = {"vorher-nachher", "detail", "mensch"}
# Säulen, die auch als reine Textkachel funktionieren.
TEXT_SAEULEN = ["wissen", "fehler", "detail", "mensch"]

# Bevorzugte Ersatzsäulen je ausgefallener Foto-Säule (Reihenfolge zählt).
RUECKFALL = THEMEN.get("rueckfall", {
    "vorher-nachher": ["detail", "wissen", "fehler"],
    "detail": ["wissen", "fehler", "mensch"],
    "mensch": ["fehler", "wissen", "detail"],
})


# --------------------------------------------------------------------------- #
# Verlauf
# --------------------------------------------------------------------------- #
def lade_verlauf() -> dict:
    if STATE_DATEI.exists():
        return json.loads(STATE_DATEI.read_text(encoding="utf-8"))
    return {"eintraege": []}


def speichere_verlauf(verlauf: dict) -> None:
    STATE_DATEI.write_text(
        json.dumps(verlauf, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def vermerke(thema_id: str, tag: date, pfad: str | None = None,
             ig_id: str | None = None) -> None:
    verlauf = lade_verlauf()
    verlauf["eintraege"].append({
        "id": thema_id,
        "datum": tag.isoformat(),
        "bild": pfad,
        "instagram_id": ig_id,
        "erstellt": datetime.now().isoformat(timespec="seconds"),
    })
    speichere_verlauf(verlauf)


def _zuletzt_verwendet() -> dict[str, str]:
    letzte: dict[str, str] = {}
    for e in lade_verlauf()["eintraege"]:
        letzte[e["id"]] = e["datum"]
    return letzte


# Ein Foto darf frühestens nach dieser Zeit erneut in den Feed.
SPERRFRIST_TAGE = 30


def _gesperrt(thema_id: str, tag: date, verlauf: dict[str, str]) -> bool:
    zuletzt = verlauf.get(thema_id)
    if not zuletzt:
        return False
    if zuletzt == "9999-99-99":          # in derselben Vorschau schon vergeben
        return True
    return (tag - date.fromisoformat(zuletzt)).days < SPERRFRIST_TAGE


# --------------------------------------------------------------------------- #
# Medien
# --------------------------------------------------------------------------- #
def _bilder(ordner: Path) -> list[Path]:
    """Bilder eines Ordners - nur die mit Einwilligung des Kunden.

    Diese Funktion ist die einzige Stelle, ueber die Fotos in einen Beitrag
    gelangen. Deshalb sitzt die Sperre hier: Was in
    content/medien/freigabe.json fehlt, kann gar nicht erst ausgewaehlt werden.
    """
    if not ordner.exists():
        return []
    gefunden = sorted(p for p in ordner.iterdir()
                      if p.is_file() and p.suffix.lower() in BILDENDUNGEN)
    return einwilligung.filtere(gefunden)


def projekte_mit_paar() -> list[Path]:
    """Projektordner, die sowohl ein Vorher- als auch ein Nachher-Bild haben."""
    treffer = []
    if not PROJEKTE_DIR.exists():
        return treffer
    for ordner in sorted(p for p in PROJEKTE_DIR.iterdir() if p.is_dir()):
        namen = {p.stem.lower() for p in _bilder(ordner)}
        if any(n.startswith("vorher") for n in namen) and any(n.startswith("nachher") for n in namen):
            treffer.append(ordner)
    return treffer


def projekte_mit_foto() -> list[Path]:
    if not PROJEKTE_DIR.exists():
        return []
    return [o for o in sorted(p for p in PROJEKTE_DIR.iterdir() if p.is_dir())
            if _bilder(o)]


def _projekt_bild(ordner: Path, praefix: str) -> Path | None:
    for p in _bilder(ordner):
        if p.stem.lower().startswith(praefix):
            return p
    return None


def _videos(ordner: Path) -> list[Path]:
    """Videos eines Ordners - dieselbe Sperre wie bei Bildern."""
    if not ordner.exists():
        return []
    gefunden = sorted(p for p in ordner.iterdir()
                      if p.is_file() and p.suffix.lower() in VIDEOENDUNGEN)
    return einwilligung.filtere(gefunden)


def projekte_mit_video() -> list[Path]:
    if not PROJEKTE_DIR.exists():
        return []
    return [o for o in sorted(p for p in PROJEKTE_DIR.iterdir() if p.is_dir())
            if _videos(o)]


def projekte_mit_serie() -> list[Path]:
    """Projektordner mit genug Fotos für ein Carousel."""
    if not PROJEKTE_DIR.exists():
        return []
    return [o for o in sorted(p for p in PROJEKTE_DIR.iterdir() if p.is_dir())
            if len(_bilder(o)) >= AB_CAROUSEL]


def _serie_sortiert(ordner: Path) -> list[Path]:
    """Fotos in sinnvoller Reihenfolge: Nachher zuerst, Vorher zuletzt.

    Das Nachher-Bild ist das stärkste Motiv und gehört auf die erste Slide –
    im Raster und in der Vorschau ist nur diese sichtbar.
    """
    bilder = _bilder(ordner)

    def rang(p: Path) -> tuple[int, str]:
        name = p.stem.lower()
        if name.startswith("nachher"):
            return (0, name)
        if name.startswith("vorher"):
            return (2, name)
        return (1, name)

    return sorted(bilder, key=rang)[:MAX_SLIDES]


def _projekt_info(ordner: Path) -> dict:
    datei = ordner / "info.json"
    if datei.exists():
        return json.loads(datei.read_text(encoding="utf-8"))
    return {}


# --------------------------------------------------------------------------- #
# Auswahl
# --------------------------------------------------------------------------- #
POSTTAGE = THEMEN.get("posttage", [1, 3])          # 0=Montag; Standard Di/Do
ROTATION = THEMEN.get("rotation", ["wissen", "vorher-nachher"])
# Eigene Rotation je Wochentag (z. B. Dienstag = Text, Donnerstag = Foto).
# JSON-Schlüssel sind Strings; hier auf int gewandelt, damit sie sich direkt
# mit date.weekday() vergleichen lassen. Wochentage ohne eigenen Eintrag
# laufen weiter über die alte flache ROTATION.
ROTATION_JE_TAG = {int(k): v for k, v in THEMEN.get("rotation_je_wochentag", {}).items()}


def rubrik_fuer(tag: date) -> str | None:
    """Säule für diesen Tag – oder None, wenn an diesem Tag nicht gepostet wird."""
    if tag.weekday() not in POSTTAGE:
        return None
    wochennr = tag.isocalendar()[1]
    rotation = ROTATION_JE_TAG.get(tag.weekday())
    if rotation:
        return rotation[wochennr % len(rotation)]
    slot_im_tag = POSTTAGE.index(tag.weekday())
    index = wochennr * len(POSTTAGE) + slot_im_tag
    return ROTATION[index % len(ROTATION)]


def ist_posttag(tag: date) -> bool:
    return tag.weekday() in POSTTAGE


def _benachbarter_posttag(tag: date, richtung: int) -> date:
    """Der vorherige (-1) oder nächste (+1) Tag, an dem gepostet wird."""
    schritt = date.fromordinal(tag.toordinal() + richtung)
    while schritt.weekday() not in POSTTAGE:
        schritt = date.fromordinal(schritt.toordinal() + richtung)
    return schritt


def _freigegeben(thema: dict) -> bool:
    """Themen mit "pruefen": true werden nie automatisch veröffentlicht.

    Gedacht für Kundenstimmen: eine Aussage darf erst raus, wenn sie
    tatsächlich so gefallen ist und der Kunde einverstanden ist.
    """
    return not thema.get("pruefen", False)


def _themen_der_rubrik(rubrik: str) -> list[dict]:
    return [t for t in THEMEN["themen"] if t["rubrik"] == rubrik and _freigegeben(t)]


def _ersatz_rubrik(ausgefallen: str, tag: date, verlauf: dict[str, str],
                   ausschluss: set[str] | None = None) -> str:
    """Welche Textsäule einspringt, wenn eine Foto-Säule kein Material hat.

    Ohne diese Rotation fielen alle drei Foto-Säulen auf 'wissen' zurück und
    die Woche bestünde aus sechs gleichartigen Beiträgen. Der Content-Prompt
    verlangt aber: nie zweimal dieselbe Säule hintereinander.
    """
    # Bei zwei Posts pro Woche liegt "gestern" fast nie auf einem Posttag –
    # relevant ist der vorherige und nächste TATSÄCHLICHE Post-Termin.
    gestern = _saeule_am(_benachbarter_posttag(tag, -1), verlauf)
    morgen = rubrik_fuer(_benachbarter_posttag(tag, +1))
    morgen = morgen if morgen not in FOTO_SAEULEN else None

    # Nur Säulen, die aktuell noch ein Thema außerhalb der Sperrfrist haben.
    kandidaten = [r for r in RUECKFALL.get(ausgefallen, TEXT_SAEULEN)
                  if _freie_themen(r, tag, verlauf, ausschluss)]
    if not kandidaten:
        kandidaten = [r for r in TEXT_SAEULEN if _freie_themen(r, tag, verlauf, ausschluss)]
    if not kandidaten:
        return "wissen"

    frei = [r for r in kandidaten if r not in (gestern, morgen)]
    auswahl = frei or [r for r in kandidaten if r != gestern] or kandidaten
    return auswahl[tag.toordinal() % len(auswahl)]


def _saeule_am(tag: date, verlauf: dict[str, str]) -> str | None:
    """Welche Säule an diesem Tag geplant war – aus dem mitgeführten Verlauf."""
    for thema_id, datum in verlauf.items():
        if datum == tag.isoformat():
            treffer = next((t for t in THEMEN["themen"] if t["id"] == thema_id), None)
            if treffer:
                return treffer["rubrik"]
            # Foto-Posts stehen nicht in der Themenbank
            if thema_id.startswith(("projekt-", "pool-")):
                return "detail"
    return None


def _aeltestes(themen: list[dict], verlauf: dict[str, str],
               tag: date | None = None) -> dict:
    """Nie verwendete zuerst, danach das am längsten zurückliegende."""
    return sorted(themen, key=lambda t: verlauf.get(t["id"], "0000-00-00"))[0]


def _freie_themen(rubrik: str, tag: date, verlauf: dict[str, str],
                  ausschluss: set[str] | None = None) -> list[dict]:
    """Themen der Rubrik, die nicht in der Sperrfrist stecken.

    Ohne diese Prüfung erschien ein Thema erneut, sobald es das älteste seiner
    Säule war – bei kleinen Säulen also alle zwei Wochen.
    """
    ausschluss = ausschluss or set()
    return [t for t in _themen_der_rubrik(rubrik)
            if not _gesperrt(t["id"], tag, verlauf) and t["id"] not in ausschluss]


def _erster_freier(kandidaten: list, id_von, tag: date, verlauf: dict[str, str],
                   ausschluss: set[str] | None = None):
    """Erster Kandidat, der nicht in der Sperrfrist steckt – sonst None.

    Ohne diese Prüfung würde bei nur einem Projektordner jede Woche dasselbe
    Foto erscheinen. Lieber ein Text-Post als ein wiederholtes Bild.

    ausschluss: IDs, die trotz freier Sperrfrist übersprungen werden – für die
    Telegram-Freigabeschleife, wenn ein Vorschlag bereits abgelehnt wurde.
    """
    if not kandidaten:
        return None
    ausschluss = ausschluss or set()
    start = _index(tag, len(kandidaten))
    for versatz in range(len(kandidaten)):
        kandidat = kandidaten[(start + versatz) % len(kandidaten)]
        kid = id_von(kandidat)
        if not _gesperrt(kid, tag, verlauf) and kid not in ausschluss:
            return kandidat
    return None


def _naechste_freie_nummer() -> int:
    """Die Nummer, die der nächste tatsächlich veröffentlichte Post trägt.

    Zählt die bereits echt geposteten Beiträge aus content/verlauf.json und
    zählt eins weiter. So zeigt jeder Beitrag im Profil eine fortlaufende
    Nummer (01, 02, 03, …) statt einer vom Thema unabhängig vergebenen –
    zwei verschiedene Themen dürfen sonst zufällig beide "01" tragen.
    """
    return len(lade_verlauf()["eintraege"]) + 1


def _mit_nummer(ergebnis: dict, post_nummer: int | None) -> dict:
    """Setzt die Wasserzahl im Bild auf die fortlaufende Post-Nummer.

    Überschreibt bewusst jeden Wert, den ein Thema selbst in felder.nummer
    eingetragen hat – die Reihenfolge im Feed entscheidet, nicht die
    Themenbank.
    """
    if post_nummer is not None:
        ergebnis.setdefault("felder", {})["nummer"] = f"{post_nummer:02d}"
    return ergebnis


def plane(tag: date | None = None, verlauf: dict[str, str] | None = None,
         post_nummer: int | None = None,
         ausschluss: set[str] | None = None) -> dict | None:
    """Liefert einen fertigen Post-Auftrag für den Tag – oder None.

    None heißt: an diesem Wochentag wird laut "posttage" nicht gepostet.
    Das ist der Normalfall bei zwei Terminen pro Woche, kein Fehler.

    post_nummer: fortlaufende Post-Nummer fürs Bild (01, 02, …). Ohne Angabe
    wird die nächste freie Nummer anhand von content/verlauf.json ermittelt -
    das reicht für einen einzelnen Tag. Wer mehrere Tage im Voraus plant
    (vorschau(), naechste_termine()), muss selbst hochzählen, sonst würden
    alle Vorschau-Posts dieselbe Nummer zeigen.

    ausschluss: Themen-/Projekt-IDs, die übersprungen werden, obwohl sie nicht
    in der Sperrfrist stecken. Für die Telegram-Freigabeschleife: derselbe Tag
    wird mit wachsender Ausschlussliste neu geplant, bis ein Kandidat gefällt.
    """
    tag = tag or date.today()
    verlauf = _zuletzt_verwendet() if verlauf is None else verlauf
    ausschluss = ausschluss or set()
    if post_nummer is None:
        post_nummer = _naechste_freie_nummer()
    rubrik = rubrik_fuer(tag)
    if rubrik is None:
        return None

    # --- Foto-Rubriken: nur wenn frisches Material da ist ------------------- #
    if rubrik == "vorher-nachher":
        wahl = _erster_freier(projekte_mit_paar(),
                              lambda o: f"projekt-{o.name}-vn", tag, verlauf, ausschluss)
        if wahl:
            return _mit_nummer(_aus_projekt(wahl, tag, paar=True), post_nummer)
        # Vorher/Nachher hat keine Textvariante – immer über den Ersatz.
        rubrik = _ersatz_rubrik(rubrik, tag, verlauf, ausschluss)

    elif rubrik in FOTO_SAEULEN:
        # Reihenfolge nach Wirkung: Video schlägt Serie schlägt Einzelbild.
        wahl = _erster_freier(projekte_mit_video(),
                              lambda o: f"projekt-{o.name}-reel", tag, verlauf, ausschluss)
        if wahl:
            return _mit_nummer(_aus_video(wahl, tag, saeule=rubrik), post_nummer)
        wahl = _erster_freier(projekte_mit_serie(),
                              lambda o: f"projekt-{o.name}-serie", tag, verlauf, ausschluss)
        if wahl:
            return _mit_nummer(_aus_serie(wahl, tag, saeule=rubrik), post_nummer)
        wahl = _erster_freier(projekte_mit_foto(),
                              lambda o: f"projekt-{o.name}-foto", tag, verlauf, ausschluss)
        if wahl:
            return _mit_nummer(_aus_projekt(wahl, tag, paar=False, saeule=rubrik), post_nummer)
        wahl = _erster_freier(_bilder(POOL_DIR),
                              lambda p: f"pool-{p.stem}", tag, verlauf, ausschluss)
        if wahl:
            return _mit_nummer(_aus_pool(wahl, tag, saeule=rubrik), post_nummer)
        # Kein Foto: erst dieselbe Säule als Textkachel, sonst rotierender Ersatz.
        if not _freie_themen(rubrik, tag, verlauf, ausschluss):
            rubrik = _ersatz_rubrik(rubrik, tag, verlauf, ausschluss)

    # Erst frische Themen der Säule, dann irgendein frisches Textthema, und
    # nur wenn alles in der Sperrfrist steckt das am längsten zurückliegende.
    themen = _freie_themen(rubrik, tag, verlauf, ausschluss)
    if not themen:
        themen = [t for t in THEMEN["themen"]
                  if t["rubrik"] in TEXT_SAEULEN and _freigegeben(t)
                  and not _gesperrt(t["id"], tag, verlauf) and t["id"] not in ausschluss]
    if not themen:
        themen = [t for t in _themen_der_rubrik(rubrik) if t["id"] not in ausschluss] or [
            t for t in THEMEN["themen"]
            if t["rubrik"] in TEXT_SAEULEN and _freigegeben(t) and t["id"] not in ausschluss]
    if not themen:
        # Ausschlussliste hat alles leergeräumt (sehr kleine Themenbank) –
        # lieber eine Wiederholung zulassen als gar keinen Vorschlag liefern.
        themen = _themen_der_rubrik(rubrik) or [
            t for t in THEMEN["themen"] if t["rubrik"] in TEXT_SAEULEN and _freigegeben(t)]

    thema = _aeltestes(themen, verlauf)
    return _mit_nummer({
        "id": thema["id"],
        "rubrik": thema["rubrik"],
        "vorlage": thema["vorlage"],
        "gewerk": thema.get("gewerk", ""),
        "felder": dict(thema["felder"], gewerk=thema.get("gewerk", "")),
        "caption": thema["caption"],
        "hashtags": thema.get("hashtags", "allgemein"),
        "datum": tag.isoformat(),
    }, post_nummer)


def _index(tag: date, n: int) -> int:
    """Stabile, über die Zeit rotierende Auswahl ohne Zufall."""
    return tag.toordinal() % n


BADGES = {"vorher-nachher": "Vorher/Nachher", "detail": "Detail",
          "mensch": "Baustelle", "wissen": "Wissen", "fehler": "Achtung"}

# Drei Grundfarben im festen Wechsel. Instagram zeigt drei Kacheln je Reihe –
# eine Periode von 3 sorgt dafür, dass jede Farbe immer in derselben Spalte
# landet. Genau daraus entsteht das ruhige Streifenmuster im Profil.
VARIANTEN = ["rot", "dunkel", "hell"]


def farbvariante(tag: date) -> str:
    return VARIANTEN[tag.toordinal() % len(VARIANTEN)]


def _aus_projekt(ordner: Path, tag: date, paar: bool, saeule: str = "detail") -> dict:
    info = _projekt_info(ordner)
    name = info.get("titel") or ordner.name.replace("-", " ").title()
    gewerk = info.get("gewerk", "Sanierung")

    basis = {
        "id": f"projekt-{ordner.name}-{'vn' if paar else 'foto'}",
        "gewerk": gewerk,
        "hashtags": info.get("hashtags", "sanierung"),
        "datum": tag.isoformat(),
        "caption": info.get("caption") or (
            f"{name} – fertiggestellt in {info.get('ort', 'Mülheim an der Ruhr')}.\n\n"
            "Alle Gewerke aus einer Hand: von der Demontage bis zur Feinmontage, "
            "ein Ansprechpartner und ein Zeitplan."
        ),
    }

    if paar:
        basis.update({
            "rubrik": "vorher-nachher",
            "vorlage": "vorher-nachher.html",
            "felder": {
                "gewerk": gewerk,
                "badge": info.get("badge", BADGES["vorher-nachher"]),
                "eyebrow": info.get("eyebrow", "Vorher / Nachher"),
                "titel_vor": info.get("titel_vor", ""),
                "titel_stark": info.get("titel_stark", name),
                "titel_nach": info.get("titel_nach", "."),
                "lead": info.get("lead", ""),
                "dauer": info.get("dauer"),
                "ort_projekt": info.get("ort"),
                "bild_vorher": str(_projekt_bild(ordner, "vorher")),
                "bild_nachher": str(_projekt_bild(ordner, "nachher")),
            },
        })
    else:
        bilder = _bilder(ordner)
        bevorzugt = _projekt_bild(ordner, "nachher") or bilder[0]
        basis.update({
            "rubrik": saeule,
            "vorlage": "projekt.html",
            "felder": {
                "gewerk": gewerk,
                "badge": info.get("badge", BADGES.get(saeule, "Baustelle")),
                "eyebrow": info.get("eyebrow", "Aus der Werkstatt"),
                "titel_vor": info.get("titel_vor", ""),
                "titel_stark": info.get("titel_stark", name),
                "titel_nach": info.get("titel_nach", "."),
                "lead": info.get("lead", ""),
                "details": info.get("details", []),
                "bild": str(bevorzugt),
            },
        })
    return basis


def _aus_serie(ordner: Path, tag: date, saeule: str = "detail") -> dict:
    """Mehrere Fotos eines Projekts als Carousel zum Durchwischen.

    Slide 1 bekommt die volle Beschriftung, die Folgeslides nur einen dezenten
    Rahmen – sonst erschlägt der Text die Bilder.
    """
    info = _projekt_info(ordner)
    name = info.get("titel") or ordner.name.replace("-", " ").title()
    gewerk = info.get("gewerk", "Sanierung")
    fotos = _serie_sortiert(ordner)

    slides = []
    for nr, foto in enumerate(fotos, start=1):
        if nr == 1:
            # Erste Slide im Rasterlayout – das ist die Kachel, die im Profil
            # sichtbar ist und über den Klick entscheidet.
            slides.append({
                "vorlage": "cover-raster.html", "gewerk": gewerk,
                "variante": info.get("variante") or farbvariante(tag),
                "oberlabel": info.get("badge", BADGES.get(saeule, "Baustelle")),
                "titel_vor": info.get("titel_vor", ""),
                "titel_stark": info.get("titel_stark", name),
                "titel_nach": info.get("titel_nach", ""),
                "titel_gross": info.get("titel_gross", True),
                "bild": str(foto),
                "bildlabel": info.get("bildlabel", ""),
            })
        else:
            slides.append({
                "vorlage": "foto-slide.html", "gewerk": gewerk,
                "seite": nr, "gesamt": len(fotos),
                "bild": str(foto),
                "bildunterschrift": (info.get("bildunterschriften") or {}).get(foto.stem, ""),
                "letzte": nr == len(fotos),
            })

    return {
        "id": f"projekt-{ordner.name}-serie",
        "rubrik": saeule,
        "typ": "carousel",
        "slides": slides,
        "gewerk": gewerk,
        "hashtags": info.get("hashtags", "sanierung"),
        "datum": tag.isoformat(),
        "felder": slides[0],
        "caption": info.get("caption") or (
            f"{name} – {len(fotos)} Bilder zum Durchwischen.\n\n"
            f"Fertiggestellt in {info.get('ort', 'Mülheim an der Ruhr')}. "
            "Alle Gewerke aus einer Hand: von der Demontage bis zur Feinmontage, "
            "ein Ansprechpartner und ein Zeitplan.\n\n"
            "Wenn du etwas Ähnliches planst – Besichtigung und Aufmaß kosten dich nichts."
        ),
    }


def _aus_video(ordner: Path, tag: date, saeule: str = "detail") -> dict:
    """Video als Reel. Das Titelbild wird gebrandet, das Video bleibt unangetastet."""
    info = _projekt_info(ordner)
    name = info.get("titel") or ordner.name.replace("-", " ").title()
    gewerk = info.get("gewerk", "Sanierung")
    video = _videos(ordner)[0]
    titelbild = _projekt_bild(ordner, "cover") or _projekt_bild(ordner, "nachher")

    return {
        "id": f"projekt-{ordner.name}-reel",
        "rubrik": saeule,
        "typ": "reel",
        "video": str(video),
        "titelbild": str(titelbild) if titelbild else None,
        "gewerk": gewerk,
        "hashtags": info.get("hashtags", "sanierung"),
        "datum": tag.isoformat(),
        # Das Titelbild des Reels ist die Kachel im Profil – gleiches Layout
        # wie bei Carousels, damit das Raster einheitlich bleibt.
        "vorlage": "cover-raster.html",
        "felder": {
            "gewerk": gewerk,
            "variante": info.get("variante") or farbvariante(tag),
            "oberlabel": info.get("badge", BADGES.get(saeule, "Baustelle")),
            "titel_vor": info.get("titel_vor", ""),
            "titel_stark": info.get("titel_stark", name),
            "titel_nach": info.get("titel_nach", ""),
            "titel_gross": info.get("titel_gross", True),
            "bild": str(titelbild) if titelbild else None,
            "bildlabel": info.get("bildlabel", ""),
        },
        "caption": info.get("caption") or (
            f"{name} – im Video.\n\n"
            f"Aufgenommen in {info.get('ort', 'Mülheim an der Ruhr')}. "
            "Alle Gewerke aus einer Hand, ein Ansprechpartner, ein Zeitplan.\n\n"
            "Fragen zu deinem Projekt? Kommentar oder DM."
        ),
    }


def _aus_pool(bild: Path, tag: date, saeule: str = "detail") -> dict:
    return {
        "id": f"pool-{bild.stem}",
        "rubrik": saeule,
        "vorlage": "projekt.html",
        "gewerk": "Sanierung",
        "hashtags": "sanierung",
        "datum": tag.isoformat(),
        "felder": {
            "gewerk": "Sanierung",
            "badge": BADGES.get(saeule, "Baustelle"),
            "eyebrow": "Aus der Werkstatt",
            "titel_vor": "Sauber ",
            "titel_stark": "übergeben",
            "titel_nach": ".",
            "lead": "Alle Gewerke aus einer Hand – von der Demontage bis zur Feinmontage.",
            "bild": str(bild),
        },
        "caption": "Ein Blick von der Baustelle in Mülheim an der Ruhr.\n\n"
                   "Was du hier siehst, ist das Ergebnis von Vorarbeit, die man später "
                   "nicht mehr sieht: gerader Untergrund, saubere Abdichtung, "
                   "durchlaufende Fugen.\n\n"
                   "Wenn du etwas Ähnliches planst – Besichtigung und Aufmaß kosten dich nichts.",
    }


def naechste_termine(anzahl: int, start: date | None = None) -> list[dict]:
    """Die nächsten `anzahl` tatsächlichen Post-Termine – unabhängig davon,
    wie viele Kalendertage das braucht.

    vorschau() nimmt eine feste Anzahl KALENDERTAGE entgegen; bei zwei Posts
    pro Woche reicht das nicht, um z. B. "die nächsten 9 Beiträge" (für das
    3x3-Profilraster) zuverlässig zu bekommen. Sicherheitsgrenze von zwei
    Jahren, falls "posttage" versehentlich leer ist.
    """
    start = start or date.today()
    verlauf = _zuletzt_verwendet()
    plaene: list[dict] = []
    tag = start
    grenze = date.fromordinal(start.toordinal() + 730)
    naechste_nummer = _naechste_freie_nummer()

    while len(plaene) < anzahl and tag < grenze:
        plan = plane(tag, verlauf, post_nummer=naechste_nummer)
        if plan is not None:
            verlauf[plan["id"]] = tag.isoformat()
            plaene.append(plan)
            naechste_nummer += 1
        tag = date.fromordinal(tag.toordinal() + 1)

    return plaene


def vorschau(tage: int = 7, start: date | None = None) -> list[dict]:
    """Plant mehrere Tage im Voraus – ohne den Verlauf auf der Platte zu ändern."""
    start = start or date.today()
    verlauf = _zuletzt_verwendet()
    plaene = []
    naechste_nummer = _naechste_freie_nummer()

    for i in range(tage):
        tag = date.fromordinal(start.toordinal() + i)
        plan = plane(tag, verlauf, post_nummer=naechste_nummer)
        if plan is None:                 # kein Posttag – z. B. Mo/Mi/Fr–So
            continue
        # In dieser Vorschau vergebene Themen für die Folgetage sperren.
        verlauf[plan["id"]] = tag.isoformat()
        plaene.append(plan)
        naechste_nummer += 1

    return plaene
