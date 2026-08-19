"""Selbstprüfung nach content/CONTENT-PROMPT.md, Abschnitt 8.

Prüft, was sich maschinell prüfen lässt. Was Urteilsvermögen braucht
(„ist das ein echtes Fachdetail?"), bleibt beim Menschen – dafür gibt es
den Agenten berisabau-redaktion.
"""
from __future__ import annotations

import json
import re
from datetime import date

from config import CONTENT_DIR, HASHTAGS, THEMEN
import texter

MAX_HOOK = 80
MAX_CAPTION = 2200
MIN_TAGS, MAX_TAGS = 10, 14
MAX_HEADLINE = 46          # Layoutgrenze bei ~92 px Schrift auf 1080 px
MAX_LEAD = 95
MAX_PUNKT = 105
MAX_ANTWORT = 560          # FAQ-Karte, sonst läuft der Text aus dem Bild
MAX_FRAGE = 70

# Positivliste geprüfter Normen. Alles andere muss belegt werden, bevor es
# in einen Beitrag darf – ein falscher Normbezug schadet mehr als keiner.
GEPRUEFTE_NORMEN = {
    "DIN 18534",      # Abdichtung Innenräume
    "DIN 18560",      # Estrich
    "DIN 18202",      # Ebenheitstoleranzen
    "DIN EN 1264",    # Fußbodenheizung
    "DIN EN 1996",    # Mauerwerksbau, Schlitze
    "DIN 4109",       # Schallschutz
    "TRGS 519",       # Asbest
    "VDE 0100-701",   # Badezimmer-Schutzbereiche
}
NORM_MUSTER = re.compile(
    r"\b(DIN\s+EN\s+ISO\s+\d+|DIN\s+EN\s+\d+|DIN\s+\d+|TRGS\s+\d+|"
    r"VDE\s+\d[\d\-]*|VOB(?:/[A-C])?|ISO\s+\d+)")

# Wörter, die laut Content-Prompt nicht vorkommen dürfen.
SUPERLATIVE = re.compile(
    r"\b(beste[rsn]?|billig|günstigste[rsn]?|unschlagbar|Nr\.?\s*1|"
    r"einzigartig|perfekt|revolutionär|sensationell)\b", re.IGNORECASE)
PREISE = re.compile(r"\b\d+\s*(€|EUR|Euro)\b|\b(ab|nur)\s+\d+\s*(€|EUR)", re.IGNORECASE)
ZUSAGEN = re.compile(r"\b(garantiert|in \d+ Tagen fertig|hält \d+ Jahre|"
                     r"100\s*%\s*(sicher|dicht))\b", re.IGNORECASE)


def _hook(caption: str) -> str:
    return caption.split("\n")[0].strip()


def pruefe_thema(thema: dict) -> list[str]:
    fehler = []
    caption = thema.get("caption", "")
    hook = _hook(caption)

    if len(hook) > MAX_HOOK:
        fehler.append(f"Hook {len(hook)} Zeichen (max. {MAX_HOOK}): „{hook[:60]}…\"")
    if not hook:
        fehler.append("Kein Hook in Zeile 1")

    for muster, name in ((SUPERLATIVE, "Superlativ"), (PREISE, "Preisangabe"),
                         (ZUSAGEN, "Zusage")):
        treffer = muster.search(caption)
        if treffer:
            fehler.append(f"{name} in der Caption: „{treffer.group(0)}\"")

    # Headline im Bild darf nicht derselbe Satz sein wie der Hook.
    f = thema.get("felder", {})
    kopf = "".join(str(f.get(k, "")) for k in ("titel_vor", "titel_stark", "titel_nach"))
    if kopf and hook and kopf.strip().rstrip(".").lower() == hook.rstrip(".").lower():
        fehler.append("Headline im Bild ist derselbe Satz wie der Hook")

    # Gesamtlänge inklusive Hashtags
    plan = {"datum": date.today().isoformat(), "caption": caption,
            "hashtags": thema.get("hashtags", "allgemein"),
            "rubrik": thema.get("rubrik", ""), "felder": f}
    gesamt = texter.baue_caption(plan)
    if len(gesamt) > MAX_CAPTION:
        fehler.append(f"Caption mit Hashtags {len(gesamt)} Zeichen (max. {MAX_CAPTION})")

    if thema.get("hashtags") not in HASHTAGS["sets"]:
        fehler.append(f"Unbekanntes Hashtag-Set: {thema.get('hashtags')}")

    # --- Normen gegen die Positivliste -------------------------------------- #
    volltext = " ".join([caption, kopf, str(f.get("lead", "")),
                         " ".join(str(p) for p in f.get("punkte", [])),
                         str(f.get("antwort", "")), str(f.get("hinweis", ""))])
    for treffer in NORM_MUSTER.findall(volltext):
        sauber = re.sub(r"\s+", " ", treffer).strip()
        if sauber.startswith("VOB"):
            continue          # VOB ist ein Vertragswerk, keine technische Norm
        if sauber not in GEPRUEFTE_NORMEN:
            fehler.append(f"Norm nicht auf der Positivliste: „{sauber}“ "
                          "– belegen oder ohne Nummer formulieren")

    # --- Layoutgrenzen ------------------------------------------------------- #
    if thema.get("vorlage") == "faq.html":
        # Die FAQ-Karten müssen zwischen Kopf- und Fußzeile passen; darüber
        # läuft der Text unten aus dem Bild.
        klartext = re.sub(r"<[^>]+>", "", str(f.get("antwort", "")))
        if len(klartext) > MAX_ANTWORT:
            fehler.append(f"FAQ-Antwort {len(klartext)} Zeichen (max. {MAX_ANTWORT})")
        if len(str(f.get("frage", ""))) > MAX_FRAGE:
            fehler.append(f"FAQ-Frage {len(f['frage'])} Zeichen (max. {MAX_FRAGE})")
    else:
        # Fehlendes Leerzeichen zwischen den Headline-Teilen ergibt im Bild
        # zusammengeklebte Wörter („Wenn die Wandandersaussieht").
        for a, b in (("titel_vor", "titel_stark"), ("titel_stark", "titel_nach")):
            links, rechts = str(f.get(a, "")), str(f.get(b, ""))
            if not links or not rechts:
                continue
            if links[-1] not in " „(" and rechts[0] not in " ,.?!–:":
                fehler.append(f"Leerzeichen fehlt zwischen {a} und {b}: "
                              f"„{links[-12:]}|{rechts[:12]}“")

    if len(kopf) > MAX_HEADLINE:
        fehler.append(f"Headline {len(kopf)} Zeichen (max. {MAX_HEADLINE}): bricht das Layout")
    if len(str(f.get("lead", ""))) > MAX_LEAD:
        fehler.append(f"Lead {len(f['lead'])} Zeichen (max. {MAX_LEAD})")
    for i, p in enumerate(f.get("punkte", []), 1):
        klar = re.sub(r"<[^>]+>", "", str(p))
        if len(klar) > MAX_PUNKT:
            fehler.append(f"Stichpunkt {i}: {len(klar)} Zeichen (max. {MAX_PUNKT})")

    return fehler


