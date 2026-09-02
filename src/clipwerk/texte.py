"""Hook, Titel, Captions und Hashtags - Abschnitt 4, 10 und 12.

Der wichtigste Satz in Abschnitt 4 ist der letzte: **kein irreführender
Clickbait.** Ein Hook, der etwas verspricht, was im Clip nicht vorkommt,
holt einmal Views und kostet danach dauerhaft Reichweite, weil die Leute
sofort wegwischen.

Technisch durchgesetzt wird das so: jeder Hook hat eine Bedingung, die im
gemessenen Signal erfüllt sein muss. „Chat ist komplett eskaliert" darf nur
stehen, wenn der Chat im Clip messbar ausschlägt. Ist keine Bedingung
erfüllt, gewinnt der Rückfall - ein Hook aus dem tatsächlich gesagten Satz.
Der kann nie falsch sein, weil er zitiert.

Die Captions sind kurz. Abschnitt 10 sagt „keine langen Marketingtexte",
und auf TikTok verdeckt eine dritte Zeile ohnehin das Bild.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import kategorien as kat
from .bewertung import Bewertung
from .kandidaten import Kandidat

TIKTOK_TITEL_MAX = 60
YOUTUBE_TITEL_MAX = 68
CAPTION_MAX = 150

_FUELLER = re.compile(
    r"^(also|und|ähm|äh|öhm|ja|so|dann|aber|halt|ne|nee|okay|ok)\b[\s,]*", re.I)


@dataclass
class Texte:
    hook: str
    tiktok_titel: str
    tiktok_caption: str
    instagram_caption: str
    youtube_titel: str
    hashtags: list[str] = field(default_factory=list)
    kernzitat: str = ""


# --------------------------------------------------------------------------- #
# Bausteine aus dem tatsächlichen Inhalt
# --------------------------------------------------------------------------- #
def _traegt(satz: str) -> bool:
    """Steht der Satz für sich, oder ist er Zwischenrede?

    Ein Titel aus „ich mach mal weiter" ist schlimmer als gar kein Titel:
    er sagt dem Zuschauer im Vorbeiscrollen, dass hier nichts kommt.
    """
    from .kandidaten import _FUELLWOERTER
    from .verlauf import STOPP
    woerter = [re.sub(r"[^\wäöüßÄÖÜ]+", "", w).lower() for w in satz.split()]
    inhalt = [w for w in woerter
              if w and len(w) > 3 and w not in _FUELLWOERTER and w not in STOPP]
    return len(inhalt) >= 2


def _satzanfang(text: str) -> bool:
    """Fängt dieser Text am Satzanfang an - soweit man das sehen kann?

    Vorsichtig formuliert, weil nicht jedes Transkript Großschreibung
    kennt: ein durchgehend kleingeschriebener Text sagt nichts über
    Satzgrenzen aus, dort wird nicht bestraft. Steht dagegen anderswo im
    Satz ein Großbuchstabe und am Anfang ein kleiner, ist der Anfang
    abgeschnitten.
    """
    text = text.strip()
    if not text:
        return False
    if text[:1].isupper():
        return True
    return not any(z.isupper() for z in text)


def kernzitat(kandidat: Kandidat, hoechstens: int = 12) -> str:
    """Der Satz, der dem Höhepunkt am nächsten liegt und für sich steht.

    Nur daraus dürfen Titel gebaut werden. Alles andere wäre eine Behauptung
    über den Clip statt eines Auszugs aus ihm.
    """
    # Zwei Durchgänge, und der erste gewinnt: ein Zitat, das am Satzanfang
    # beginnt, schlägt jedes, das mitten im Satz einsetzt - auch wenn das
    # näher am Höhepunkt liegt. „das mein rechter Fuß" ist kein Zitat,
    # sondern ein Stück von einem.
    ganz, bruch = ("", 1e9), ("", 1e9)
    for segment in kandidat.segmente:
        for satz in re.split(r"(?<=[.!?])\s+", segment.text.strip()):
            satz = _FUELLER.sub("", satz).strip(" ,.:;–-")
            woerter = satz.split()
            if not 3 <= len(woerter) <= hoechstens:
                continue
            if not _traegt(satz):
                continue
            abstand = abs(segment.start - kandidat.hoehepunkt)
            ziel = "ganz" if _satzanfang(satz) else "bruch"
            if ziel == "ganz" and abstand < ganz[1]:
                ganz = (satz, abstand)
            elif ziel == "bruch" and abstand < bruch[1]:
                bruch = (satz, abstand)
    if ganz[0]:
        return ganz[0]
    if bruch[0]:
        return bruch[0]
    # Notfall: die ersten Wörter des Clips, gekürzt.
    woerter = kandidat.text.split()[:hoechstens]
    return " ".join(woerter).strip(" ,.–-")


def _kuerze(text: str, grenze: int) -> str:
    text = text.strip()
    if len(text) <= grenze:
        return text
    geschnitten = text[:grenze].rsplit(" ", 1)[0].rstrip(" ,.–-")
    return geschnitten + "…"


# --------------------------------------------------------------------------- #
# Hook
# --------------------------------------------------------------------------- #
# (Bedingung, Schwelle, Fassungen). Die Bedingung prüft das gemessene
# Signal, nicht die Kategorie allein - sonst stünde über jedem RAGE-Clip
# derselbe Satz.
#
# Mehrere Fassungen je Signal, weil ein Stream nicht einen solchen Moment
# hat, sondern zwanzig. Am echten Stream 2862735566 trug ein Signal allein
# 18 von 30 Clips - mit einem einzigen Satz je Signal stand über fünf
# davon wortgleich „Seine Reaktion sagt alles 😂". Fünf Beiträge mit
# demselben Aufmacher lesen sich als Fließband, und genau das ist das
# Gegenteil von dem, wofür jemand folgt.
_HOOKS: list[tuple[str, float, list[str]]] = [
    ("chat_clipruf", 0.8, [
        "Der Chat wollte genau das als Clip 💀",
        "Der Chat hat selbst nach dem Clip gerufen.",
        "Das wollte der Chat sofort gespeichert haben 💀"]),
    ("chat_lachen", 2.0, [
        "Er hat sich nicht mehr eingekriegt 😂",
        "Danach ging eine Minute lang nichts mehr 😂",
        "Der Lacher kam aus dem Nichts 😂"]),
    ("chat_wut", 1.5, [
        "Chat ist komplett eskaliert 💀",
        "Der Chat ist danach durchgedreht 💀",
        "Zwei Sekunden später stand der Chat still 💀"]),
    ("chat_streit", 1.5, [
        "Der Chat war danach gespalten.",
        "Halber Chat dafür, halber dagegen.",
        "Darüber hat der Chat sich zerlegt."]),
    ("chat_schock", 1.5, [
        "Damit hat wirklich niemand gerechnet 💀",
        "Der Chat war für einen Moment still 💀",
        "Das kam für alle aus dem Nichts 💀"]),
    ("sprache_wut", 1.5, [
        "Er wusste sofort, dass er einen Fehler gemacht hat.",
        "Da ist ihm der Kragen geplatzt.",
        "Man hört genau, wann es kippt."]),
    ("sprache_ueberraschung", 1.2, [
        "Seine Reaktion sagt alles 😂",
        "Er hat zweimal hinsehen müssen.",
        "Damit hatte er nicht gerechnet.",
        "Guck auf die Sekunde, in der es klickt.",
        "Er braucht kurz, bis er es glaubt."]),
    ("sprache_fail", 1.2, [
        "Eine Sekunde später war alles vorbei 💀",
        "Es ging genau so schief, wie es klingt 💀",
        "Das hätte er sich sparen können 💀"]),
    ("sprache_meinung", 1.2, [
        "Das hätte er besser nicht gesagt…",
        "Er sagt es, wie er es sieht.",
        "Da legt er sich fest."]),
    ("sprache_story", 1.0, [
        "Warte bis zum Ende 😂",
        "Die Geschichte geht anders aus, als du denkst.",
        "Er erzählt es, als wäre es gestern gewesen."]),
    ("sprache_chatbezug", 1.0, [
        "Er hätte den Chat nicht lesen sollen.",
        "Er antwortet dem Chat direkt.",
        "Die Frage aus dem Chat hat gesessen."]),
]


def hook(kandidat: Kandidat, note: Bewertung,
         benutzt: set[str] | None = None) -> str:
    """Der Aufmacher über dem Video.

    `benutzt` sammelt, was in diesem Lauf schon dranstand. Ist jede
    Fassung eines Signals vergeben, wird nach der Startzeit gewählt - das
    ist zwar eine Wiederholung, aber eine berechenbare: derselbe Stream
    ergibt zweimal denselben Bericht.
    """
    for reihe, schwelle, fassungen in _HOOKS:
        if kandidat.anteile.get(reihe, 0.0) < schwelle:
            continue
        frei = [s for s in fassungen if not benutzt or s not in benutzt]
        satz = (frei[0] if frei
                else fassungen[int(kandidat.start) % len(fassungen)])
        if benutzt is not None:
            benutzt.add(satz)
        return satz
    # Kein Signal stark genug für eine Behauptung: dann zitieren wir.
    # Ein Zitat kann nie falsch sein, und es wiederholt sich von selbst
    # nicht - deshalb steht es hier nicht unter der Wiederholungssperre.
    zitat = kernzitat(kandidat, hoechstens=8)
    if zitat:
        return f"„{_kuerze(zitat, 52)}“"
    muster = kat.KATEGORIEN[note.kategorie].hook_muster
    return muster[0] if muster else "Guck bis zum Ende."


# --------------------------------------------------------------------------- #
# Titel und Captions
# --------------------------------------------------------------------------- #
_CAPTION_JE_KATEGORIE = {
    "FUNNY": "Er kriegt sich nicht mehr ein.",
    "RAGE": "Der Moment, in dem es kippt.",
    "REACTION": "Guck auf sein Gesicht.",
    "STORY": "Die Geschichte musste raus.",
    "CONTROVERSIAL": "Ihr dürft das gern anders sehen.",
    "GAMING": "Kein Zufall.",
    "FAIL": "Tat beim Zusehen weh.",
    "WIN": "Vorher angekündigt, danach geliefert.",
    "CHAT MOMENT": "Chat hat wieder gewonnen.",
    "HOT TAKE": "Sagt sonst keiner laut.",
    "UNEXPECTED": "Und dann kam das.",
    "CLIP / MEME": "Kein Kontext nötig.",
}

_FRAGE_JE_KATEGORIE = {
    "CONTROVERSIAL": "Wie seht ihr das?",
    "HOT TAKE": "Hat er recht oder nicht?",
    "CHAT MOMENT": "Team Chat oder Team Streamer?",
    "RAGE": "Wer wäre auch ausgerastet?",
    "FAIL": "Wer kennt's?",
    "STORY": "Sowas schon mal erlebt?",
}


def baue(kandidat: Kandidat, note: Bewertung, streamer: str, spiel: str,
         hashtag_saetze: dict, hashtag_anzahl: int = 7,
         benutzte_hooks: set[str] | None = None) -> Texte:
    zitat = kernzitat(kandidat)
    text_hook = hook(kandidat, note, benutzte_hooks)

    titel_kern = _kuerze(zitat, TIKTOK_TITEL_MAX - 2) if zitat else text_hook
    tiktok_titel = _kuerze(f"„{titel_kern}“" if zitat else titel_kern,
                           TIKTOK_TITEL_MAX)

    grundsatz = _CAPTION_JE_KATEGORIE.get(note.kategorie, "Ohne Worte.")
    tiktok_caption = _kuerze(grundsatz, CAPTION_MAX)

    # Instagram: eine Spur mehr Kontext, weil Reels häufiger von Leuten
    # gesehen werden, die den Streamer nicht kennen. Und eine Frage, wo sie
    # zur Kategorie passt - Kommentare sind dort das knappere Gut.
    frage = _FRAGE_JE_KATEGORIE.get(note.kategorie, "")
    instagram = grundsatz
    if streamer and streamer.lower() not in instagram.lower():
        instagram = f"{streamer} live auf Twitch. {grundsatz}"
    if frage:
        instagram = f"{instagram} {frage}"
    instagram_caption = _kuerze(instagram, CAPTION_MAX)

    # YouTube Shorts: der Titel ist dort das Vorschaubild. Kategorie voran,
    # damit die Suche etwas zu greifen hat.
    youtube_roh = f"{streamer}: {titel_kern}" if streamer else titel_kern
    youtube_titel = _kuerze(youtube_roh, YOUTUBE_TITEL_MAX)

    return Texte(
        hook=text_hook,
        tiktok_titel=tiktok_titel,
        tiktok_caption=tiktok_caption,
        instagram_caption=instagram_caption,
        youtube_titel=youtube_titel,
        hashtags=kat.hashtags(note.kategorie, streamer, spiel, hashtag_saetze,
                              hashtag_anzahl),
        kernzitat=zitat,
    )


def variante(texte: Texte, plattform: str) -> str:
    """Leicht abgewandelter Hook fürs Crossposting (Abschnitt 12).

    Derselbe Clip darf auf drei Plattformen laufen, aber nicht mit
    identischem Text: TikTok und Instagram teilen sich Zuschauer, und zwei
    wortgleiche Posts nebeneinander sehen nach Bot aus.
    """
    if plattform == "instagram":
        return texte.hook.replace("💀", "😳") if "💀" in texte.hook else texte.hook
    if plattform == "youtube":
        ohne_emoji = re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "",
                            texte.hook).strip()
        return ohne_emoji or texte.hook
    return texte.hook
