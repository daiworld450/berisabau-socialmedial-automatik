"""Erzeugt den Redaktionsplan für einen Monat – mit allen Texten und Begründungen.

Zweck: Der Betriebsinhaber soll vor dem ersten automatischen Post sehen können,
was an welchem Tag mit welcher Absicht erscheint. Ohne die Bilder einzeln
durchklicken zu müssen und ohne Instagram-Zugang.
"""
from __future__ import annotations

import html
import json
import re
from calendar import monthrange
from datetime import date

import planer
import texter
from config import BRAND, HASHTAGS, OUT_DIR, THEMEN

WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
              "Freitag", "Samstag", "Sonntag"]
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]

# Warum diese Säule an diesem Wochentag steht.
SAEULEN_ZWECK = {
    "vorher-nachher": (
        "Stärkster Reichweitentreiber der Branche. Der Vergleich funktioniert "
        "ohne Text und wird überdurchschnittlich oft geteilt."),
    "detail": (
        "Zeigt Qualität ohne ein Wort Werbung. Wer ein Detail erklärt bekommt, "
        "kann es beim nächsten Angebot selbst prüfen – das schafft Vertrauen."),
    "wissen": (
        "Beantwortet eine Frage, die Kunden tatsächlich stellen. Wissensposts "
        "werden gespeichert und wieder hervorgeholt, wenn die Sanierung ansteht."),
    "fehler": (
        "Höchste Kommentarrate, deshalb sparsam eingesetzt. Wer Pfusch erkennt, "
        "sucht danach einen Betrieb, der es besser macht."),
    "mensch": (
        "Baut Vertrauen vor der Anfrage auf. Menschen beauftragen Menschen, "
        "nicht Firmenlogos."),
}

FOTO_NOETIG = {"vorher-nachher", "detail", "mensch"}

# <b>Schlagwort</b> Rest  ->  **Schlagwort:** Rest
SCHLAGWORT = re.compile(r"<b>(.*?)</b>:?\s*")


def _kopfzeile(felder: dict) -> str:
    kopf = "".join(str(felder.get(k, ""))
                   for k in ("titel_vor", "titel_stark", "titel_nach")).strip()
    return kopf or felder.get("frage", "") or felder.get("zitat", "")


def _hook(caption: str) -> str:
    return caption.split("\n")[0].strip()


def _begruendung(plan: dict, geplante_saeule: str, hat_foto: bool) -> str:
    """Warum genau dieser Beitrag an diesem Tag steht."""
    ist = plan["rubrik"]
    teile = [SAEULEN_ZWECK.get(ist, "")]

    if ist != geplante_saeule:
        teile.append(
            f"<b>Ersatz:</b> Für „{geplante_saeule}“ liegt kein passendes Foto "
            f"im Medienordner. Statt den Tag ausfallen zu lassen, springt "
            f"„{ist}“ ein – so bleibt der Kalender lückenlos.")
    elif ist in FOTO_NOETIG and not hat_foto:
        teile.append("<b>Läuft als Textkachel.</b> Mit einem passenden Foto in "
                     "<code>content/medien/</code> wird daraus automatisch ein "
                     "Bildbeitrag.")

    return " ".join(t for t in teile if t)


def sammle(jahr: int, monat: int) -> list[dict]:
    """Nur die tatsächlichen Post-Termine des Monats (zwei pro Woche).

    planer.vorschau() liefert bereits nur Posttage zurück – nicht einen
    Eintrag je Kalendertag. Das Datum kommt deshalb aus dem Plan selbst,
    nicht aus der Position in der Liste.
    """
    tage = monthrange(jahr, monat)[1]
    start = date(jahr, monat, 1)
    plaene = planer.vorschau(tage, start)

    eintraege = []
    for plan in plaene:
        tag = date.fromisoformat(plan["datum"])
        geplant = planer.rubrik_fuer(tag)
        caption = texter.baue_caption(plan)
        hat_foto = bool(plan["felder"].get("bild") or plan["felder"].get("bild_nachher"))
        eintraege.append({
            "datum": tag,
            "wochentag": WOCHENTAGE[tag.weekday()],
            "saeule_geplant": geplant,
            "saeule_ist": plan["rubrik"],
            "id": plan["id"],
            "gewerk": plan.get("gewerk", ""),
            # Rasterkacheln nennen das Feld 'oberlabel', Textkacheln 'badge'.
            "badge": plan["felder"].get("badge") or plan["felder"].get("oberlabel", ""),
            "headline": _kopfzeile(plan["felder"]),
            "lead": plan["felder"].get("lead", ""),
            "punkte": plan["felder"].get("punkte", []),
            "antwort": plan["felder"].get("antwort", ""),
            "hook": _hook(plan["caption"]),
            "caption": caption,
            "zeichen": len(caption),
            "begruendung": _begruendung(plan, geplant, hat_foto),
            "braucht_foto": plan["rubrik"] in FOTO_NOETIG and not hat_foto,
            "typ": plan.get("typ", "einzel"),
            "slides": plan.get("slides", []),
            "video": plan.get("video"),
            "plan": plan,
        })
    return eintraege


