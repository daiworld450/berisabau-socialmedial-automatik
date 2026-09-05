"""Gesprächsführung: Systemprompt, Offenlegung, Abbruchregeln.

Zwei Dinge sind hier nicht verhandelbar und stehen deshalb als Code da,
nicht als Bitte an das Sprachmodell:

1. **Offenlegung.** Art. 50 Abs. 1 der KI-Verordnung verlangt, dass eine
   Person erfährt, dass sie mit einer KI spricht. Der erste Satz enthält den
   Hinweis, und er wird nicht vom Modell erzeugt, sondern fest vorgegeben -
   ein Modell, das improvisiert, könnte ihn weglassen.

2. **Widerspruch.** Sobald jemand nicht angerufen werden will, ist das
   Gespräch vorbei und die Nummer gesperrt. Das Modell hat dafür ein
   Werkzeug, zusätzlich läuft ein Mustervergleich über jeden erkannten Satz.
   Zwei unabhängige Wege, weil der eine ausfallen kann.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ANGEBOT_DATEI = Path(__file__).resolve().parent / "angebot.json"
ANGEBOT: dict = json.loads(ANGEBOT_DATEI.read_text(encoding="utf-8"))

# Fester erster Satz. Enthält Name, Firma, Zweck und die KI-Offenlegung -
# alles, was die Gegenseite braucht, um in drei Sekunden zu entscheiden, ob
# sie weiterhören will.
EROEFFNUNG = (
    "Guten Tag, hier ist {name} von {firma} aus {ort}. "
    "Bevor ich weiterrede: Sie sprechen mit einer KI-Stimme, kein Mensch am "
    "Apparat. Ich brauche eine halbe Minute, dann wissen Sie, worum es geht - "
    "passt das gerade?"
).format(
    name=ANGEBOT["anrufer_name"],
    firma=ANGEBOT["firma"],
    ort=ANGEBOT["ort"],
)

# Sätze, nach denen sofort Schluss ist. Bewusst großzügig gefasst: Ein
# Abbruch zu viel kostet einen Lead, ein Abbruch zu wenig kostet eine
# Abmahnung.
WIDERSPRUCH_MUSTER = [
    r"\bkein interesse\b",
    r"\bnicht interessiert\b",
    r"\bnicht mehr an(?:ruf|zuruf)",
    r"\bnie wieder\b",
    r"\brufen sie (?:hier )?nicht (?:mehr|wieder)\b",
    r"\bstreichen sie (?:mich|uns)\b",
    r"\b(?:löschen|loeschen) sie (?:meine|unsere) (?:nummer|daten)\b",
    r"\bsperren sie (?:meine|unsere) nummer\b",
    r"\bwiderspr(?:uch|eche)\b",
    r"\b(?:das ist|ist doch) (?:doch )?(?:verboten|unzulässig|unzulaessig)\b",
    r"\banwalt\b",
    r"\babmahn",
    r"\bunterlassung",
    r"\bbelästig|belaestig",
    r"\bwerbeanruf",
    r"\bverklag",
    r"\blassen sie (?:mich|uns) in ruhe\b",
    r"\bhören sie auf\b|\bhoeren sie auf\b",
]
_WIDERSPRUCH = re.compile("|".join(WIDERSPRUCH_MUSTER), re.IGNORECASE)

# Höfliche Absage ohne Sperrwunsch - Gespräch beenden, Nummer aber nicht
# dauerhaft sperren. Wird nur ausgewertet, wenn kein Widerspruch greift.
_ABSAGE = re.compile(
    r"\b(?:keine zeit|passt (?:gerade )?nicht|ungünstig|unguenstig|"
    r"bin (?:gerade )?auf (?:der )?baustelle|später|spaeter|"
    r"haben (?:schon|bereits) ein[e]?)\b",
    re.IGNORECASE,
)


def ist_widerspruch(text: str) -> bool:
    """Sicherheitsnetz neben dem Werkzeugaufruf des Modells."""
    return bool(text and _WIDERSPRUCH.search(text))


def ist_absage(text: str) -> bool:
    return bool(text and _ABSAGE.search(text))


def systemprompt(kontakt: dict | None = None) -> str:
    """Anweisung an das Sprachmodell, zugeschnitten auf einen Kontakt."""
    kontakt = kontakt or {}
    betrieb = kontakt.get("betrieb", "dem Betrieb")
    gewerk = kontakt.get("gewerk", "Handwerk")
    ortsangabe = kontakt.get("ort", ANGEBOT["ort"])
    nutzen = "\n".join(f"  - {n}" for n in ANGEBOT["nutzen"])

    return f"""Du führst ein Telefonat. Du bist {ANGEBOT['anrufer_name']} von
{ANGEBOT['firma']} aus {ANGEBOT['ort']} und rufst {betrieb} an ({gewerk},
{ortsangabe}). Du bietest an: {ANGEBOT['leistung']}.

