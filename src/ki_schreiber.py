"""Schreibt neue Themen per KI – OpenAI (ChatGPT) primär, Anthropic optional.

Grundregel: Die KI bekommt exakt denselben Maßstab wie die menschlichen
Redakteure – content/CONTENT-PROMPT.md wird unverändert als Systemprompt
verwendet, nicht neu formuliert. Ein von der KI geschriebenes Thema muss
dieselbe Selbstprüfung bestehen wie jedes andere (src/pruefung.py), bevor es
in content/themen.json aufgenommen werden kann. KI-Text ist damit ein
zusätzlicher Autor, kein Weg an der Qualitätssicherung vorbei.

Zwei Anbieter, weil unterschiedlich verfügbar:
  - OPENAI_API_KEY   -> ChatGPT (chat.completions, JSON-Modus)
  - ANTHROPIC_API_KEY -> Claude (messages, Tool-Use für strukturierte Ausgabe)
Ist keiner gesetzt, meldet das Modul einen klaren Fehler statt zu raten.
"""
from __future__ import annotations

import json
import re

import requests

from config import BRAND, CONTENT_DIR, HASHTAGS

CONTENT_PROMPT_DATEI = CONTENT_DIR / "CONTENT-PROMPT.md"

OPENAI_MODELL = "gpt-4o-mini"
ANTHROPIC_MODELL = "claude-sonnet-5"
TIMEOUT = 60

# Lokale Suchbegriffe, die eine Caption glaubwürdig tragen kann, ohne
# gestopft zu wirken. Ein bis zwei genügen – das ist keine Keyword-Wand.
SEO_BEGRIFFE = [
    "Mülheim an der Ruhr", "Badsanierung", "Fliesenleger", "Sanierung",
    "Renovierung", "Handwerksbetrieb", "Ruhrgebiet",
]

SCHEMA_FELDER = {
    "id", "rubrik", "vorlage", "gewerk", "hashtags", "felder", "caption",
}


class SchreibFehler(RuntimeError):
    pass


def _lade_content_prompt() -> str:
    if not CONTENT_PROMPT_DATEI.exists():
        raise SchreibFehler(f"{CONTENT_PROMPT_DATEI} fehlt – ohne den Maßstab "
                            "schreibt die KI blind.")
    return CONTENT_PROMPT_DATEI.read_text(encoding="utf-8")


def _system_prompt() -> str:
    saeulen = ", ".join(sorted(set(HASHTAGS["sets"])))
    return f"""{_lade_content_prompt()}

---

ZUSÄTZLICH FÜR DICH ALS KI-AUTOR:

Du schreibst GENAU EIN neues Thema für content/themen.json, im selben Stil
wie ein menschlicher Redakteur nach diesem Content-Prompt. Halte dich an
JEDE Regel oben – Ton, Verbote, Formatgrenzen, Hook-Länge.

SEO: Bau natürlich (nicht gestopft) ein bis zwei lokale Suchbegriffe in die
Caption ein, passend zum Thema. Beispiele: {", ".join(SEO_BEGRIFFE)}.
Diese Begriffe helfen bei der Google-Auffindbarkeit von öffentlichen
Facebook-Beiträgen und der Instagram-Suche – sie dürfen aber nie den
Lesefluss stören. Ein Wort wie „Badsanierung in Mülheim an der Ruhr"
irgendwo im Fließtext reicht.

hashtags-Feld: eines von {saeulen}.

Gib AUSSCHLIESSLICH ein einziges JSON-Objekt zurück, keinen Fließtext davor
oder danach, mit genau diesen Schlüsseln:
{{
  "id": "kurzer-kebab-case-slug",
  "rubrik": "wissen | fehler | detail | mensch",
  "vorlage": "tipp.html oder faq.html",
  "gewerk": "eines der Gewerke aus dem Content-Prompt",
  "hashtags": "eines von {saeulen}",
  "felder": {{
    "badge": "Wissen | Achtung | Detail | Baustelle",
    "eyebrow": "2-4 Wörter Überzeile",
    "titel_vor": "...", "titel_stark": "...", "titel_nach": "...",
    "lead": "ein Satz, max. 85 Zeichen",
    "punkte": ["<b>Schlagwort</b> Rest", "...", "..."]
  }},
  "caption": "Hook-Zeile (max 80 Zeichen)\\n\\nAbsatz 1\\n\\nAbsatz 2\\n\\nAbsatz 3"
}}

Bei vorlage "faq.html": felder bekommt stattdessen "frage", "antwort"
(HTML mit <b> und <br><br>), "hinweis" – keine punkte, kein titel_*."""