def _verteilung(eintraege: list[dict]) -> list[tuple[str, int, float]]:
    gesamt = len(eintraege)
    zaehler: dict[str, int] = {}
    for e in eintraege:
        zaehler[e["saeule_ist"]] = zaehler.get(e["saeule_ist"], 0) + 1
    return sorted(((s, n, 100 * n / gesamt) for s, n in zaehler.items()),
                  key=lambda x: -x[1])


def als_markdown(jahr: int, monat: int) -> str:
    e = sammle(jahr, monat)
    f = BRAND["firma"]
    z = []

    z.append(f"# Redaktionsplan {MONATE[monat - 1]} {jahr}")
    z.append(f"\n{f['name']} · {f['instagram']} · {f['plz_ort']}\n")
    posttage_namen = [WOCHENTAGE[t] for t in sorted(THEMEN.get("posttage", [1, 3]))]
    z.append(f"Zwei Beiträge pro Woche ({' und '.join(posttage_namen)}), "
             f"{len(e)} Beiträge in diesem Monat. Erstellt aus "
             "`content/themen.json`; jeder Text ist final und geht so raus.\n")

    z.append("\n## Verteilung der Säulen\n")
    z.append("| Säule | Beiträge | Anteil | Zielanteil |")
    z.append("|---|---|---|---|")
    ziel = {"vorher-nachher": "30 %", "detail": "25 %", "wissen": "25 %",
            "fehler": "10 %", "mensch": "10 %"}
    for s, n, p in _verteilung(e):
        z.append(f"| {s} | {n} | {p:.0f} % | {ziel.get(s, '–')} |")

    ohne_foto = sum(1 for x in e if x["saeule_ist"] != x["saeule_geplant"])
    if ohne_foto:
        z.append(f"\n> **{ohne_foto} von {len(e)} Terminen** weichen vom Plan ab, "
                 "weil für die Foto-Säulen kein Bildmaterial vorliegt. Mit eigenen "
                 "Baustellenfotos verschiebt sich die Verteilung automatisch zum "
                 "Zielanteil – ohne dass am System etwas geändert werden muss.\n")

    z.append("\n## Die Post-Termine und die Säulen-Rotation\n")
    z.append(f"Gepostet wird an {' und '.join(posttage_namen)}, jeweils zur "
             "recherchierten Bestzeit. Welche Säule an der Reihe ist, rotiert über "
             "die tatsächlichen Post-Termine – nicht über Kalendertage:\n")
    z.append("| Säule | Zweck |")
    z.append("|---|---|")
    for s_name in dict.fromkeys(THEMEN.get("rotation", [])):
        zweck = SAEULEN_ZWECK.get(s_name, "").replace("\n", " ")
        z.append(f"| {s_name} | {zweck} |")

    z.append("\n---\n\n## Die Beiträge im Einzelnen\n")

    for x in e:
        z.append(f"\n### {x['datum'].strftime('%d.%m.')} · {x['wochentag']} · "
                 f"{x['saeule_ist']}\n")
        z.append(f"**Bild-Headline:** {x['headline']}  ")
        if x["lead"]:
            z.append(f"**Unterzeile:** {x['lead']}  ")
        if x["punkte"]:
            # <b>Schlagwort</b> Rest  ->  **Schlagwort:** Rest
            reine = [re.sub(SCHLAGWORT, lambda m: f"**{m.group(1)}:** ", p)
                     for p in x["punkte"]]
            z.append("**Stichpunkte:** " + " · ".join(reine) + "  ")
        if x["antwort"]:
            klar = (x["antwort"].replace("<br><br>", " ").replace("<b>", "")
                    .replace("</b>", ""))
            z.append(f"**Antwort im Bild:** {klar}  ")
        z.append(f"**Kennzeichen:** {x['badge']} · **Gewerk:** {x['gewerk']} · "
                 f"**Thema-ID:** `{x['id']}`\n")
        z.append(f"*Warum an diesem Tag:* "
                 f"{x['begruendung'].replace('<b>', '**').replace('</b>', '**').replace('<code>', '`').replace('</code>', '`')}\n")
        z.append("**Text unter dem Beitrag:**\n")
        z.append("```")
        z.append(x["caption"])
        z.append("```")
        z.append(f"*{x['zeichen']} Zeichen von 2200.*\n")

    z.append("\n---\n\n## Was noch fehlt\n")
    z.append("- **Profikonto:** @berisabau muss von privat auf ein professionelles "
             "Konto umgestellt werden, sonst lässt Instagram keine Veröffentlichung "
             "über die Schnittstelle zu.")
    z.append("- **Eigene Fotos:** Ohne Bildmaterial laufen die Säulen "
             "vorher-nachher, detail und mensch als Textkacheln. Fünf bis sechs "
             "Projektordner decken ein Jahr ab.")
    gesperrt = [t["id"] for t in THEMEN["themen"] if t.get("pruefen")]
    if gesperrt:
        z.append(f"- **Gesperrte Themen ({len(gesperrt)}):** "
                 + ", ".join(f"`{g}`" for g in gesperrt)
                 + " – Kundenstimmen, die erst nach Freigabe durch den Inhaber "
                   "veröffentlicht werden dürfen.")
    return "\n".join(z)