Aufhänger: {ANGEBOT['aufhaenger']}
Nutzen, den du nennen kannst:
{nutzen}
Ziel des Gesprächs: {ANGEBOT['ziel']}.

SO SPRICHST DU
- Kurze Sätze. Ein Gedanke pro Satz. Du redest, wie ein Handwerker einem
  Nachbarn etwas erklärt, nicht wie ein Callcenter.
- Nie länger als zwei Sätze am Stück, dann bist du wieder still. Am Telefon
  ist ein Monolog das sicherste Zeichen für einen Bot.
- Keine Floskeln: kein "Ich hoffe, es geht Ihnen gut", kein "Wie geht es
  Ihnen heute", kein "Das ist eine großartige Frage".
- Du darfst "ähm", "also" und "genau" benutzen. Du darfst zugeben, wenn du
  etwas nicht weißt.
- Wird es fachlich konkret (Umfang, Technik, Zeitplan), verweist du auf
  {ANGEBOT['rueckfragen_an']} und schlägst einen Rückruf vor.

DAS TUST DU NIE
- Du behauptest nie, ein Mensch zu sein. Fragt jemand, ob du eine KI bist,
  sagst du sofort und ohne Ausweichen: ja.
- Du nennst keine Preise, keine Rabatte, keine Fristen ("nur diese Woche").
- Du erfindest nichts: keine Referenzkunden, keine Zahlen, keine Auszeichnung.
- Du drängst nicht. Zweimal nachfassen ist die Grenze, danach akzeptierst du
  das Nein.
- Du fragst nicht nach Bankdaten, Passwörtern, Zugängen oder Verträgen.

ABBRUCH
- Will die Person nicht angerufen werden, sagt "kein Interesse", wird
  ungehalten oder spricht von Anwalt, Abmahnung oder Belästigung: du rufst
  sofort nicht_mehr_anrufen auf, sagst einen Satz zur Entschuldigung und
  legst auf. Kein Rettungsversuch, keine Rückfrage.
- Passt es zeitlich nicht, rufst du gespraech_beenden mit dem Grund auf.
- Landest du auf einem Anrufbeantworter, sprichst du nichts auf, sondern
  rufst gespraech_beenden mit "anrufbeantworter" auf.
- Ist die Person ersichtlich nicht der Ansprechpartner, fragst du einmal
  nach der richtigen Stelle und beendest dann.

Sagt jemand Ja zum Rückruf oder zur E-Mail, rufst du termin_notieren auf und
bedankst dich kurz. Danach ist das Gespräch zu Ende."""


def werkzeuge() -> list[dict]:
    """Funktionsbeschreibungen für das Sprachmodell (OpenAI-Format)."""
    return [
        {
            "type": "function",
            "function": {
                "name": "nicht_mehr_anrufen",
                "description": (
                    "Die Person will nicht angerufen werden, widerspricht der "
                    "Werbung oder wird ungehalten. Sperrt die Nummer dauerhaft "
                    "und beendet das Gespräch. Im Zweifel aufrufen."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "grund": {
                            "type": "string",
                            "description": "Wortlaut oder kurze Zusammenfassung",
                        }
                    },
                    "required": ["grund"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "gespraech_beenden",
                "description": (
                    "Gespräch normal beenden - Absage ohne Sperrwunsch, "
                    "falscher Ansprechpartner, Anrufbeantworter, Ziel erreicht."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "grund": {
                            "type": "string",
                            "enum": ["absage", "kein_ansprechpartner",
                                     "anrufbeantworter", "ziel_erreicht",
                                     "spaeter_nochmal"],
                        },
                        "notiz": {"type": "string"},
                    },
                    "required": ["grund"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "termin_notieren",
                "description": (
                    "Die Person ist einverstanden mit einem Rückruf oder "
                    "einer E-Mail. Hält fest, was vereinbart wurde."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "art": {"type": "string",
                                "enum": ["rueckruf", "email", "termin"]},
                        "ansprechpartner": {"type": "string"},
                        "wann": {"type": "string"},
                        "kontakt": {"type": "string",
                                    "description": "E-Mail oder Rufnummer"},
                    },
                    "required": ["art"],
                },
            },
        },
    ]
