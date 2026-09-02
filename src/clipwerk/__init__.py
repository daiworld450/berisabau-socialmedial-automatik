"""Clip-Werk: aus einem Twitch-Stream werden TikToks, Reels und Shorts.

Das Paket setzt die Betriebsanweisung „Twitch → TikTok / Reels Content
Engine" um (content/CLIP-PROMPT.md). Der Weg durch die Module entspricht
den Abschnitten der Anweisung:

    quellen    Stream einlesen (Transkript, Chat)              Abschnitt 1
    signale    Interessenkurve über den ganzen Stream          Abschnitt 1
    kandidaten Fenster schneiden, Stille entfernen             Abschnitt 3, 4
    bewertung  100-Punkte-Maßstab, Schwelle 65 / 80            Abschnitt 2
    kategorien zwölf Kategorien, Hashtags, Serienformate       Abschnitt 9
    untertitel 3-7 Wörter, ASS/SRT                             Abschnitt 7
    schnitt    Schnittplan und Bildaufteilung                  Abschnitt 5, 6, 8
    texte      Hook, Titel, Captions                           Abschnitt 4, 10
    render     ffmpeg-Befehl für 1080x1920                     Abschnitt 6
    verlauf    Clip-Datenbank gegen Doppelungen                Abschnitt 13
    plan       Veröffentlichungsrhythmus                       Abschnitt 12
    lernkurve  Auswahl an echter Leistung nachziehen           Abschnitt 14
    wachstum   Was der Kanal daraus lernen soll                Abschnitt 11
    motor      hält die Kette zusammen
    ausgabe    Markdown und JSON nach Abschnitt 10

Das Paket hängt bewusst an keiner der übrigen Module dieses Repos: es
bringt seine eigenen Pfade mit und lässt sich einzeln kopieren.
"""
from __future__ import annotations

from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent.parent
CONTENT = WURZEL / "content"
AUSGABE = WURZEL / "out" / "clips"

LEXIKON_DATEI = CONTENT / "clip_lexikon.json"
HASHTAG_DATEI = CONTENT / "clip_hashtags.json"
VERLAUF_DATEI = CONTENT / "clip_verlauf.json"
PROMPT_DATEI = CONTENT / "CLIP-PROMPT.md"

__all__ = ["WURZEL", "CONTENT", "AUSGABE", "LEXIKON_DATEI", "HASHTAG_DATEI",
           "VERLAUF_DATEI", "PROMPT_DATEI"]
