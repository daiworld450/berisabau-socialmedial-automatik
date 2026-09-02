"""Zugänge und Grenzwerte des Telefonagenten.

Bewusst getrennt von src/config.py: Der Telefonteil läuft nicht in GitHub
Actions, sondern auf einem dauerhaft erreichbaren Server (WebSocket-
Verbindung zu Twilio). Er teilt sich mit dem Rest nur die .env-Datei.

Kein Schlüssel steht hier im Klartext. Fehlt einer, meldet pruefe_zugaenge()
das beim Start, statt mitten im Anruf zu scheitern.
"""
from __future__ import annotations

import os
from pathlib import Path

WURZEL = Path(__file__).resolve().parent
DATEN = WURZEL / "daten"
DATEN.mkdir(exist_ok=True)

SPERRLISTE_DATEI = DATEN / "sperrliste.json"
PROTOKOLL_DATEI = DATEN / "anrufe.jsonl"
KAMPAGNE_DATEI = DATEN / "kampagne.json"

# --- Telefonie ------------------------------------------------------------- #
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
# Absendernummer in E.164. Muss eine echte, auf den Betrieb registrierte
# Nummer sein - Rufnummernunterdrückung und gefälschte Absender sind nach
# § 120 TKG verboten und kosten bis 10.000 € je Fall.
TWILIO_NUMMER = os.getenv("TWILIO_NUMMER", "")

# Öffentlich erreichbare Basis-URL dieses Servers, ohne Schrägstrich am Ende.
# Twilio ruft sie an, um den Medienstrom aufzubauen: https://... bzw. wss://...
OEFFENTLICHE_URL = os.getenv("TELEFON_BASIS_URL", "").rstrip("/")
SERVER_PORT = int(os.getenv("TELEFON_PORT") or "8080")

# --- Sprache --------------------------------------------------------------- #
DEEPGRAM_KEY = os.getenv("DEEPGRAM_API_KEY", "")
ELEVENLABS_KEY = os.getenv("ELEVENLABS_API_KEY", "")
# ID des geklonten Stimmprofils aus dem ElevenLabs-Konto.
ELEVENLABS_STIMME = os.getenv("ELEVENLABS_STIMME_ID", "")
# Flash v2.5 ist das schnellste Modell (~75 ms) und kann Deutsch. Turbo v2.5
# klingt etwas voller, kostet aber rund 100 ms mehr - hörbar am Telefon.
ELEVENLABS_MODELL = os.getenv("ELEVENLABS_MODELL", "eleven_flash_v2_5")

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
# Kleines Modell mit Absicht: Ein Akquisegespräch braucht kein Weltwissen,
# sondern Tempo. Jede 100 ms Nachdenkzeit hört der Angerufene.
LLM_MODELL = os.getenv("TELEFON_LLM_MODELL", "gpt-4o-mini")

# --- Grenzen --------------------------------------------------------------- #
# Eigene Obergrenze, keine technische. Wer 500 Nummern am Tag anwählt, fällt
# beim Netzbetreiber und bei der Bundesnetzagentur als Massenanrufer auf.
MAX_ANRUFE_PRO_TAG = int(os.getenv("TELEFON_MAX_PRO_TAG") or "40")
# Gleichzeitige Leitungen. Mehr als zwei sieht nach Callcenter aus.
MAX_GLEICHZEITIG = int(os.getenv("TELEFON_MAX_GLEICHZEITIG") or "1")
# Sekunden Pause zwischen zwei Wahlvorgängen.
PAUSE_ZWISCHEN_ANRUFEN = int(os.getenv("TELEFON_PAUSE") or "45")
# Harte Obergrenze je Gespräch. Ein Akquiseanruf, der länger dauert, ist
# entweder ein echtes Verkaufsgespräch (dann übernimmt ein Mensch) oder
# entgleist.
MAX_GESPRAECHSDAUER = int(os.getenv("TELEFON_MAX_DAUER") or "180")
# Ein zweiter Versuch ist zulässig, ein dritter ist Belästigung.
MAX_VERSUCHE_JE_NUMMER = int(os.getenv("TELEFON_MAX_VERSUCHE") or "2")
# Tage, die zwischen zwei Versuchen bei derselben Nummer liegen müssen.
ABSTAND_TAGE = int(os.getenv("TELEFON_ABSTAND_TAGE") or "14")

# Mobilnummern sind standardmäßig gesperrt: Hinter 0151/0176 steckt oft eine
# Privatperson, und bei Verbrauchern ist der Werbeanruf ohne ausdrückliche
# vorherige Einwilligung ausnahmslos rechtswidrig (§ 7 Abs. 2 Nr. 1 UWG).
# Nur bewusst und für nachweislich geschäftliche Mobilnummern aufheben.
MOBIL_ERLAUBT = os.getenv("TELEFON_MOBIL_ERLAUBT", "").strip() in ("1", "true", "ja")

# Probelauf: wählt nicht, protokolliert nur, was passiert wäre.
TROCKENLAUF = os.getenv("TELEFON_TROCKENLAUF", "").strip() in ("1", "true", "ja")


def fehlende_zugaenge() -> list[str]:
    """Namen der Umgebungsvariablen, ohne die kein Anruf zustande kommt."""
    pflicht = {
        "TWILIO_ACCOUNT_SID": TWILIO_SID,
        "TWILIO_AUTH_TOKEN": TWILIO_TOKEN,
        "TWILIO_NUMMER": TWILIO_NUMMER,
        "TELEFON_BASIS_URL": OEFFENTLICHE_URL,
        "DEEPGRAM_API_KEY": DEEPGRAM_KEY,
        "ELEVENLABS_API_KEY": ELEVENLABS_KEY,
        "ELEVENLABS_STIMME_ID": ELEVENLABS_STIMME,
        "OPENAI_API_KEY": OPENAI_KEY,
    }
    return [name for name, wert in pflicht.items() if not wert]
