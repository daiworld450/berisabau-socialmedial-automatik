"""Legt einen kompletten Monat als durchsuchbaren Ordner ab.

Zweck: Der Betriebsinhaber soll den ganzen Monat abnehmen können, ohne Python,
ohne Instagram und ohne diese Sitzung – einfach den Ordner öffnen und die
Tabelle durchgehen. Deshalb liegen Bilder, Texte und Übersicht nebeneinander
und alle Verweise sind relativ.
"""
from __future__ import annotations

import csv
import html
import re
import shutil
from datetime import date
from pathlib import Path

import monatsplan
import texter
from config import BRAND, WURZEL
from renderer import rendere

SCHLAGWORT = re.compile(r"<b>(.*?)</b>:?\s*")


def _ohne_markup(text: str) -> str:
    return re.sub(r"<[^>]+>", "", str(text)).replace("  ", " ").strip()


def _dateiname(nr: int, eintrag: dict) -> str:
    return f"{nr:02d}_{eintrag['datum'].strftime('%Y-%m-%d')}_{eintrag['saeule_ist']}"


def _hashtags(eintrag: dict) -> str:
    """Die Hashtag-Zeile aus der fertigen Caption – letzte nichtleere Zeile."""
    zeilen = [z for z in eintrag["caption"].split("\n") if z.strip()]
    return zeilen[-1] if zeilen and zeilen[-1].startswith("#") else ""


def _text_ohne_hashtags(eintrag: dict) -> str:
    tags = _hashtags(eintrag)
    text = eintrag["caption"]
    return text.replace(tags, "").rstrip() if tags else text


def _text_ohne_hook(eintrag: dict) -> str:
    """Rumpftext ohne die erste Zeile – die steht in der Tabelle schon oben."""
    rest = _text_ohne_hashtags(eintrag).split("\n", 1)
    return rest[1].lstrip("\n") if len(rest) > 1 else ""


# --------------------------------------------------------------------------- #
def exportiere(jahr: int, monat: int, ziel: Path | None = None,
               bilder: bool = True) -> Path:
    eintraege = monatsplan.sammle(jahr, monat)
    name = f"{monatsplan.MONATE[monat - 1]}-{jahr}"
    ordner = Path(ziel) if ziel else (WURZEL / "monatspakete" / name)
    # Zwingend absolut: rendere() legt relative Ziele sonst unter out/ ab.
    if not ordner.is_absolute():
        ordner = WURZEL / ordner

    # Inhalt leeren statt den Ordner zu löschen: Unter Windows sperrt schon ein
    # geöffneter Explorer oder Browser-Tab das Verzeichnis, und ein Neuexport
    # während die Übersicht offen ist, ist der Normalfall.
    for unter in ("bilder", "texte"):
        pfad = ordner / unter
        if pfad.exists():
            for datei in pfad.iterdir():
                try:
                    datei.unlink()
                except OSError:
                    pass          # gesperrte Datei wird gleich überschrieben
        pfad.mkdir(parents=True, exist_ok=True)

    zeilen = []
    for nr, e in enumerate(eintraege, start=1):
        basis = _dateiname(nr, e)
        dateien: list[str] = []

        if bilder:
            if e["typ"] == "carousel":
                # Alle Slides – der Nutzer soll sehen, was beim Wischen kommt.
                for s_nr, slide in enumerate(e["slides"], start=1):
                    daten = {k: v for k, v in slide.items() if k != "vorlage"}
                    rendere(slide["vorlage"], daten,
                            ordner / "bilder" / f"{basis}_{s_nr:02d}.jpg")
                    dateien.append(f"bilder/{basis}_{s_nr:02d}.jpg")
            else:
                rendere(_vorlage_fuer(e), _felder_fuer(e),
                        ordner / "bilder" / f"{basis}.jpg")
                dateien.append(f"bilder/{basis}.jpg")

            if e["typ"] == "reel" and e["video"]:
                quelle = Path(e["video"])
                if quelle.exists():
                    shutil.copy2(quelle, ordner / "bilder" / f"{basis}{quelle.suffix}")
                    dateien.append(f"bilder/{basis}{quelle.suffix}")

        # Text einzeln ablegen – zum Kopieren, falls doch von Hand gepostet wird.
        (ordner / "texte" / f"{basis}.txt").write_text(
            e["caption"], encoding="utf-8")

        zeilen.append({**e, "nr": nr, "basis": basis,
                       "dateien": dateien or [f"bilder/{basis}.jpg"]})

    _schreibe_csv(ordner / "tabelle.csv", zeilen)
    (ordner / "UEBERSICHT.html").write_text(
        _html(jahr, monat, zeilen), encoding="utf-8")
    (ordner / "LIESMICH.txt").write_text(_liesmich(jahr, monat, zeilen),
                                         encoding="utf-8")
    return ordner


