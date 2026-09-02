"""Den Chat eines Twitch-VODs holen - ohne Fremdbibliothek.

Warum selbst gebaut: `chat-downloader` 0.2.8 scheitert an aufgezeichneten
Videos. Im Protokoll steht `'chat_type': 'live'` - die Bibliothek fragt für
ein VOD die Livechat-Schnittstelle ab, bekommt eine kurze Fehlerantwort und
wiederholt sie fünfzehnmal vergeblich. Die Fassung ist die neueste; das
Projekt hinkt also nicht sich selbst hinterher, sondern Twitch.

Dass der Weg gangbar ist, wurde vorher gemessen, nicht vermutet: dieselbe
Schnittstelle liefert mit derselben öffentlichen Kennung anstandslos Daten.

    POST https://gql.twitch.tv/gql
    {"query":"{ video(id: \\"2862735566\\") { id lengthSeconds } }"}
    -> HTTP 200
       {"data":{"video":{"id":"2862735566","lengthSeconds":9200}}}

Also wird genau dieser Weg benutzt: eine gewöhnliche GraphQL-Abfrage, keine
vorgemerkte Abfrage mit Prüfsumme, die bei jeder Twitch-Änderung bricht.

Geholt wird seitenweise über den Cursor, bis Twitch keine weitere Seite mehr
meldet. Herausgeschrieben wird das Format, das `quellen.lade_chat` ohnehin
liest - `content_offset_seconds` zählt ab Streambeginn, und genau darauf
beruht die ganze Zeitrechnung des Clip-Werks.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

GQL = "https://gql.twitch.tv/gql"

# Die öffentliche Web-Kennung von Twitch. Kein Geheimnis: sie steht in jeder
# Twitch-Seite im Quelltext und wird von jedem Werkzeug benutzt.
CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"

# Twitch gibt je Abfrage höchstens 100 Kommentare heraus.
SEITENGROESSE = 100


class TwitchFehler(RuntimeError):
    pass


def _abfrage(query: str, variables: dict | None = None) -> dict:
    rumpf = json.dumps({"query": query, "variables": variables or {}}).encode()
    anfrage = urllib.request.Request(
        GQL, data=rumpf,
        headers={"Client-ID": CLIENT_ID, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(anfrage, timeout=30) as antwort:
            daten = json.loads(antwort.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as fehler:
        text = fehler.read().decode("utf-8", "replace")[:400]
        raise TwitchFehler(f"HTTP {fehler.code} von Twitch: {text}") from None
    except urllib.error.URLError as fehler:
        raise TwitchFehler(f"Twitch nicht erreichbar: {fehler.reason}") from None

    # GraphQL antwortet auch bei Fehlern mit HTTP 200 - der Fehler steht im
    # Rumpf. Genau daran ist chat-downloader gescheitert.
    if "errors" in daten:
        meldungen = "; ".join(str(f.get("message", f))
                              for f in daten.get("errors", []))
        raise TwitchFehler(f"Twitch lehnt die Abfrage ab: {meldungen}")
    if "data" not in daten:
        raise TwitchFehler(f"Unerwartete Antwort ohne Daten: {str(daten)[:300]}")
    return daten["data"]


def video_info(vod: str) -> dict:
    """Titel, Länge und Kanal - auch als Gegenprobe, ob das VOD erreichbar ist."""
    daten = _abfrage(
        f"{{ video(id: {json.dumps(str(vod))}) {{ id title lengthSeconds "
        f"createdAt owner {{ displayName }} game {{ name }} }} }}")
    info = daten.get("video")
    if not info:
        raise TwitchFehler(
            f"Video {vod} nicht gefunden. Entweder ist die Nummer falsch, "
            f"oder die Aufzeichnung ist gelöscht bzw. nur für Abonnenten "
            f"sichtbar.")
    return info


# Bewusst ohne typisierte Variablen: die Argumente werden direkt in die
# Abfrage geschrieben. Sonst muesste hier der Typname des Cursors stehen
# ("Cursor", "String", ...), und den falsch zu raten kostet jedes Mal einen
# Lauf. Eingesetzt wird ueber json.dumps, damit die Zeichenkette sauber
# maskiert ist.
def _kommentar_abfrage(vod: str, cursor: str | None, offset: int) -> str:
    if cursor:
        argument = f"after: {json.dumps(cursor)}"
    else:
        argument = f"contentOffsetSeconds: {int(offset)}"
    return f"""
{{
  video(id: {json.dumps(str(vod))}) {{
    comments({argument}) {{
      edges {{
        cursor
        node {{
          contentOffsetSeconds
          commenter {{ displayName }}
          message {{ fragments {{ text }} }}
        }}
      }}
      pageInfo {{ hasNextPage }}
    }}
  }}
}}
"""


def _nachricht(knoten: dict) -> dict | None:
    text = "".join(t.get("text") or ""
                   for t in (knoten.get("message") or {}).get("fragments") or [])
    if not text.strip():
        return None
    schreiber = knoten.get("commenter") or {}
    return {
        "content_offset_seconds": knoten.get("contentOffsetSeconds", 0),
        "commenter": {"display_name": schreiber.get("displayName") or ""},
        "message": {"body": text.strip()},
    }


def hole_chat(vod: str, ziel: Path, melden=print) -> int:
    """Alle Chatnachrichten eines VODs holen und als JSON ablegen.

    Rückgabe ist die Anzahl der Nachrichten. Geschrieben wird erst am Ende,
    damit bei einem Abbruch keine halbe Datei liegen bleibt, die später als
    vollständig durchgeht.
    """
    info = video_info(vod)
    laenge = int(info.get("lengthSeconds") or 0)
    melden(f"Video {vod}: „{info.get('title', '?')}“ "
           f"({laenge // 3600}:{laenge % 3600 // 60:02d}:{laenge % 60:02d})")

    nachrichten: list[dict] = []
    cursor: str | None = None
    offset: int | None = 0
    seiten = 0

    while True:
        daten = _abfrage(_kommentar_abfrage(vod, cursor, offset or 0))
        block = ((daten.get("video") or {}).get("comments") or {})
        kanten = block.get("edges") or []
        if not kanten:
            break

        for kante in kanten:
            eintrag = _nachricht(kante.get("node") or {})
            if eintrag:
                nachrichten.append(eintrag)
            cursor = kante.get("cursor") or cursor

        seiten += 1
        if seiten % 20 == 0:
            letzte = nachrichten[-1]["content_offset_seconds"] if nachrichten else 0
            anteil = f" ({letzte / laenge * 100:.0f} %)" if laenge else ""
            melden(f"  {len(nachrichten)} Nachrichten, "
                   f"bei {int(letzte) // 60}:{int(letzte) % 60:02d}{anteil}")

        if not (block.get("pageInfo") or {}).get("hasNextPage"):
            break
        # Twitch mag keine Sturzflut. Eine kurze Pause kostet bei einem
        # Stream dieser Länge Sekunden und erspart abgewiesene Anfragen.
        time.sleep(0.05)

    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps({"comments": nachrichten}, ensure_ascii=False),
                    encoding="utf-8")
    melden(f"{len(nachrichten)} Nachrichten in {ziel.name}")
    return len(nachrichten)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import re
    import sys

    p = argparse.ArgumentParser(
        prog="clipwerk-twitch",
        description="Chat eines Twitch-VODs holen")
    p.add_argument("vod", help="Adresse oder Nummer des VODs")
    p.add_argument("--ziel", default="chat.json")
    args = p.parse_args(argv)

    treffer = re.search(r"/videos/(\d+)", args.vod)
    nummer = treffer.group(1) if treffer else args.vod.strip()
    if not nummer.isdigit():
        print(f"Keine Videonummer erkennbar in: {args.vod}", file=sys.stderr)
        return 2

    try:
        hole_chat(nummer, Path(args.ziel))
    except TwitchFehler as fehler:
        print(f"Abbruch: {fehler}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
