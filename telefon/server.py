"""Der Server, den Twilio anruft.

Vier Endpunkte:
  POST /twiml       - Twilio fragt: "Was soll ich mit diesem Anruf machen?"
                      Antwort: verbinde den Ton mit unserem WebSocket.
  WS   /medien      - der Tonstrom in beide Richtungen. Hier läuft das Gespräch.
  POST /status      - Twilio meldet das Ende: besetzt, keine Annahme, Dauer.
  GET  /gesundheit  - für die Überwachung.

Warum ein eigener Server und kein GitHub Actions wie beim Rest des Projekts:
Ein Telefongespräch ist eine offene Verbindung. Actions-Läufe sind kurz und
haben keine öffentliche Adresse, unter der Twilio sie erreichen könnte.
Der Server läuft dauerhaft (Railway, Fly.io, Hetzner - egal was, Hauptsache
eine feste HTTPS-Adresse mit gültigem Zertifikat).
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

import einstellungen as e
import protokoll
from agent import Gespraechslauf

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("telefon.server")

app = FastAPI(title="Berisa Telefonagent")

# Kontaktdaten, die der Wähler vor dem Anruf hinterlegt, damit das Gespräch
# weiß, wen es anruft. Schlüssel ist die Twilio-Anruf-ID.
_laufende: dict[str, dict] = {}


def kontakt_hinterlegen(call_sid: str, kontakt: dict) -> None:
    _laufende[call_sid] = kontakt


@app.get("/gesundheit")
async def gesundheit() -> JSONResponse:
    fehlt = e.fehlende_zugaenge()
    return JSONResponse(
        {"bereit": not fehlt, "fehlende_zugaenge": fehlt,
         "laufende_gespraeche": len(_laufende)},
        status_code=200 if not fehlt else 503,
    )


@app.post("/twiml")
async def twiml(request: Request) -> Response:
    """Verbindet den Anruf mit dem WebSocket.

    <Connect><Stream> ist die zweiseitige Variante - <Start><Stream> würde
    nur mithören, ohne dass wir sprechen können.
    """
    formular = await request.form()
    call_sid = formular.get("CallSid", "")
    nummer = formular.get("To", "")
    wss = (e.OEFFENTLICHE_URL
           .replace("https://", "wss://")
           .replace("http://", "ws://"))

    log.info("TwiML für %s an %s", call_sid, nummer)
    antwort = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               "<Response>\n"
               "  <Connect>\n"
               f'    <Stream url="{wss}/medien" />\n'
               "  </Connect>\n"
               "</Response>")
    return Response(content=antwort, media_type="application/xml")


@app.websocket("/medien")
async def medien(websocket: WebSocket) -> None:
    await websocket.accept()

    # Twilio schickt zuerst "connected", dann "start" mit den Kennungen.
    # Beide müssen gelesen werden, bevor der Serializer gebaut wird.
    try:
        await websocket.receive_json()          # connected
        start = await websocket.receive_json()  # start
    except (WebSocketDisconnect, ValueError):
        log.warning("Medienstrom vor dem Start abgebrochen")
        return

    daten = start.get("start", {})
    stream_sid = daten.get("streamSid", "")
    call_sid = daten.get("callSid", "")
    kontakt = _laufende.get(call_sid, {})
    nummer = kontakt.get(
        "nummer", daten.get("customParameters", {}).get("nummer", ""))

    log.info("Gespräch beginnt: %s -> %s", call_sid, nummer)
    lauf = Gespraechslauf(nummer, kontakt)
    try:
        ergebnis = await lauf.fuehren(websocket, stream_sid, call_sid)
        log.info("Gespräch %s beendet: %s", call_sid, ergebnis)
    except Exception as fehler:            # noqa: BLE001 - nichts still schlucken
        log.exception("Gespräch %s abgestürzt", call_sid)
        protokoll.eintragen(nummer, ereignis="fehler", call_sid=call_sid,
                            fehler=str(fehler))
    finally:
        _laufende.pop(call_sid, None)


@app.post("/status")
async def status(CallSid: str = Form(""), CallStatus: str = Form(""),
                 To: str = Form(""), CallDuration: str = Form(""),
                 AnsweredBy: str = Form("")) -> Response:
    """Twilios Schlussmeldung - auch für Anrufe, die nie ein Gespräch wurden.

    AnsweredBy stammt aus Twilios Anrufbeantworter-Erkennung. Ein
    aufgesprochener Werbetext auf einer Mailbox ist rechtlich derselbe
    Werbeanruf, nur ohne die Möglichkeit, sofort Nein zu sagen - deshalb
    wird er hier nur protokolliert, nie erzeugt.
    """
    protokoll.eintragen(To, ereignis="anrufende", call_sid=CallSid,
                        status=CallStatus, dauer=CallDuration,
                        angenommen_von=AnsweredBy or "unbekannt")
    _laufende.pop(CallSid, None)
    return Response(status_code=204)


def starten() -> None:
    import uvicorn
    fehlt = e.fehlende_zugaenge()
    if fehlt:
        raise SystemExit("Es fehlen Zugänge: " + ", ".join(fehlt))
    uvicorn.run(app, host="0.0.0.0", port=e.SERVER_PORT)


if __name__ == "__main__":
    starten()
