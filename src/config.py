"""Zentrale Pfade und Marken-Daten für das Berisa-Bau-Posting-System."""
from __future__ import annotations

import json
import os
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
__all__ = ["WURZEL"]

BRAND_DIR = WURZEL / "brand"
FONT_DIR = BRAND_DIR / "fonts"
TEMPLATE_DIR = WURZEL / "templates"
CONTENT_DIR = WURZEL / "content"
MEDIEN_DIR = CONTENT_DIR / "medien"
OUT_DIR = WURZEL / "out"
STATE_DATEI = WURZEL / "content" / "verlauf.json"
LOG_DATEI = WURZEL / "logs" / "posts.jsonl"

OUT_DIR.mkdir(exist_ok=True)
MEDIEN_DIR.mkdir(parents=True, exist_ok=True)


def _lade(pfad: Path) -> dict:
    with pfad.open(encoding="utf-8") as f:
        return json.load(f)


BRAND: dict = _lade(BRAND_DIR / "brand.json")
THEMEN: dict = _lade(CONTENT_DIR / "themen.json")
HASHTAGS: dict = _lade(CONTENT_DIR / "hashtags.json")

# Instagram-Zugang – wird aus Umgebungsvariablen bzw. .env gelesen.
IG_USER_ID = os.getenv("IG_USER_ID", "")
IG_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")

# graph.instagram.com = "Instagram API mit Instagram Login" – braucht keine
# Facebook-Seite. Wer den Weg über eine Facebook-Seite geht, trägt hier
# https://graph.facebook.com ein.
IG_HOST = os.getenv("IG_HOST", "https://graph.instagram.com").rstrip("/")
IG_API_VERSION = os.getenv("IG_API_VERSION", "v23.0")

# Eigene Sicherheitsgrenze. Metas Limit liegt höher, aber ein Ausreißer nach
# oben wäre bei diesem Konto immer ein Fehler, kein Feature.
MAX_POSTS_24H = int(os.getenv("MAX_POSTS_24H") or "5")

# --- Facebook-Seite (optional) -------------------------------------------- #
# Facebook-Seiten laufen immer über graph.facebook.com und brauchen einen
# eigenen Seiten-Token. Ohne diese beiden Werte bleibt Facebook einfach aus.
FB_PAGE_ID = os.getenv("FB_PAGE_ID", "")
FB_TOKEN = os.getenv("FB_PAGE_TOKEN", "")
FB_API_VERSION = os.getenv("FB_API_VERSION", "v23.0")

# --- Instagram über die Facebook-Seite ------------------------------------- #
# Instagram lässt sich auf zwei Wegen erreichen:
#   a) eigener Instagram-Token über graph.instagram.com
#   b) der Facebook-Seiten-Token über graph.facebook.com
#
# (b) ist der robustere Weg: ein Token weniger, der ablaufen kann, und er
# funktioniert ohne die zusätzliche Anmeldung in der Meta Business Suite.
# Am 29.08.2026 stellte sich heraus, dass (a) mit einem unbrauchbaren Token
# scheiterte ("Cannot parse access token"), während (b) dasselbe Konto
# problemlos erreichte.
#
# Ist IG_ACCESS_TOKEN leer, aber ein Seiten-Token vorhanden, wird automatisch
# auf (b) umgeschaltet. Erzwingen lässt sich das mit IG_UEBER_SEITE=1.
IG_UEBER_SEITE = (os.getenv("IG_UEBER_SEITE", "").strip() in ("1", "true", "ja")
                  or (not IG_TOKEN and bool(FB_TOKEN)))

if IG_UEBER_SEITE and FB_TOKEN:
    IG_TOKEN = FB_TOKEN
    IG_HOST = "https://graph.facebook.com"
    IG_API_VERSION = FB_API_VERSION

# --- Telegram-Freigabe (optional) ------------------------------------------ #
# Ohne beide Werte bleibt die Automatik wie bisher voll automatisch. Sind sie
# gesetzt, wartet die Veröffentlichung auf eine Freigabe per Tastendruck im
# Chat, statt direkt zu posten - siehe docs/04-TELEGRAM-EINRICHTEN.md.
# Eigener Bot (getrennt vom Ads-Bot unten), seit 28.08.2026.
TELEGRAM_BOT_TOKEN_SOCIAL = os.getenv("TELEGRAM_BOT_TOKEN_BERISABAUSOCIALMEDIA", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Google-Ads-Update-Kanal (optional, separater Telegram-Kanal) --------- #
# Eigener Bot (TELEGRAM_BOT_TOKEN, historischer Name) - die Instagram-Freigabe
# oben läuft seit 28.08.2026 über einen zweiten, eigenen Bot.
TELEGRAM_BOT_TOKEN_ADS = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID_ADS = os.getenv("TELEGRAM_CHAT_ID_ADS", "")

# Nur-lesender Zugang für den Dienstags-Kurzcheck und den Donnerstags-
# Optimierungsvorschlag. Dieselben Werte wie in google-ads-mcp/.env, hier
# als eigene Kopie, weil dieses Projekt separat in GitHub Actions läuft.
GOOGLE_ADS_DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "")
GOOGLE_ADS_CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID", "")
GOOGLE_ADS_CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET", "")
GOOGLE_ADS_REFRESH_TOKEN = os.getenv("GOOGLE_ADS_REFRESH_TOKEN", "")
GOOGLE_ADS_CUSTOMER_ID = os.getenv("GOOGLE_ADS_CUSTOMER_ID", "")
GOOGLE_ADS_LOGIN_CUSTOMER_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "")

ADS_VERLAUF_DATEI = CONTENT_DIR / "ads_verlauf.json"

# --- KI-Textautor (optional) ----------------------------------------------- #
# ChatGPT primaer (der Nutzer nennt es so und hat einen Schluessel), Claude
# als Ausweichoption. Ohne einen von beiden bleibt das Schreiben regelbasiert
# wie bisher - keine Funktion haengt zwingend an einem Schluessel.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Wenn true, postet die Automatik nur Themen, die vorher freigegeben wurden
# (siehe README, Abschnitt Freigabe). Standard: aus – volle Automatik.
FREIGABE_PFLICHT = os.getenv("FREIGABE_PFLICHT", "").lower() in ("1", "true", "ja")
# Öffentliche Basis-URL, unter der die gerenderten Bilder erreichbar sind
# (Instagram lädt das Bild selbst herunter – lokale Pfade funktionieren nicht).
MEDIA_BASE_URL = os.getenv("MEDIA_BASE_URL", "").rstrip("/")


def datei_url(pfad: Path) -> str:
    """Absolute file:///-URL, damit Chromium Schriften und Bilder findet."""
    return pfad.resolve().as_uri()
