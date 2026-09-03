#!/usr/bin/env python3
"""Facebook-Seiten-Schluessel erneuern, ohne ihn irgendwo abzutippen.

Warum es das gibt (Befund vom 03.09.2026):
Der Beitrag "m-werkzeug" ging auf Instagram raus und wurde von Facebook
abgelehnt. Gemessen wurde danach, welche Berechtigungen der hinterlegte
Schluessel wirklich traegt - es fehlte genau eine: pages_manage_posts.
Der Grund lag in der App: die Berechtigung war dem Anwendungsfall
"Seiten verwalten" nie hinzugefuegt worden. Das ist seither erledigt,
der alte Schluessel traegt sie aber nicht nachtraeglich.

Wie es funktioniert:
Das Skript macht kurz einen kleinen Webserver auf dem eigenen Rechner auf
(127.0.0.1:8765) und schickt den Browser zum Anmeldedialog von Facebook.
Nach dem Erlauben schickt Facebook den Schluessel an genau diesen Server
zurueck. Er wandert also direkt von Facebook in dieses Skript - niemand
muss ihn kopieren, er steht in keiner Datei und in keiner Ausgabe.

Angelegt am 03.09.2026.
"""
from __future__ import annotations

import http.server
import json
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

APP_ID = "1406251358268303"
REPO = "daiworld450/berisabau-socialmedial-automatik"
PORT = 8765
GRAPH = "https://graph.facebook.com/v21.0"

# business_management steckt mit drin, weil der bisherige Schluessel sie
# ebenfalls trug - ohne sie faende /me/accounts unter Umstaenden weniger
# Seiten als vorher.
RECHTE = [
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "instagram_basic",
    "instagram_content_publish",
    "business_management",
]

SEITE = """<!doctype html><html lang="de"><meta charset="utf-8">
<title>Facebook-Anmeldung</title>
<style>
 body{font:16px/1.6 -apple-system,BlinkMacSystemFont,sans-serif;
      max-width:34rem;margin:14vh auto;padding:0 1.5rem;color:#1c1e21}
 h1{font-size:1.4rem;margin:0 0 .6rem}
 .ok{color:#1a7f37} .fehler{color:#a40e26}
 p{margin:.4rem 0}
</style>
<h1 id="kopf">Einen Moment …</h1>
<p id="text">Der Schlüssel wird an dein Skript übergeben.</p>
<script>
// Facebook haengt den Schluessel hinter das Rautezeichen. Dieser Teil der
// Adresse wird nie an einen Server geschickt - deshalb liest ihn diese
// Seite selbst aus und reicht ihn an den lokalen Server weiter.
(function () {
  var h = new URLSearchParams(location.hash.slice(1));
  var s = new URLSearchParams(location.search);
  var kopf = document.getElementById("kopf");
  var text = document.getElementById("text");
  var token = h.get("access_token");
  var fehler = h.get("error") || s.get("error");
  var ziel = "/uebergabe?" + (token ? "access_token=" + encodeURIComponent(token)
                                    : "error=" + encodeURIComponent(fehler || "unbekannt"));
  fetch(ziel).then(function () {
    if (token) {
      kopf.textContent = "Fertig.";
      kopf.className = "ok";
      text.textContent = "Du kannst dieses Fenster schließen und zum Terminal zurückgehen.";
    } else {
      kopf.textContent = "Abgebrochen.";
      kopf.className = "fehler";
      text.textContent = "Es wurde nichts geändert. Zurück zum Terminal.";
    }
  });
})();
</script>
</html>"""

_ergebnis: dict = {}
_fertig = threading.Event()