def _nutzer_prompt(saeule: str, gewerk: str, stichwort: str | None) -> str:
    teile = [f"Säule: {saeule}", f"Gewerk: {gewerk}"]
    if stichwort:
        teile.append(f"Thema/Stichwort: {stichwort}")
    else:
        teile.append("Thema: wähle selbst etwas Konkretes, Fachliches zu "
                     "diesem Gewerk, das noch nicht in der Themenbank steht.")
    return "\n".join(teile)


def _json_aus_antwort(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as fehler:
        raise SchreibFehler(f"KI-Antwort ist kein gültiges JSON: {fehler}\n"
                            f"Antwort: {text[:400]}")


# --------------------------------------------------------------------------- #
def _openai(system: str, nutzer: str, key: str) -> dict:
    antwort = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": OPENAI_MODELL,
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": nutzer},
            ],
        },
        timeout=TIMEOUT,
    )
    daten = antwort.json()
    if antwort.status_code >= 400:
        fehler = daten.get("error", {}).get("message", antwort.text[:300])
        raise SchreibFehler(f"OpenAI-Fehler ({antwort.status_code}): {fehler}")
    inhalt = daten["choices"][0]["message"]["content"]
    return _json_aus_antwort(inhalt)


def _anthropic(system: str, nutzer: str, key: str) -> dict:
    antwort = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        json={
            "model": ANTHROPIC_MODELL,
            "max_tokens": 1200,
            "system": system,
            "messages": [{"role": "user", "content": nutzer + "\n\nNur das JSON, sonst nichts."}],
        },
        timeout=TIMEOUT,
    )
    daten = antwort.json()
    if antwort.status_code >= 400:
        fehler = daten.get("error", {}).get("message", antwort.text[:300])
        raise SchreibFehler(f"Anthropic-Fehler ({antwort.status_code}): {fehler}")
    inhalt = daten["content"][0]["text"]
    return _json_aus_antwort(inhalt)


# --------------------------------------------------------------------------- #
def schreibe_thema(saeule: str, gewerk: str, stichwort: str | None = None,
                   anbieter: str | None = None,
                   openai_key: str | None = None,
                   anthropic_key: str | None = None) -> dict:
    """Lässt ein Thema schreiben. Wirft SchreibFehler, wenn kein Schlüssel da ist.

    Schlüssel werden als Parameter übergeben statt aus os.environ gelesen –
    so bleibt klar sichtbar, woher sie kommen, und das Modul erzwingt nicht
    heimlich einen bestimmten Ladeweg.
    """
    system = _system_prompt()
    nutzer = _nutzer_prompt(saeule, gewerk, stichwort)

    reihenfolge = [anbieter] if anbieter else ["openai", "anthropic"]
    fehler_gesammelt = []

    for a in reihenfolge:
        if a == "openai" and openai_key:
            try:
                thema = _openai(system, nutzer, openai_key)
                thema["_ki_anbieter"] = f"openai:{OPENAI_MODELL}"
                return _validiere_struktur(thema)
            except SchreibFehler as f:
                fehler_gesammelt.append(str(f))
        elif a == "anthropic" and anthropic_key:
            try:
                thema = _anthropic(system, nutzer, anthropic_key)
                thema["_ki_anbieter"] = f"anthropic:{ANTHROPIC_MODELL}"
                return _validiere_struktur(thema)
            except SchreibFehler as f:
                fehler_gesammelt.append(str(f))

    if not openai_key and not anthropic_key:
        raise SchreibFehler(
            "Kein API-Schlüssel gefunden. OPENAI_API_KEY oder "
            "ANTHROPIC_API_KEY in der .env setzen – siehe README, "
            "Abschnitt 'KI schreibt Themen'.")
    raise SchreibFehler("Alle Anbieter fehlgeschlagen: " + " | ".join(fehler_gesammelt))


def _validiere_struktur(thema: dict) -> dict:
    fehlend = SCHEMA_FELDER - thema.keys()
    if fehlend:
        raise SchreibFehler(f"KI-Antwort ohne Pflichtfelder: {fehlend}")
    return thema
