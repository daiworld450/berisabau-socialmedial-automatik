#!/usr/bin/env python3
"""Dauerhaften Seiten-Schluessel fuer Facebook und Instagram hinterlegen.

Warum es das gibt (03.09.2026):
Der Beitrag "m-werkzeug" ging auf Instagram raus und wurde von Facebook
abgelehnt. Gemessen: dem Schluessel fehlte pages_manage_posts. Ursache lag
in der Meta-App - die Berechtigung war dem Anwendungsfall "Seiten verwalten"
nie zugeordnet. Das ist behoben.

Warum ueber einen Systemnutzer und nicht ueber den Anmeldedialog:
Ein Schluessel aus dem gewoehnlichen Anmeldedialog gilt ein bis zwei
Stunden. Dauerhaft wird er nur durch einen Tausch mit dem App-Geheimnis -
und das steht im Entwicklerportal, das am 03.09. minutenlang nicht lud.
Der Schluessel eines Systemnutzers laeuft dagegen gar nicht ab und braucht
kein Geheimnis. Der Systemnutzer "Berisa Bau Automatik" ist im
Business-Portfolio bereits angelegt und darf im Namen der Seite posten.

Der Schluessel wird verdeckt eingegeben, geprueft und direkt hinterlegt.
Er steht in keiner Datei und in keiner Ausgabe.
"""
from __future__ import annotations

import json
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

APP_ID = "1406251358268303"
REPO = "daiworld450/berisabau-socialmedial-automatik"
GRAPH = "https://graph.facebook.com/v21.0"
BUSINESS_ID = "773601795845727"
SYSTEMNUTZER_SEITE = (
    "https://business.facebook.com/latest/settings/system_users"
    f"?business_id={BUSINESS_ID}&selected_user_id=61593731331461"
)

# Instagram laeuft ueber denselben Schluessel (Variable IG_UEBER_SEITE=1).
# Fehlen hier die beiden Instagram-Rechte, steht nach dem Hinterlegen auch
# Instagram still - der Kanal, der bisher als einziger lief.
NOETIG = {
    "pages_show_list": "Seiten sehen",
    "pages_read_engagement": "Seite lesen",
    "pages_manage_posts": "auf der Seite posten",
    "instagram_basic": "Instagram lesen",
    "instagram_content_publish": "auf Instagram posten",
}


class GraphFehler(Exception):
    """Facebook hat abgelehnt - mit dem Klartext von Facebook.

    Ohne das steht beim Nutzer nur "HTTP Error 400: Bad Request".
    """


def graph(pfad: str, **werte) -> dict:
    adresse = f"{GRAPH}/{pfad}?" + urllib.parse.urlencode(werte)
    try:
        with urllib.request.urlopen(adresse, context=ssl.create_default_context(),
                                    timeout=30) as antwort:
            return json.loads(antwort.read().decode("utf-8"))
    except urllib.error.HTTPError as fehler:
        try:
            inhalt = json.loads(fehler.read().decode("utf-8"))
            raise GraphFehler(inhalt.get("error", {}).get("message")
                              or f"Facebook antwortete mit {fehler.code}") from None
        except (ValueError, AttributeError):
            raise GraphFehler(f"Facebook antwortete mit {fehler.code}") from None
    except OSError as fehler:
        raise GraphFehler(f"Keine Verbindung zu Facebook ({fehler})") from None


def sag(text: str = "") -> None:
    print(text, flush=True)


def anleitung() -> None:
    sag("")
    sag("Im Browser oeffnet sich die Seite mit dem Systemnutzer")
    sag("\"Berisa Bau Automatik\". Dort:")
    sag("")
    sag("  1. Rechts oben auf  Token generieren  klicken.")
    sag("  2. Als App  Berisa Bau Posting  auswaehlen.")
    sag("  3. Ablaufdatum:  Nie  (steht meist schon so).")
    sag("  4. Diese fuenf Haken setzen:")
    for name, zweck in NOETIG.items():
        sag(f"        {name:<28} ({zweck})")
    sag("  5. Auf  Token generieren  klicken und den langen")
    sag("     Schluessel kopieren.")
    sag("")