def _vorlage_fuer(eintrag: dict) -> str:
    from config import THEMEN
    treffer = next((t for t in THEMEN["themen"] if t["id"] == eintrag["id"]), None)
    return treffer["vorlage"] if treffer else "tipp.html"


def _felder_fuer(eintrag: dict) -> dict:
    from config import THEMEN
    treffer = next((t for t in THEMEN["themen"] if t["id"] == eintrag["id"]), None)
    if treffer:
        return dict(treffer["felder"], gewerk=treffer.get("gewerk", ""))
    return {}


# --------------------------------------------------------------------------- #
def _schreibe_csv(pfad: Path, zeilen: list[dict]) -> None:
    """UTF-8 mit BOM und Semikolon – so öffnet deutsches Excel es korrekt."""
    spalten = ["Nr", "Datum", "Wochentag", "Säule", "Beitragsart", "Medien",
               "Kennzeichen", "Gewerk", "Bild-Headline", "Unterzeile",
               "Stichpunkte", "Hook", "Text unter dem Beitrag", "Hashtags",
               "Zeichen", "Text für Facebook", "Foto nötig", "Dateien", "Thema-ID"]

    art = {"einzel": "Einzelbild", "carousel": "Carousel (wischen)",
           "reel": "Reel (Video)"}

    with pfad.open("w", encoding="utf-8-sig", newline="") as f:
        schreiber = csv.writer(f, delimiter=";", quoting=csv.QUOTE_ALL)
        schreiber.writerow(spalten)
        for z in zeilen:
            punkte = " | ".join(
                SCHLAGWORT.sub(lambda m: f"{m.group(1)}: ", p) for p in z["punkte"])
            schreiber.writerow([
                z["nr"],
                z["datum"].strftime("%d.%m.%Y"),
                z["wochentag"],
                z["saeule_ist"],
                art.get(z["typ"], z["typ"]),
                len(z["dateien"]),
                z["badge"],
                z["gewerk"],
                z["headline"],
                z["lead"] or _ohne_markup(z["antwort"]),
                punkte,
                z["hook"],
                _text_ohne_hashtags(z),
                _hashtags(z),
                z["zeichen"],
                texter.baue_caption_facebook(z["plan"]),
                "ja" if z["braucht_foto"] else "nein",
                " | ".join(z["dateien"]),
                z["id"],
            ])


# --------------------------------------------------------------------------- #
def _vorschau(z: dict) -> str:
    """Vorschauspalte: Einzelbild, alle Carousel-Slides oder Video."""
    stuecke = []
    videos = [d for d in z["dateien"] if d.lower().endswith((".mp4", ".mov"))]
    bilder = [d for d in z["dateien"] if d not in videos]

    for i, datei in enumerate(bilder, start=1):
        nummer = (f'<span class="slidenr">{i}/{len(bilder)}</span>'
                  if len(bilder) > 1 else "")
        stuecke.append(
            f'<a href="{datei}" target="_blank" class="vorschau">'
            f'<img src="{datei}" alt="" loading="lazy">{nummer}</a>')

    for datei in videos:
        stuecke.append(
            f'<video src="{datei}" controls preload="metadata" class="vorschau-video">'
            f'</video>')

    marke = ""
    if z["typ"] == "carousel":
        marke = f'<div class="typ">Carousel · {len(bilder)} Bilder · zum Wischen</div>'
    elif z["typ"] == "reel":
        marke = '<div class="typ">Reel · Video</div>'

    return marke + '<div class="slides">' + "".join(stuecke) + "</div>"