class Empfaenger(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        pfad = urllib.parse.urlparse(self.path)
        if pfad.path == "/uebergabe":
            werte = urllib.parse.parse_qs(pfad.query)
            _ergebnis["token"] = (werte.get("access_token") or [""])[0]
            _ergebnis["fehler"] = (werte.get("error") or [""])[0]
            self.send_response(204)
            self.end_headers()
            _fertig.set()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(SEITE.encode("utf-8"))

    def log_message(self, *_):  # Serverprotokoll unterdruecken
        pass


class GraphFehler(Exception):
    """Facebook hat die Anfrage abgelehnt - mit dem Klartext von Facebook.

    Ohne das steht beim Nutzer nur "HTTP Error 400: Bad Request", und damit
    kann niemand etwas anfangen. Die eigentliche Begruendung steckt im
    Antworttext, den urllib bei einem Fehlercode nicht mitliefert.
    """


def graph(pfad: str, **werte) -> dict:
    adresse = f"{GRAPH}/{pfad}?" + urllib.parse.urlencode(werte)
    kontext = ssl.create_default_context()
    try:
        with urllib.request.urlopen(adresse, context=kontext, timeout=30) as antwort:
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


def main() -> int:
    # Direkt binden statt vorher zu pruefen: ein eigener Testsocket ohne
    # SO_REUSEADDR scheitert an der Wartezeit, die das Betriebssystem nach
    # jedem Lauf auf dem Anschluss haelt - das Skript liesse sich dann kein
    # zweites Mal hintereinander starten. HTTPServer setzt die Option selbst.
    try:
        server = http.server.HTTPServer(("127.0.0.1", PORT), Empfaenger)
    except OSError as fehler:
        sag(f"\nFEHLER: Anschluss {PORT} liess sich nicht oeffnen ({fehler}).")
        sag("Laeuft dieses Skript vielleicht schon in einem anderen Fenster?\n")
        return 1
    threading.Thread(target=server.serve_forever, daemon=True).start()

    dialog = "https://www.facebook.com/v21.0/dialog/oauth?" + urllib.parse.urlencode({
        "client_id": APP_ID,
        "redirect_uri": f"http://localhost:{PORT}/",
        "response_type": "token",
        "scope": ",".join(RECHTE),
        # Ohne dies ueberspringt Facebook den Dialog, wenn schon einmal
        # erlaubt wurde - und liefert wieder einen Schluessel ohne die neue
        # Berechtigung. Genau der Fehler, der hier behoben werden soll.
        "auth_type": "rerequest",
    })

    sag("")
    sag("Im Browser oeffnet sich jetzt der Facebook-Dialog.")
    sag("Dort auf Weiter klicken, die Seite Berisa Bau auswaehlen")
    sag("und bestaetigen. Mehr ist nicht zu tun.")
    sag("")
    sag("Warte auf die Bestaetigung im Browser ...")
    webbrowser.open(dialog)

    if not _fertig.wait(timeout=300):
        sag("\nNach fuenf Minuten kam nichts zurueck. Nichts geaendert.\n")
        return 1
    server.shutdown()

    token = _ergebnis.get("token", "")
    if not token:
        grund = _ergebnis.get("fehler") or "abgebrochen"
        sag(f"\nAbgebrochen ({grund}). Nichts geaendert.\n")
        return 1

    sag("Schluessel angekommen. Pruefe ihn bei Facebook ...")
    try:
        befund = graph("debug_token", input_token=token, access_token=token)
    except Exception as fehler:                       # noqa: BLE001
        sag(f"\nFEHLER beim Pruefen: {fehler}\nNichts geaendert.\n")
        return 1

    daten = befund.get("data", {})
    rechte = daten.get("scopes") or []
    if "pages_manage_posts" not in rechte:
        sag("")
        sag("Der neue Schluessel traegt pages_manage_posts NICHT.")
        sag("Damit wuerde Facebook genauso ablehnen wie bisher.")
        sag("Im Dialog muss die Seite Berisa Bau ausgewaehlt und die")
        sag("Berechtigung zum Veroeffentlichen bestaetigt sein.")
        sag("Nichts geaendert.")
        sag("")
        return 1
    sag("  pages_manage_posts ist dabei.")

    sag("Hole den Schluessel der Seite ...")
    try:
        seiten = (graph("me/accounts", access_token=token).get("data") or [])
    except Exception as fehler:                       # noqa: BLE001
        sag(f"\nFEHLER: {fehler}\nNichts geaendert.\n")
        return 1

    if not seiten:
        sag("\nZu diesem Zugang gehoert keine Seite. Bist du Administrator")
        sag("der Facebook-Seite Berisa Bau? Nichts geaendert.\n")
        return 1

    wahl = next((s for s in seiten if "berisa" in (s.get("name") or "").lower()), None)
    if wahl is None:
        if len(seiten) == 1:
            wahl = seiten[0]
        else:
            sag("\nDu verwaltest mehrere Seiten:")
            for i, s in enumerate(seiten):
                sag(f"   {i}  {s.get('name')}")
            try:
                wahl = seiten[int(input("\n   Nummer der Seite Berisa Bau: ").strip())]
            except (ValueError, IndexError):
                sag("\nKeine gueltige Auswahl. Nichts geaendert.\n")
                return 1
    seiten_token = wahl.get("access_token", "")
    if not seiten_token:
        sag("\nFacebook hat fuer diese Seite keinen Schluessel geliefert.")
        sag("Nichts geaendert.\n")
        return 1
    sag(f"  Seite: {wahl.get('name')}")

    # Ein Schluessel aus diesem Dialog gilt nur ein bis zwei Stunden. Damit
    # die Automatik nicht heute Abend wieder steht, wird er mit dem
    # App-Geheimnis in einen dauerhaften getauscht. Das Geheimnis wird nur
    # in diesem Moment benutzt und nirgends gespeichert.
    sag("")
    sag("-----------------------------------------------------------")
    sag("  Noch ein Schritt - der wichtigste")
    sag("-----------------------------------------------------------")
    sag("")
    sag("Ein Schluessel aus diesem Dialog gilt nur rund eine Stunde.")
    sag("Danach steht Facebook wieder still, waehrend Instagram")
    sag("weiterlaeuft - genau der Zustand vom 03.09.")
    sag("")
    sag("Damit das ein fuer alle Mal erledigt ist, braucht es einmal")
    sag("das App-Geheimnis. Es oeffnet sich gleich die Seite, auf der")
    sag("es steht - dort auf Anzeigen klicken, kopieren, hier einfuegen.")
    sag("Es wird nicht angezeigt und nirgends gespeichert.")
    sag("")
    sag("Nur Eingabetaste geht auch, ist aber eine Notloesung fuer")
    sag("heute: der Beitrag geht raus, in einer Stunde ist Schluss.")
    sag("-----------------------------------------------------------")
    webbrowser.open(f"https://developers.facebook.com/apps/{APP_ID}/settings/basic/")
    try:
        import getpass
        geheim = getpass.getpass("App-Geheimnis (wird nicht angezeigt): ").strip()
    except (EOFError, KeyboardInterrupt):
        geheim = ""

    if geheim:
        try:
            lang = graph("oauth/access_token",
                         grant_type="fb_exchange_token",
                         client_id=APP_ID, client_secret=geheim,
                         fb_exchange_token=token).get("access_token", "")
            if not lang:
                raise GraphFehler("Facebook lieferte keinen Schluessel zurueck")
            seiten_neu = (graph("me/accounts", access_token=lang).get("data") or [])
            treffer = next((s for s in seiten_neu
                            if s.get("id") == wahl.get("id")), None)
            if treffer and treffer.get("access_token"):
                seiten_token = treffer["access_token"]
        except GraphFehler as fehler:
            sag(f"  Tausch fehlgeschlagen: {fehler}")
            sag("  Steht auf der Seite wirklich das App-Geheimnis und nicht")
            sag("  die App-Nummer? Es wird der kurzlebige Schluessel")
            sag("  hinterlegt - der Beitrag geht heute raus.")
        finally:
            del geheim

    # Nicht behaupten, sondern messen: Facebook selbst fragen, wie lange
    # der Schluessel gilt, der gleich hinterlegt wird. "expires_at 0" heisst
    # unbefristet - alles andere ist eine Notloesung mit Ablaufdatum.
    dauerhaft = False
    rest = None
    try:
        pruefung = graph("debug_token", input_token=seiten_token,
                         access_token=seiten_token).get("data", {})
        ablauf = pruefung.get("expires_at") or 0
        dauerhaft = ablauf == 0
        if not dauerhaft:
            rest = max(0, int((ablauf - time.time()) // 60))
    except GraphFehler:
        pass

    sag("")
    sag("Hinterlege den Schluessel in GitHub ...")
    fertig = subprocess.run(["gh", "secret", "set", "FB_PAGE_TOKEN", "-R", REPO],
                            input=seiten_token, text=True, capture_output=True)
    del seiten_token
    if fertig.returncode != 0:
        sag(f"\nFEHLER: {fertig.stderr.strip()}\n")
        return 1
    sag("  Erledigt.")
    sag("")
    if dauerhaft:
        sag("  Haltbarkeit: unbefristet. Damit ist Facebook abgeschlossen.")
        sag("  Ein Waechter sieht jeden Morgen nach und meldet sich ueber")
        sag("  Telegram, falls doch einmal etwas klemmt.")
        return 0

    sag("  ACHTUNG - Haltbarkeit: " + (f"noch rund {rest} Minuten."
                                       if rest is not None else "nur kurz."))
    sag("")
    sag("  Der Beitrag geht gleich raus, aber danach faellt Facebook")
    sag("  wieder aus. Fuer die Dauerloesung dieses Skript noch einmal")
    sag("  starten und diesmal das App-Geheimnis einfuegen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