def hole_schluessel() -> str:
    sag("Schluessel hier einfuegen. Beim Einfuegen bleibt die Zeile")
    sag("leer - das ist richtig so. Cmd+V, dann Eingabetaste.")
    try:
        import getpass
        wert = getpass.getpass("Schluessel: ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""
    if wert:
        sag(f"  {len(wert)} Zeichen angekommen.")
    return wert


def pruefe(token: str) -> dict:
    """Was der eingegebene Schluessel taugt - gemessen, nicht vermutet."""
    daten = graph("debug_token", input_token=token, access_token=token).get("data", {})
    return {
        "gueltig": bool(daten.get("is_valid")),
        "unbefristet": (daten.get("expires_at") or 0) == 0,
        "rechte": set(daten.get("scopes") or []),
        "typ": daten.get("type", ""),
    }


def main() -> int:
    sag("")
    sag("Es geht um einen Schluessel, der nicht mehr ablaeuft.")
    sag("Der bisherige Weg lieferte nur Schluessel fuer eine Stunde.")
    anleitung()
    webbrowser.open(SYSTEMNUTZER_SEITE)

    token = hole_schluessel()
    if not token:
        sag("\nNichts eingegeben. Nichts geaendert.\n")
        return 1

    sag("")
    sag("Pruefe den Schluessel bei Facebook ...")
    try:
        befund = pruefe(token)
    except GraphFehler as fehler:
        sag(f"\nFacebook lehnt ihn ab: {fehler}")
        sag("Nichts geaendert.\n")
        return 1

    if not befund["gueltig"]:
        sag("\nDieser Schluessel gilt nicht. Nichts geaendert.\n")
        return 1

    fehlt = [r for r in NOETIG if r not in befund["rechte"]]
    if fehlt:
        sag("")
        sag("Diesem Schluessel fehlen Berechtigungen:")
        for r in fehlt:
            sag(f"    {r:<28} ({NOETIG[r]})")
        sag("")
        sag("Ohne sie faellt der jeweilige Kanal aus. Noch einmal")
        sag("erzeugen und diesmal alle fuenf Haken setzen.")
        sag("Nichts geaendert.")
        sag("")
        return 1
    sag("  Alle noetigen Berechtigungen sind dabei.")

    if not befund["unbefristet"]:
        sag("")
        sag("Dieser Schluessel hat ein Ablaufdatum - dann waere in ein paar")
        sag("Wochen wieder Schluss. Beim Erzeugen bei Ablaufdatum  Nie")
        sag("auswaehlen. Nichts geaendert.")
        sag("")
        return 1
    sag("  Er laeuft nicht ab.")

    sag("Hole den Schluessel der Seite ...")
    try:
        seiten = graph("me/accounts", access_token=token).get("data") or []
    except GraphFehler as fehler:
        sag(f"\nFEHLER: {fehler}\nNichts geaendert.\n")
        return 1

    if not seiten:
        sag("\nZu diesem Schluessel gehoert keine Seite. Ist die Seite dem")
        sag("Systemnutzer zugewiesen? Nichts geaendert.\n")
        return 1

    wahl = next((s for s in seiten if "berisa" in (s.get("name") or "").lower()),
                seiten[0] if len(seiten) == 1 else None)
    if wahl is None:
        sag("\nMehrere Seiten gefunden:")
        for i, s in enumerate(seiten):
            sag(f"   {i}  {s.get('name')}")
        try:
            wahl = seiten[int(input("\n   Nummer der Seite Berisa Bau: ").strip())]
        except (ValueError, IndexError):
            sag("\nKeine gueltige Auswahl. Nichts geaendert.\n")
            return 1

    seiten_token = wahl.get("access_token", "")
    if not seiten_token:
        sag(f"\nFuer {wahl.get('name')} kam kein Seiten-Schluessel zurueck.")
        sag("Nichts geaendert.\n")
        return 1
    sag(f"  Seite: {wahl.get('name')}")

    # Auch den Seiten-Schluessel messen, nicht annehmen: er erbt die
    # Haltbarkeit vom Systemnutzer-Schluessel, aber geprueft ist besser
    # als geglaubt - genau daran ist der Versuch um 20:27 gescheitert.
    try:
        seiten_befund = pruefe(seiten_token)
    except GraphFehler as fehler:
        sag(f"\nFEHLER beim Pruefen des Seiten-Schluessels: {fehler}")
        sag("Nichts geaendert.\n")
        return 1

    if not seiten_befund["unbefristet"]:
        sag("\nDer Seiten-Schluessel hat trotzdem ein Ablaufdatum.")
        sag("Nichts geaendert - sag Claude Bescheid.\n")
        return 1
    sag("  Auch der Seiten-Schluessel laeuft nicht ab.")

    fehlt2 = [r for r in NOETIG if r not in seiten_befund["rechte"]]
    if fehlt2:
        sag("\nDem Seiten-Schluessel fehlen: " + ", ".join(fehlt2))
        sag("Nichts geaendert - sag Claude Bescheid.\n")
        return 1

    sag("")
    sag("Hinterlege ihn in GitHub ...")
    fertig = subprocess.run(["gh", "secret", "set", "FB_PAGE_TOKEN", "-R", REPO],
                            input=seiten_token, text=True, capture_output=True)
    del seiten_token, token
    if fertig.returncode != 0:
        sag(f"\nFEHLER: {fertig.stderr.strip()}\n")
        return 1

    sag("  Erledigt.")
    sag("")
    sag("  Haltbarkeit: unbefristet. Facebook und Instagram laufen")
    sag("  ab jetzt beide ueber diesen Schluessel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
