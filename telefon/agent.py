"""Die Gesprächsschleife: Ohr -> Kopf -> Stimme, in einem Rutsch.

Aufbau (Pipecat):

    Twilio-WebSocket -> Silero-VAD -> Deepgram (Sprache zu Text)
      -> Widerspruchswächter -> GPT (Antwort) -> ElevenLabs (Stimme)
      -> Twilio-WebSocket

Der Widerspruchswächter sitzt mit Absicht VOR dem Sprachmodell. Er liest
jeden erkannten Satz und bricht selbst ab, wenn jemand nicht angerufen
werden will - unabhängig davon, ob das Modell sein Werkzeug aufruft. Ein
Sprachmodell, das eine Anweisung übergeht, ist ein Alltagsfall; ein zweiter
Anruf nach einem Widerspruch ist ein Rechtsfall.

Zur Latenz: Deepgram und ElevenLabs laufen im Streaming-Betrieb, das
Sprachmodell antwortet ebenfalls im Strom. Der erste Ton kommt dadurch,
bevor der Satz zu Ende gedacht ist. Wer hier ein größeres Modell einsetzt
oder auf nicht-strömende Dienste wechselt, verliert genau das Gefühl, um
das es geht.

Die Importpfade von Pipecat haben sich zwischen den Fassungen mehrfach
verschoben (pipecat.services.elevenlabs war früher pipecat.services.
elevenlabs_tts). Die Fassung ist in requirements.txt festgenagelt; nach
einem Upgrade zuerst hier schauen.
"""
from __future__ import annotations

import asyncio
import logging

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (EndTaskFrame, Frame, TranscriptionFrame,
                                   TTSSpeakFrame)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams, FastAPIWebsocketTransport)

import einstellungen as e
import gespraech
import protokoll
import sperrliste

log = logging.getLogger(__name__)


class WiderspruchsWaechter(FrameProcessor):
    """Liest mit und zieht die Notbremse, bevor das Modell überhaupt denkt."""

    def __init__(self, nummer: str, beenden) -> None:
        super().__init__()
        self.nummer = nummer
        self._beenden = beenden
        self.mitschrift: list[str] = []
        self.ausgeloest = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame) and frame.text:
            self.mitschrift.append(frame.text)
            if not self.ausgeloest and gespraech.ist_widerspruch(frame.text):
                self.ausgeloest = True
                log.warning("Widerspruch erkannt: %r", frame.text)
                # Der Satz geht nicht weiter an das Modell. Stattdessen ein
                # fester Abschlusssatz und auflegen.
                await self.push_frame(
                    TTSSpeakFrame("Verstanden, ich trage Sie aus und rufe "
                                  "nicht wieder an. Entschuldigen Sie die "
                                  "Störung. Auf Wiederhören."),
                    FrameDirection.DOWNSTREAM,
                )
                await self._beenden("widerspruch", frame.text)
                return

        await self.push_frame(frame, direction)