def pruefe_hashtags() -> list[str]:
    fehler = []
    for satz in HASHTAGS["sets"]:
        for tag in (date(2026, 1, 1), date(2026, 6, 15), date(2026, 11, 30)):
            tags = texter._hashtags(satz, tag).split()
            if not MIN_TAGS <= len(tags) <= MAX_TAGS:
                fehler.append(f"{satz} am {tag}: {len(tags)} Tags "
                              f"(erwartet {MIN_TAGS}–{MAX_TAGS})")
            for pflicht in HASHTAGS["fest"]:
                if pflicht not in tags:
                    fehler.append(f"{satz} am {tag}: {pflicht} fehlt")
    return fehler


def pruefe_carousels() -> list[str]:
    datei = CONTENT_DIR / "carousels.json"
    if not datei.exists():
        return []
    fehler = []
    for c in json.loads(datei.read_text(encoding="utf-8"))["carousels"]:
        slides = c["slides"]
        if not 2 <= len(slides) <= 10:
            fehler.append(f"{c['id']}: {len(slides)} Slides (erlaubt 2–10)")
        if slides and slides[0]["vorlage"] != "cover.html":
            fehler.append(f"{c['id']}: erste Slide ist kein Cover")
        hook = _hook(c.get("caption", ""))
        if len(hook) > MAX_HOOK:
            fehler.append(f"{c['id']}: Hook {len(hook)} Zeichen")
        cover_kopf = "".join(str(slides[0].get(k, ""))
                             for k in ("titel_vor", "titel_stark", "titel_nach"))
        if cover_kopf.strip().rstrip(".").lower() == hook.rstrip(".").lower():
            fehler.append(f"{c['id']}: Cover-Headline gleich dem Hook")
    return fehler


# Lokale/fachliche Suchbegriffe für die informative SEO-Prüfung. Kein
# Pflichtfeld - eine gute Caption braucht nicht in jedem Satz "Mülheim",
# aber über die ganze Themenbank gesehen sollte der Ortsname im FLIESSTEXT
# (nicht nur in Hashtags/Fußzeile) öfter vorkommen als selten, weil das bei
# öffentlich indexierten Facebook-Beiträgen und der Instagram-Suche zählt.
SEO_BEGRIFFE = [
    "mülheim", "ruhr", "badsanierung", "fliesenleger", "sanierung",
    "renovierung", "handwerksbetrieb", "gewährleistung",
]


def seo_audit() -> dict:
    """Wie viele freigegebene Captions tragen einen lokalen/fachlichen Begriff
    im Fließtext (nicht in Hashtags)? Rein informativ, blockiert nichts."""
    treffer, ohne = [], []
    for thema in THEMEN["themen"]:
        if thema.get("pruefen"):
            continue
        text = thema.get("caption", "").lower()
        gefunden = [b for b in SEO_BEGRIFFE if b in text]
        (treffer if gefunden else ohne).append((thema["id"], gefunden))

    gesamt = len(treffer) + len(ohne)
    return {
        "gesamt": gesamt,
        "mit_keyword": len(treffer),
        "anteil": round(100 * len(treffer) / gesamt, 1) if gesamt else 0.0,
        "ohne_keyword": [tid for tid, _ in ohne],
    }


def alles() -> tuple[int, list[str]]:
    """Gibt (Anzahl geprüfter Einheiten, Liste der Befunde) zurück."""
    befunde = []
    geprueft = 0

    for thema in THEMEN["themen"]:
        if thema.get("pruefen"):
            continue           # gesperrt, wird ohnehin nicht gepostet
        geprueft += 1
        for f in pruefe_thema(thema):
            befunde.append(f"{thema['id']}: {f}")

    befunde += pruefe_hashtags()
    befunde += pruefe_carousels()
    return geprueft, befunde