def als_html(jahr: int, monat: int) -> str:
    e = sammle(jahr, monat)
    f = BRAND["firma"]

    def esc(s):
        return html.escape(str(s))

    karten = []
    for x in e:
        punkte = "".join(f"<li>{p}</li>" for p in x["punkte"])
        abweichung = ' class="karte abweichung"' if x["saeule_ist"] != x["saeule_geplant"] else ' class="karte"'
        karten.append(f"""
<article{abweichung} id="t{x['datum'].day}">
  <header>
    <span class="tag">{x['datum'].strftime('%d.%m.')}</span>
    <span class="wt">{esc(x['wochentag'])}</span>
    <span class="saeule s-{esc(x['saeule_ist'])}">{esc(x['saeule_ist'])}</span>
    {'<span class="foto">Foto nötig</span>' if x['braucht_foto'] else ''}
  </header>
  <h3>{esc(x['headline'])}</h3>
  {f'<p class="lead">{esc(x["lead"])}</p>' if x['lead'] else ''}
  {f'<ul class="punkte">{punkte}</ul>' if punkte else ''}
  {f'<div class="antwort">{x["antwort"]}</div>' if x['antwort'] else ''}
  <div class="warum"><b>Warum an diesem Tag:</b> {x['begruendung']}</div>
  <details>
    <summary>Text unter dem Beitrag · {x['zeichen']} Zeichen</summary>
    <pre>{esc(x['caption'])}</pre>
  </details>
  <footer><code>{esc(x['id'])}</code> · {esc(x['gewerk'])}</footer>
</article>""")

    verteilung = "".join(
        f'<div class="balken"><span class="name">{s}</span>'
        f'<span class="bar"><i style="width:{p:.0f}%"></i></span>'
        f'<span class="zahl">{n} · {p:.0f} %</span></div>'
        for s, n, p in _verteilung(e))

    return f"""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Redaktionsplan {MONATE[monat-1]} {jahr} · {esc(f['instagram'])}</title>
<style>
:root{{--rot:#D00000;--schwarz:#0B0B0F;--linie:rgba(255,255,255,.14)}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--schwarz);color:#e8e8ea;font-family:system-ui,-apple-system,sans-serif;
 line-height:1.6;padding:48px 24px;max-width:1000px;margin:0 auto}}
h1{{font-size:clamp(28px,4vw,42px);letter-spacing:-.5px;margin-bottom:8px}}
.sub{{color:#8a8f96;margin-bottom:40px}}
h2{{font-size:22px;margin:48px 0 18px;padding-bottom:10px;border-bottom:1px solid var(--linie)}}
.balken{{display:grid;grid-template-columns:140px 1fr 110px;gap:14px;align-items:center;margin-bottom:10px}}
.balken .name{{font-size:14px;color:#b6bbc2}}
.balken .bar{{height:10px;background:rgba(255,255,255,.08);border-radius:99px;overflow:hidden}}
.balken .bar i{{display:block;height:100%;background:var(--rot);border-radius:99px}}
.balken .zahl{{font-size:13px;color:#8a8f96;text-align:right}}
.hinweis{{background:rgba(208,0,0,.10);border:1px solid rgba(208,0,0,.4);
 border-radius:12px;padding:16px 20px;margin:24px 0;font-size:15px}}
.karte{{border:1px solid var(--linie);border-radius:14px;padding:22px 24px;margin-bottom:14px;
 background:rgba(255,255,255,.025)}}
.karte.abweichung{{border-left:3px solid var(--rot)}}
.karte header{{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px;font-size:13px}}
.tag{{font-weight:700;font-size:16px}}
.wt{{color:#8a8f96}}
.saeule{{padding:3px 12px;border-radius:99px;background:rgba(255,255,255,.09);
 text-transform:uppercase;letter-spacing:1px;font-size:11px;font-weight:600}}
.s-fehler{{background:rgba(208,0,0,.22);color:#ff8a8a}}
.s-wissen{{background:rgba(16,50,207,.28);color:#9db0ff}}
.s-mensch{{background:rgba(253,196,72,.20);color:#f6d089}}
.s-detail{{background:rgba(56,209,122,.18);color:#7fe0aa}}
.foto{{color:#f6d089;font-size:11px;border:1px solid rgba(253,196,72,.4);
 padding:2px 10px;border-radius:99px}}
.karte h3{{font-size:21px;line-height:1.25;margin-bottom:8px}}
.karte .lead{{color:#b6bbc2;font-size:15px;margin-bottom:12px}}
.punkte{{margin:0 0 14px 18px;font-size:14px;color:#c6cad0}}
.punkte li{{margin-bottom:5px}}
.antwort{{font-size:14px;color:#c6cad0;margin-bottom:14px}}
.warum{{font-size:13.5px;color:#98a0a8;background:rgba(255,255,255,.04);
 border-radius:10px;padding:12px 14px;margin-bottom:12px}}
details summary{{cursor:pointer;font-size:13px;color:#8a8f96;padding:6px 0}}
details[open] summary{{color:#e8e8ea}}
pre{{white-space:pre-wrap;font-family:ui-monospace,monospace;font-size:13px;
 background:#000;border:1px solid var(--linie);border-radius:10px;padding:16px;
 margin-top:8px;color:#d6dae0}}
.karte footer{{margin-top:12px;font-size:12px;color:#6d747c}}
code{{background:rgba(255,255,255,.08);padding:1px 6px;border-radius:5px;font-size:12px}}
ul.offen{{margin-left:20px}} ul.offen li{{margin-bottom:8px;font-size:15px}}
</style></head><body>
<h1>Redaktionsplan {MONATE[monat-1]} {jahr}</h1>
<p class="sub">{esc(f['name'])} · {esc(f['instagram'])} · {esc(f['plz_ort'])} ·
{len(e)} Beiträge, zwei pro Woche</p>

<h2>Verteilung der Säulen</h2>
{verteilung}

<div class="hinweis">
Rot markierte Beiträge weichen vom Wochenplan ab: Für die Foto-Säulen liegt noch
kein Bildmaterial vor, deshalb springt eine Textsäule ein. Sobald Fotos in
<code>content/medien/</code> liegen, verschiebt sich die Verteilung automatisch.
</div>

<h2>Die {len(e)} Beiträge</h2>
{''.join(karten)}

<h2>Was noch fehlt</h2>
<ul class="offen">
<li><b>Profikonto:</b> @berisabau ist noch ein privates Konto. Ohne Umstellung
lässt Instagram keine Veröffentlichung über die Schnittstelle zu.</li>
<li><b>Eigene Fotos:</b> Fünf bis sechs Projektordner in
<code>content/medien/projekte/</code> decken ein Jahr ab.</li>
</ul>
</body></html>"""


def schreibe(jahr: int, monat: int) -> tuple:
    md = OUT_DIR / f"redaktionsplan-{jahr}-{monat:02d}.md"
    ht = OUT_DIR / f"redaktionsplan-{jahr}-{monat:02d}.html"
    md.write_text(als_markdown(jahr, monat), encoding="utf-8")
    ht.write_text(als_html(jahr, monat), encoding="utf-8")
    return md, ht
