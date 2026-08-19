"""Baut die Bildunterschrift: Text + Handlungsaufruf + Hashtags.

Bewusst regelbasiert und ohne KI-Dienst – damit der tägliche Post nichts kostet
und immer denselben Ton trifft. Wer möchte, kann mit --ki eine Anthropic-Politur
zuschalten (nur dann fallen Kosten an).
"""
from __future__ import annotations

import os
import re
import textwrap
from datetime import date

from config import BRAND, HASHTAGS

MAX_ZEICHEN = 2200          # Instagram-Limit für Bildunterschriften


def _cta(tag: date) -> str:
    varianten = HASHTAGS["cta_varianten"]
    vorlage = varianten[tag.toordinal() % len(varianten)]
    return vorlage.format(
        telefon=BRAND["firma"]["telefon"],
        website=BRAND["firma"]["website"],
    )


def _rotiere(liste: list[str], versatz: int, anzahl: int) -> list[str]:
    """Nimmt `anzahl` Einträge ab `versatz` – umlaufend, ohne Zufall.

    Deterministisch, damit derselbe Tag immer denselben Block ergibt (wichtig
    für Vorschau und Wiederholbarkeit), aber von Tag zu Tag verschoben.
    """
    if not liste:
        return []
    return [liste[(versatz + i) % len(liste)] for i in range(min(anzahl, len(liste)))]


def _hashtags(set_name: str, tag: date, rubrik: str | None = None) -> str:
    """10–14 Tags, regional zuerst, pro Tag neu gemischt.

    Bei Vorher/Nachher-Beiträgen kommt zusätzlich ein Projekt-Hashtag dazu -
    recherchiert als eigene, wirksame Kategorie neben Branchen- und
    Regional-Tags (siehe README, Abschnitt Hashtags).
    """
    n = tag.toordinal()
    fachlich = HASHTAGS["sets"].get(set_name, HASHTAGS["sets"]["allgemein"])

    tags = (
        list(HASHTAGS["fest"])
        + _rotiere(HASHTAGS["regional"], n, 3)
        + _rotiere(fachlich, n, 5)
        + _rotiere(HASHTAGS["breit"], n, 2)
    )
    if rubrik == "vorher-nachher":
        tags += HASHTAGS.get("projekt", ["#vorhernachher"])

    gesehen, sauber = set(), []
    for t in tags:
        if t.lower() not in gesehen:
            gesehen.add(t.lower())
            sauber.append(t)
    return " ".join(sauber)


def baue_caption(plan: dict, mit_ki: bool = False) -> str:
    tag = date.fromisoformat(plan["datum"])
    kern = plan["caption"].strip()

    if mit_ki:
        kern = _ki_politur(kern, plan)

    teile = [kern, "", _cta(tag), "",
             _hashtags(plan.get("hashtags", "allgemein"), tag, plan.get("rubrik"))]
    text = "\n".join(teile).strip()

    if len(text) > MAX_ZEICHEN:
        ueberhang = len(text) - MAX_ZEICHEN
        kern = textwrap.shorten(kern, width=max(200, len(kern) - ueberhang - 20), placeholder=" …")
        text = "\n".join([kern, "", _cta(tag), "",
                          _hashtags(plan.get("hashtags", "allgemein"), tag, plan.get("rubrik"))])
    return text


def baue_caption_facebook(plan: dict) -> str:
    """Fassung für die Facebook-Seite.

    Drei Unterschiede zu Instagram, die in der Praxis zählen:
      1. Links sind klickbar – die Website gehört als echte Adresse in den Text,
         nicht als "Link in Bio".
      2. Große Hashtag-Blöcke wirken auf Facebook deplatziert und bringen dort
         kaum Reichweite. Zwei bis drei reichen.
      3. Kein Zeichenlimit in der Praxis, der Text darf ausatmen.
    """
    tag = date.fromisoformat(plan["datum"])
    kern = plan["caption"].strip()

    fon = BRAND["firma"]["telefon"]
    web = BRAND["firma"]["website"]
    ort = BRAND["firma"]["region"]

    schluss = (f"Berisa Bau · {ort}\n"
               f"Kostenlose Besichtigung: {fon}\n"
               f"https://{web}")

    # Nur die Marken- und Ortsmarke, keine Fachtag-Wand.
    tags = " ".join(HASHTAGS["fest"])

    return "\n\n".join([kern, schluss, tags])


def baue_alt_text(plan: dict) -> str:
    """Bildbeschreibung für Screenreader.

    Instagram nimmt sie über das Feld alt_text entgegen. Kostet nichts und
    macht die Beiträge für sehbeeinträchtigte Nutzer zugänglich.
    """
    f = plan.get("felder", {})
    satz = ["Grafik von Berisa Bau"]
    if f.get("gewerk"):
        satz.append(f"zum Thema {f['gewerk']}")

    kopf = "".join(str(f.get(k, "")) for k in ("titel_vor", "titel_stark", "titel_nach"))
    if kopf.strip():
        satz.append(f"mit der Überschrift „{kopf.strip().rstrip('.')}“")
    elif f.get("frage"):
        satz.append(f"mit der Frage „{f['frage']}“")
    elif f.get("zitat"):
        satz.append(f"mit dem Kundenzitat „{f['zitat'].rstrip('.')}“")

    saetze = [" ".join(satz) + "."]

    if plan.get("rubrik") == "vorher-nachher":
        saetze.append("Links das Bild vor der Sanierung, rechts danach.")
    elif f.get("bild"):
        saetze.append("Im Hintergrund ein Foto von der Baustelle.")

    if f.get("punkte"):
        klartext = [re.sub(r"<[^>]+>", "", str(p)) for p in f["punkte"]]
        saetze.append("Stichpunkte: " + "; ".join(klartext) + ".")

    return " ".join(saetze)


def _ki_politur(text: str, plan: dict) -> str:
    """Optional: Anthropic-API glättet den Text. Ohne Schlüssel unverändert."""
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return text
    try:
        import anthropic
    except ImportError:
        return text

    ton = BRAND["tonalitaet"]
    client = anthropic.Anthropic(api_key=key)
    antwort = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=600,
        system=(
            f"Du schreibst Instagram-Texte für den Handwerksbetrieb Berisa Bau "
            f"({BRAND['firma']['plz_ort']}). Stimme: {ton['stimme']} Anrede: {ton['anrede']}. "
            f"Verboten: {', '.join(ton['verboten'])}. "
            "Gib ausschließlich den überarbeiteten Text zurück, ohne Hashtags, "
            "ohne Anführungszeichen, maximal 800 Zeichen."
        ),
        messages=[{"role": "user", "content":
                   f"Gewerk: {plan.get('gewerk')}\nRubrik: {plan.get('rubrik')}\n\n{text}"}],
    )
    return antwort.content[0].text.strip()
