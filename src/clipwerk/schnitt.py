"""Schnittplan und Bildaufteilung - Abschnitt 5, 6 und 8.

Der Plan ist bewusst eine Liste knapper Anweisungen mit Zeitmarken, keine
Prosa. Er geht so, wie er ist, in die Schnittsoftware oder an `render.py`.

Die Anweisungen entstehen aus dem, was gemessen wurde, nicht aus einem
festen Muster: der Punch-In sitzt auf dem Höhepunkt der Signalkurve, die
Jump Cuts sitzen auf den Auslassungen, die Chat-Einblendung sitzt dort, wo
der Chat tatsächlich ausschlägt. Ein Effektregen ohne Anlass fällt damit
weg - Abschnitt 5, letzter Satz: die Person bleibt Mittelpunkt.

Zeiten sind Clip-Zeiten (nach Herausrechnen der Stille), nicht Streamzeiten.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .bewertung import Bewertung
from .kandidaten import Kandidat
from .quellen import Stream
from .signale import Signalkurve

# Bildaufteilungen nach Abschnitt 6. 1080x1920, Facecam nie kleiner als ein
# Drittel der Höhe - darunter erkennt auf dem Handy niemand ein Gesicht.
LAYOUTS = {
    "vollbild": "Gameplay formatfüllend beschnitten, Hintergrund unscharf gedoppelt",
    "geteilt": "Facecam oben (1080×760), Gameplay unten (1080×1160)",
    "facecam_gross": "Gameplay als Hintergrund, Facecam groß im oberen Drittel",
    "nur_person": "Nur die Facecam, formatfüllend – für reine Wortclips",
}

# Welche Kategorie welche Aufteilung braucht, wenn nichts vorgegeben ist.
_LAYOUT_JE_KATEGORIE = {
    "GAMING": "geteilt",
    "WIN": "geteilt",
    "FAIL": "geteilt",
    "RAGE": "facecam_gross",
    "REACTION": "facecam_gross",
    "FUNNY": "facecam_gross",
    "STORY": "nur_person",
    "HOT TAKE": "nur_person",
    "CONTROVERSIAL": "nur_person",
    "CHAT MOMENT": "facecam_gross",
    "UNEXPECTED": "facecam_gross",
    "CLIP / MEME": "vollbild",
}


@dataclass
class Anweisung:
    von: float
    bis: float
    text: str

    def zeile(self) -> str:
        def mmss(wert: float) -> str:
            minute, sek = divmod(int(wert), 60)
            return f"{minute}:{sek:02d}"
        if self.bis - self.von < 0.3:
            return f"{mmss(self.von)} {self.text}"
        return f"{mmss(self.von)}–{mmss(self.bis)} {self.text}"


@dataclass
class Schnittplan:
    layout: str
    anweisungen: list[Anweisung] = field(default_factory=list)
    loop: bool = False
    loop_hinweis: str = ""

    def als_text(self) -> str:
        zeilen = [a.zeile() for a in self.anweisungen]
        if self.loop:
            zeilen.append(f"Loop: {self.loop_hinweis}")
        return "\n".join(zeilen)


def waehle_layout(kategorie: str, hat_facecam: bool, vorgabe: str = "") -> str:
    if vorgabe:
        if vorgabe not in LAYOUTS:
            raise ValueError(f"unbekanntes Layout: {vorgabe} "
                             f"(erlaubt: {', '.join(LAYOUTS)})")
        return vorgabe
    gewuenscht = _LAYOUT_JE_KATEGORIE.get(kategorie, "geteilt")
    if not hat_facecam:
        return "vollbild"
    return gewuenscht


def _chat_momente(kandidat: Kandidat, kurve: Signalkurve,
                  hoechstens: int = 2) -> list[float]:
    """Sekunden im Clip, an denen der Chat am deutlichsten ausschlägt."""
    treffer: list[tuple[float, float]] = []
    schritt = max(1.0, kurve.aufloesung)
    zeit = kandidat.start
    while zeit < kandidat.ende:
        if not kandidat.in_auslassung(zeit):
            wert = kurve.spitzenwert("chat_menge", zeit, zeit + schritt)
            if wert > 1.2:
                treffer.append((wert, zeit))
        zeit += schritt
    treffer.sort(reverse=True)
    gewaehlt: list[float] = []
    for _, zeit in treffer:
        if all(abs(zeit - fest) > 4.0 for fest in gewaehlt):
            gewaehlt.append(zeit)
        if len(gewaehlt) >= hoechstens:
            break
    return sorted(gewaehlt)


def _haeufigste(nachrichten, hoechstens: int = 3) -> str:
    """Die meistwiederholten Chatzeilen eines Ausschnitts, als Zitat."""
    from collections import Counter
    zaehler = Counter(n.text.strip()[:40] for n in nachrichten if n.text.strip())
    return " · ".join(f"„{text}“ ×{anzahl}" if anzahl > 1 else f"„{text}“"
                      for text, anzahl in zaehler.most_common(hoechstens))


def _looptauglich(kandidat: Kandidat, note: Bewertung) -> tuple[bool, str]:
    """Abschnitt 8: passt das Ende an den Anfang?

    Zwei Fälle tragen wirklich. Erstens die offene Frage am Ende - der
    Zuschauer springt zurück, um den Anfang noch einmal zu hören. Zweitens
    der kurze Clip unter 20 Sekunden: da läuft der Loop ohnehin, bevor
    jemand wegwischt, und ein weicher Übergang macht daraus Rewatches.
    """
    text = kandidat.text.strip()
    if text.endswith("?"):
        return True, ("letzte Zeile stehen lassen, hart auf Bild 1 zurück – "
                      "die Frage am Ende schickt den Zuschauer an den Anfang")
    if kandidat.dauer <= 20.0 and note.punkte >= 75:
        return True, ("letzte 0,4 s auf den Anfangsframe blenden, Ton hart "
                      "schneiden – der Clip läuft dann rund")
    return False, ""


def plane(kandidat: Kandidat, note: Bewertung, kurve: Signalkurve,
          stream: Stream, layout_vorgabe: str = "",
          hat_facecam: bool = True) -> Schnittplan:
    layout = waehle_layout(note.kategorie, hat_facecam, layout_vorgabe)
    plan = Schnittplan(layout=layout)
    hoehepunkt = kandidat.clipzeit(kandidat.hoehepunkt)
    ende = kandidat.dauer

    # 1. Einstieg: die ersten zwei Sekunden gehören dem Gesicht bzw. dem
    #    Text-Hook. Bei schwachem Einstieg wird härter herangefahren.
    if note.hook < 16:
        plan.anweisungen.append(Anweisung(
            0.0, 1.8, "harter Punch-In auf das Gesicht, Text-Hook ab Bild 1, "
                      "kein Vorlauf"))
    else:
        plan.anweisungen.append(Anweisung(
            0.0, 2.0, "Gesicht groß, Text-Hook einblenden"))

    # 2. Aufbau bis zum Höhepunkt läuft im gewählten Layout.
    if hoehepunkt > 2.5:
        plan.anweisungen.append(Anweisung(
            2.0, max(2.5, hoehepunkt - 0.6),
            f"Originalausschnitt im Layout „{layout}“"))

    # 3. Jump Cuts an den Auslassungen.
    for von, bis in kandidat.auslassungen:
        marke = kandidat.clipzeit(von)
        if 0.5 < marke < ende - 0.5:
            plan.anweisungen.append(Anweisung(
                marke, marke, f"Jump Cut – {bis - von:.1f} s Stille raus"))

    # 4. Der Höhepunkt selbst.
    plan.anweisungen.append(Anweisung(
        max(0.0, hoehepunkt - 0.4), min(ende, hoehepunkt + 1.6),
        "Reaktions-Punch-In auf das Gesicht, Ton eine Spur lauter"))
    if note.kategorie in ("FAIL", "UNEXPECTED", "CLIP / MEME"):
        plan.anweisungen.append(Anweisung(
            min(ende, hoehepunkt + 0.2), min(ende, hoehepunkt + 0.5),
            "kurzer Freeze Frame (0,3 s) auf dem Gesichtsausdruck"))

    # 5. Chat nur dort einblenden, wo er wirklich ausschlägt. Gezeigt wird,
    #    was am häufigsten kam - eine Einblendung soll die Stimmung des
    #    Chats zeigen, nicht die schnellste Nachricht.
    letzte_einblendung = 0.0
    for zeit in _chat_momente(kandidat, kurve):
        marke = kandidat.clipzeit(zeit)
        zitat = _haeufigste(stream.chat_zwischen(zeit, zeit + 2.5))
        plan.anweisungen.append(Anweisung(
            marke, min(ende, marke + 2.2),
            f"Chat einblenden{': ' + zitat if zitat else ''}"))
        letzte_einblendung = min(ende, marke + 2.2)

    # 6. Ausklang - erst nach der letzten Einblendung, sonst steht im Plan
    #    eine Anweisung über einer anderen.
    ausklang = max(hoehepunkt + 1.6, letzte_einblendung)
    if ende - ausklang > 2.0:
        plan.anweisungen.append(Anweisung(
            min(ende, ausklang), ende,
            "zurück auf Normalgröße, letzte Zeile ausspielen"))

    plan.anweisungen.sort(key=lambda a: (a.von, a.bis))
    plan.loop, plan.loop_hinweis = _looptauglich(kandidat, note)
    return plan