def _html(jahr: int, monat: int, zeilen: list[dict]) -> str:
    f = BRAND["firma"]
    esc = html.escape

    def zelle(z: dict) -> str:
        punkte = "".join(
            f"<li>{SCHLAGWORT.sub(lambda m: f'<b>{m.group(1)}:</b> ', p)}</li>"
            for p in z["punkte"])
        antwort = f'<div class="antwort">{z["antwort"]}</div>' if z["antwort"] else ""
        tags = _hashtags(z)
        return f"""
<tr data-saeule="{esc(z['saeule_ist'])}" data-foto="{'ja' if z['braucht_foto'] else 'nein'}">
  <td class="c-nr">{z['nr']}</td>
  <td class="c-datum">
    <b>{z['datum'].strftime('%d.%m.')}</b><br><span class="wt">{esc(z['wochentag'])}</span>
    <span class="pill p-{esc(z['saeule_ist'])}">{esc(z['saeule_ist'])}</span>
    {'<span class="foto">Foto nötig</span>' if z['braucht_foto'] else ''}
  </td>
  <td class="c-bild">
    {_vorschau(z)}
  </td>
  <td class="c-inhalt">
    <div class="headline">{esc(z['headline'])}</div>
    {f'<div class="lead">{esc(z["lead"])}</div>' if z['lead'] else ''}
    {antwort}
    {f'<ul class="punkte">{punkte}</ul>' if punkte else ''}
    <div class="meta">{esc(z['badge'])} · {esc(z['gewerk'])} · <code>{esc(z['id'])}</code></div>
  </td>
  <td class="c-text">
    <div class="hook">{esc(z['hook'])}</div>
    <pre>{esc(_text_ohne_hook(z))}</pre>
    <div class="tags">{esc(tags)}</div>
    <div class="meta">{z['zeichen']} von 2200 Zeichen</div>
  </td>
</tr>"""

    saeulen = sorted({z["saeule_ist"] for z in zeilen})
    knoepfe = "".join(
        f'<button data-filter="{s}">{s}</button>' for s in saeulen)
    fotos = sum(1 for z in zeilen if z["braucht_foto"])

    return f"""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Beitragsplan {monatsplan.MONATE[monat-1]} {jahr} · {esc(f['instagram'])}</title>
<style>
:root{{--rot:#D00000;--bg:#0B0B0F;--karte:#141419;--linie:#26262e;--text:#e8e8ea;--grau:#8f96a0}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);
 font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;padding:28px}}
header{{max-width:1600px;margin:0 auto 22px}}
h1{{font-size:26px;letter-spacing:-.3px;margin-bottom:4px}}
.sub{{color:var(--grau);font-size:14px}}
.leiste{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:20px 0 14px}}
.leiste button{{background:var(--karte);color:var(--text);border:1px solid var(--linie);
 border-radius:99px;padding:7px 16px;font-size:13px;cursor:pointer;font-family:inherit}}
.leiste button:hover{{border-color:#4a4a58}}
.leiste button.aktiv{{background:var(--rot);border-color:var(--rot);color:#fff}}
.leiste .zaehler{{margin-left:auto;color:var(--grau);font-size:13px}}
.hinweis{{max-width:1600px;margin:0 auto 18px;background:rgba(208,0,0,.09);
 border:1px solid rgba(208,0,0,.35);border-radius:10px;padding:13px 17px;font-size:14px}}
table{{width:100%;max-width:1600px;margin:0 auto;border-collapse:separate;border-spacing:0 8px}}
thead th{{text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:1.2px;
 color:var(--grau);padding:0 14px 8px;font-weight:600}}
tbody tr{{background:var(--karte);vertical-align:top}}
tbody tr.aus{{display:none}}
td{{padding:16px 14px;border-top:1px solid var(--linie);border-bottom:1px solid var(--linie)}}
td:first-child{{border-left:1px solid var(--linie);border-radius:10px 0 0 10px}}
td:last-child{{border-right:1px solid var(--linie);border-radius:0 10px 10px 0}}
.c-nr{{width:38px;color:var(--grau);font-variant-numeric:tabular-nums}}
.c-datum{{width:132px;font-size:14px}}
.c-datum .wt{{color:var(--grau);font-size:13px}}
.c-bild{{width:200px}}
.slides{{display:flex;flex-wrap:wrap;gap:6px}}
.vorschau{{position:relative;display:block}}
.vorschau img{{width:170px;border-radius:8px;display:block;border:1px solid var(--linie)}}
.slides .vorschau:nth-child(n+2) img{{width:81px}}
.slidenr{{position:absolute;right:5px;bottom:5px;background:rgba(0,0,0,.72);
 color:#fff;font-size:10.5px;padding:1px 6px;border-radius:99px}}
.vorschau-video{{width:170px;border-radius:8px;border:1px solid var(--linie)}}
.typ{{font-size:11.5px;color:#f7d493;margin-bottom:7px;letter-spacing:.3px}}
.c-inhalt{{width:31%}}
.pill{{display:inline-block;margin-top:8px;padding:2px 10px;border-radius:99px;
 background:#22222a;font-size:11px;text-transform:uppercase;letter-spacing:.8px}}
.p-fehler{{background:rgba(208,0,0,.25);color:#ff9b9b}}
.p-wissen{{background:rgba(16,50,207,.3);color:#a8b8ff}}
.p-mensch{{background:rgba(253,196,72,.22);color:#f7d493}}
.p-detail{{background:rgba(56,209,122,.2);color:#8ae4b4}}
.foto{{display:inline-block;margin-top:6px;font-size:11px;color:#f7d493;
 border:1px solid rgba(253,196,72,.4);border-radius:99px;padding:1px 9px}}
.headline{{font-size:17px;font-weight:650;line-height:1.3;margin-bottom:6px}}
.lead,.antwort{{color:#b9bfc7;font-size:14px;margin-bottom:9px}}
.punkte{{margin:0 0 9px 17px;font-size:13.5px;color:#c3c8cf}}
.punkte li{{margin-bottom:4px}}
.meta{{color:#6f7680;font-size:12px;margin-top:8px}}
code{{background:#22222a;padding:1px 6px;border-radius:5px;font-size:11.5px}}
.hook{{font-weight:650;margin-bottom:9px;font-size:14.5px}}
pre{{white-space:pre-wrap;font-family:inherit;font-size:13.5px;color:#c3c8cf;
 background:#0e0e13;border:1px solid var(--linie);border-radius:8px;padding:12px}}
.tags{{color:#7f95d6;font-size:12.5px;margin-top:9px;word-break:break-word}}
@media print{{body{{background:#fff;color:#000}}tbody tr{{background:#fff}}
 pre{{background:#f6f6f8;color:#000}}.leiste{{display:none}}}}
</style></head><body>
<header>
  <h1>Beitragsplan {monatsplan.MONATE[monat-1]} {jahr}</h1>
  <div class="sub">{esc(f['name'])} · {esc(f['instagram'])} · {len(zeilen)} Beiträge,
  zwei pro Woche · jeder Text geht genau so raus</div>
</header>

<div class="hinweis">
Bei <b>{fotos} Beiträgen</b> steht „Foto nötig“: Sie laufen aktuell als Textkachel.
Sobald eigene Bilder in <code>content/medien/</code> liegen, werden daraus
automatisch Bildbeiträge. Klick auf ein Vorschaubild öffnet es in Originalgröße.
</div>

<div class="leiste" style="max-width:1600px;margin-left:auto;margin-right:auto">
  <button data-filter="alle" class="aktiv">Alle</button>
  {knoepfe}
  <button data-filter="foto">Nur „Foto nötig“</button>
  <span class="zaehler" id="zaehler">{len(zeilen)} Beiträge</span>
</div>

<table>
<thead><tr>
  <th></th><th>Tag</th><th>Vorschau</th><th>Im Bild</th><th>Text unter dem Beitrag</th>
</tr></thead>
<tbody>{''.join(zelle(z) for z in zeilen)}</tbody>
</table>

<script>
const knoepfe = document.querySelectorAll('.leiste button');
const reihen  = document.querySelectorAll('tbody tr');
const zaehler = document.getElementById('zaehler');
knoepfe.forEach(b => b.addEventListener('click', () => {{
  knoepfe.forEach(x => x.classList.remove('aktiv'));
  b.classList.add('aktiv');
  const w = b.dataset.filter;
  let sichtbar = 0;
  reihen.forEach(r => {{
    const zeigen = w === 'alle'
      || (w === 'foto' ? r.dataset.foto === 'ja' : r.dataset.saeule === w);
    r.classList.toggle('aus', !zeigen);
    if (zeigen) sichtbar++;
  }});
  zaehler.textContent = sichtbar + (sichtbar === 1 ? ' Beitrag' : ' Beiträge');
}}));
</script>
</body></html>"""