class Gespraechslauf:
    """Ein Telefonat von der Begrüßung bis zum Auflegen."""

    def __init__(self, nummer: str, kontakt: dict | None = None) -> None:
        self.nummer = nummer
        self.kontakt = kontakt or {}
        self.ergebnis = "unbekannt"
        self.notiz: dict = {}
        self.waechter: WiderspruchsWaechter | None = None
        self._task: PipelineTask | None = None

    # --- Werkzeuge, die das Sprachmodell aufrufen kann -------------------- #

    async def _nicht_mehr_anrufen(self, params) -> None:
        grund = (params.arguments or {}).get("grund", "ohne Angabe")
        sperrliste.sperren(self.nummer, grund, "gespraech")
        self.ergebnis = "gesperrt"
        await params.result_callback({"status": "gesperrt"})
        await self._auflegen()

    async def _gespraech_beenden(self, params) -> None:
        argumente = params.arguments or {}
        self.ergebnis = argumente.get("grund", "beendet")
        self.notiz = argumente
        await params.result_callback({"status": "beendet"})
        await self._auflegen()

    async def _termin_notieren(self, params) -> None:
        self.notiz = params.arguments or {}
        self.ergebnis = "termin"
        await params.result_callback({"status": "notiert"})

    async def _auflegen(self, ergebnis: str | None = None,
                        text: str | None = None) -> None:
        if ergebnis:
            self.ergebnis = ergebnis
        if text:
            self.notiz.setdefault("wortlaut", text)
        if self._task is not None:
            # EndTaskFrame läuft durch die Pipeline, damit der bereits
            # erzeugte Abschlusssatz noch zu Ende gesprochen wird. Ein
            # sofortiges cancel() würde ihn mitten im Wort abschneiden.
            await self._task.queue_frame(EndTaskFrame())

    # --- Aufbau ----------------------------------------------------------- #

    def _sprachmodell(self) -> OpenAILLMService:
        llm = OpenAILLMService(api_key=e.OPENAI_KEY, model=e.LLM_MODELL)
        llm.register_function("nicht_mehr_anrufen", self._nicht_mehr_anrufen)
        llm.register_function("gespraech_beenden", self._gespraech_beenden)
        llm.register_function("termin_notieren", self._termin_notieren)
        return llm

    @staticmethod
    def _werkzeugschema() -> ToolsSchema:
        return ToolsSchema(standard_tools=[
            FunctionSchema(
                name=w["function"]["name"],
                description=w["function"]["description"],
                properties=w["function"]["parameters"]["properties"],
                required=w["function"]["parameters"].get("required", []),
            )
            for w in gespraech.werkzeuge()
        ])

    async def fuehren(self, websocket, stream_sid: str, call_sid: str) -> str:
        """Läuft, bis aufgelegt wird. Gibt das Ergebnis zurück."""
        serializer = TwilioFrameSerializer(
            stream_sid=stream_sid,
            call_sid=call_sid,
            account_sid=e.TWILIO_SID,
            auth_token=e.TWILIO_TOKEN,
        )
        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                add_wav_header=False,
                # stop_secs ist die Stellschraube für das Gesprächsgefühl:
                # zu kurz und die KI fällt ins Wort, zu lang und sie wirkt
                # schwerfällig. 0,5 s ist für deutsche Sprecher ein guter
                # Ausgangswert.
                vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.5)),
                serializer=serializer,
            ),
        )

        stt = DeepgramSTTService(
            api_key=e.DEEPGRAM_KEY,
            live_options={"model": "nova-2-phonecall", "language": "de",
                          "smart_format": True, "interim_results": True},
        )
        tts = ElevenLabsTTSService(
            api_key=e.ELEVENLABS_KEY,
            voice_id=e.ELEVENLABS_STIMME,
            model=e.ELEVENLABS_MODELL,
            # 8 kHz ist die Telefonbandbreite; höher zu rechnen kostet nur
            # Zeit, weil Twilio ohnehin herunterrechnet.
            sample_rate=8000,
        )
        llm = self._sprachmodell()

        kontext = OpenAILLMContext(
            messages=[{"role": "system",
                       "content": gespraech.systemprompt(self.kontakt)}],
            tools=self._werkzeugschema(),
        )
        aggregator = llm.create_context_aggregator(kontext)
        self.waechter = WiderspruchsWaechter(self.nummer, self._auflegen)

        pipeline = Pipeline([
            transport.input(),
            stt,
            self.waechter,
            aggregator.user(),
            llm,
            tts,
            transport.output(),
            aggregator.assistant(),
        ])

        self._task = PipelineTask(
            pipeline,
            params=PipelineParams(audio_in_sample_rate=8000,
                                  audio_out_sample_rate=8000,
                                  allow_interruptions=True),
        )

        @transport.event_handler("on_client_connected")
        async def _begruessen(_transport, _client):
            # Die Offenlegung wird gesprochen, nicht vom Modell erzeugt.
            # Ein Modell, das den Satz umformuliert, könnte den Hinweis
            # verlieren - und genau der ist die Pflicht aus Art. 50 KI-VO.
            await self._task.queue_frame(TTSSpeakFrame(gespraech.EROEFFNUNG))
            protokoll.eintragen(self.nummer, ereignis="offenlegung",
                                call_sid=call_sid, wortlaut=gespraech.EROEFFNUNG)

        @transport.event_handler("on_client_disconnected")
        async def _aufgelegt(_transport, _client):
            await self._task.cancel()

        runner = PipelineRunner(handle_sigint=False)
        try:
            await asyncio.wait_for(runner.run(self._task),
                                   timeout=e.MAX_GESPRAECHSDAUER)
        except asyncio.TimeoutError:
            # Ein Akquisegespräch, das die Obergrenze reißt, ist entgleist.
            log.warning("Gespräch %s nach %ss abgebrochen", call_sid,
                        e.MAX_GESPRAECHSDAUER)
            self.ergebnis = "zeitueberschreitung"
            await self._task.cancel()

        protokoll.eintragen(
            self.nummer,
            ereignis="gespraech_ende",
            call_sid=call_sid,
            ergebnis=self.ergebnis,
            notiz=self.notiz,
            mitschrift=self.waechter.mitschrift if self.waechter else [],
        )
        return self.ergebnis