# --------------------------------------------------------------------------- #
def _liesmich(jahr: int, monat: int, zeilen: list[dict]) -> str:
    fotos = sum(1 for z in zeilen if z["braucht_foto"])
    return f"""BEITRAGSPLAN {monatsplan.MONATE[monat - 1].upper()} {jahr}
{'=' * 60}

Was in diesem Ordner liegt:

  UEBERSICHT.html   Die Tabelle. Doppelklick genügt - sie öffnet sich im
                    Browser, mit Vorschaubild und vollständigem Text je Tag.
                    Oben lässt sich nach Säule filtern.

  tabelle.csv       Dieselben Daten für Excel oder LibreOffice.
                    Semikolon als Trennzeichen, UTF-8 - deutsches Excel
                    öffnet die Datei mit Doppelklick korrekt.

  bilder/           Die {len(zeilen)} fertigen Beitragsbilder, 1080 x 1350 Pixel,
                    JPEG. Benannt nach Reihenfolge, Datum und Säule.

  texte/            Der Text jedes Beitrags als einzelne Textdatei -
                    zum Kopieren, falls doch einmal von Hand gepostet wird.

{'=' * 60}

Stand: {len(zeilen)} Beiträge, zwei pro Woche.
Bei {fotos} davon steht "Foto nötig": Diese Tage laufen als Textkachel,
weil noch kein eigenes Bildmaterial vorliegt. Sobald Fotos unter
content/medien/ liegen, werden daraus automatisch Bildbeiträge -
am System muss dafür nichts geändert werden.

Die Texte sind final. Was hier steht, wird so veröffentlicht.

Änderungswünsche gehören in content/themen.json. Danach neu erzeugen mit:
  python src/main.py export --jahr {jahr} --monat {monat}
"""
