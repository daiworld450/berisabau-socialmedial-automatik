// ---------------------------------------------------------------------------
// Social-Bot-Worker für Berisa Bau.
//
// Zweck: /neu im Telegram-Chat soll in ein bis zwei Sekunden einen Vorschlag
// liefern. Über GitHub Actions ging das nicht — der Abruf lief alle zehn
// Minuten, und ein Lauf braucht allein zum Hochfahren fast eine Minute.
//
// Der Trick: Der Worker rendert nichts. Er verschickt fertige Bilder aus dem
// Vorrat, den der Workflow "Vorrat rendern" nachts auf GitHub Pages ablegt.
// Telegram lädt das Bild selbst von dort — der Worker schickt nur die URL.
//
// Was der Worker NICHT kann: veröffentlichen. Ein Druck auf "Freigeben"
// stößt deshalb den GitHub-Workflow an (repository_dispatch) und meldet dem
// Nutzer sofort, dass es läuft. Das dauert dann wieder rund eine Minute —
// aber beim Veröffentlichen zählt jede Sekunde weniger als beim Blättern.
// ---------------------------------------------------------------------------

const TG = "https://api.telegram.org/bot";

async function telegram(env, methode, daten) {
  const antwort = await fetch(`${TG}${env.TELEGRAM_TOKEN}/${methode}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(daten),
  });
  return antwort.json();
}

function erlaubt(env, chatId) {
  const liste = (env.TELEGRAM_CHAT_IDS || "").split(",").map((s) => s.trim());
  return liste.includes(String(chatId));
}

async function vorratLaden(env) {
  // cache: "no-store", sonst liefert Cloudflare den Stand von gestern.
  const antwort = await fetch(env.VORRAT_URL, { cache: "no-store" });
  if (!antwort.ok) throw new Error(`Vorrat nicht erreichbar (HTTP ${antwort.status})`);
  return antwort.json();
}

/** Welche Kandidaten wurden heute schon gezeigt? */
async function gezeigt(env, tag) {
  const roh = await env.ZUSTAND.get(`gezeigt:${tag}`);
  return roh ? JSON.parse(roh) : [];
}

async function merkeGezeigt(env, tag, id) {
  const liste = await gezeigt(env, tag);
  if (!liste.includes(id)) liste.push(id);
  // 3 Tage aufheben — danach ist der Vorrat ohnehin ein anderer.
  await env.ZUSTAND.put(`gezeigt:${tag}`, JSON.stringify(liste), {
    expirationTtl: 60 * 60 * 24 * 3,
  });
}

async function schickeVorschlag(env, chatId, eintrag, vorratTag) {
  const tasten = {
    inline_keyboard: [[
      { text: "✅ Freigeben", callback_data: `ok:${eintrag.id}`.slice(0, 64) },
      { text: "❌ Ablehnen", callback_data: `nein:${eintrag.id}`.slice(0, 64) },
    ]],
  };
  await telegram(env, "sendPhoto", {
    chat_id: chatId,
    photo: eintrag.bild_url,
    caption: eintrag.kurztext.slice(0, 1024),
    reply_markup: tasten,
  });
  await merkeGezeigt(env, vorratTag, eintrag.id);
}

async function naechsterKandidat(env) {
  const vorrat = await vorratLaden(env);
  const schon = await gezeigt(env, vorrat.tag);
  const offen = vorrat.eintraege.filter((e) => !schon.includes(e.id));
  return { vorrat, eintrag: offen[0] || null, alleGezeigt: offen.length === 0 };
}

/** Stösst einen GitHub-Workflow an. Nur nötig, wo der Worker nicht selbst kann. */
async function githubAnstossen(env, ereignis, nutzlast) {
  if (!env.GITHUB_TOKEN) return false;
  const antwort = await fetch(
    `https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`,
    {
      method: "POST",
      headers: {
        authorization: `Bearer ${env.GITHUB_TOKEN}`,
        accept: "application/vnd.github+json",
        "content-type": "application/json",
        "user-agent": "berisabau-social-bot",
      },
      body: JSON.stringify({ event_type: ereignis, client_payload: nutzlast }),
    },
  );
  return antwort.ok;
}

// --------------------------------------------------------------- Sprache
//
// Seit dem 02.09.2026 versteht der Bot auch Sprachnachrichten. Der Inhaber
// steht oft auf der Baustelle und hat keine Hand frei zum Tippen.
//
// Die Umschrift läuft über Cloudflare Workers AI im Worker selbst. Kein
// zweiter Dienst, kein zweiter Schlüssel, keine Datei verlässt Cloudflare.
// Braucht die Bindung [ai] in wrangler.toml.

const SPRACHE_MAX_SEKUNDEN = 120;

/** Holt die Audiodatei bei Telegram ab und gibt sie als Bytes zurück. */
async function sprachdateiHolen(env, fileId) {
  const info = await telegram(env, "getFile", { file_id: fileId });
  const pfad = info?.result?.file_path;
  if (!pfad) throw new Error("Telegram gibt keinen Dateipfad heraus.");

  const antwort = await fetch(`https://api.telegram.org/file/bot${env.TELEGRAM_TOKEN}/${pfad}`);
  if (!antwort.ok) throw new Error(`Datei nicht ladbar (HTTP ${antwort.status})`);
  return new Uint8Array(await antwort.arrayBuffer());
}

/** Schreibt die Sprachnachricht in Text um. */
async function umschreiben(env, bytes) {
  if (!env.AI) throw new Error("Workers AI ist nicht gebunden (siehe wrangler.toml).");
  const ergebnis = await env.AI.run("@cf/openai/whisper", { audio: [...bytes] });
  const text = (ergebnis?.text || "").trim();
  if (!text) throw new Error("Nichts verstanden.");
  return text;
}

/**
 * Übersetzt freien Text in einen Befehl. Bewusst über Stichwörter statt über
 * ein Sprachmodell: der Bot kennt vier Befehle, dafür braucht es keine KI.
 * Das kostet nichts, fällt nie aus und ist nachvollziehbar.
 *
 * Reihenfolge zählt, der erste Treffer gewinnt.
 */
export function befehlAusText(text) {
  const t = (text || "").toLowerCase();

  // Wortstämme statt ganzer Wörter: "nächster", "nächste", "nächstes" sollen
  // alle treffen. Eine schließende Wortgrenze würde genau das verhindern,
  // weil sie hinter dem Stamm eine Wortgrenze verlangt. Am Anfang bleibt die
  // Grenze stehen, sonst träfe "neu" auch in "erneuern".
  if (/\b(hilfe|was kannst du|welche befehle|wie funktion)/.test(t)) return "hilfe";
  if (/\b(status|vorrat|stand\b|wie viel|noch übrig|noch uebrig|noch da\b)/.test(t)) return "status";
  if (/\b(neu|vorschlag|was posten|zeig mir|nächst|naechst|ander)/.test(t)) return "neu";
  return null;
}

async function behandleSprache(env, nachricht) {
  const chatId = nachricht.chat?.id;
  const sprache = nachricht.voice || nachricht.audio;

  if (sprache.duration && sprache.duration > SPRACHE_MAX_SEKUNDEN) {
    await telegram(env, "sendMessage", {
      chat_id: chatId,
      text:
        `Die Nachricht ist ${sprache.duration} Sekunden lang, ich verarbeite bis zu ` +
        `${SPRACHE_MAX_SEKUNDEN}. Bitte kürzer, oder tipp den Befehl.`,
    });
    return;
  }

  let text;
  try {
    const bytes = await sprachdateiHolen(env, sprache.file_id);
    text = await umschreiben(env, bytes);
  } catch (fehler) {
    await telegram(env, "sendMessage", {
      chat_id: chatId,
      text: `Die Sprachnachricht ging nicht: ${fehler.message}\nTipp den Befehl, dann läuft es sicher.`,
    });
    return;
  }

  const befehl = befehlAusText(text);

  // Immer zeigen, was verstanden wurde. Whisper verhört sich gelegentlich,
  // und wer das sieht, wiederholt sich statt sich zu wundern.
  if (!befehl) {
    await telegram(env, "sendMessage", {
      chat_id: chatId,
      text:
        `Verstanden: „${text}"\n\n` +
        "Daraus werde ich nicht schlau. Ich kenne drei Dinge:\n" +
        "„gib mir einen neuen Vorschlag“, „wie ist der Stand“, „hilfe“.",
    });
    return;
  }

  await telegram(env, "sendMessage", { chat_id: chatId, text: `Verstanden: „${text}"` });
  await fuehreBefehlAus(env, chatId, befehl);
}

async function behandleNachricht(env, nachricht) {
  const chatId = nachricht.chat?.id;
  if (!erlaubt(env, chatId)) return;

  // Sprachnachrichten tragen "voice" statt "text". Wer nur auf text prüft,
  // verwirft sie stumm - genau das war hier bis zum 02.09.2026 der Fall.
  if (nachricht.voice || nachricht.audio) {
    await behandleSprache(env, nachricht);
    return;
  }

  const text = (nachricht.text || "").trim();
  if (!text.startsWith("/")) return;
  const befehl = text.split(/\s+/)[0].slice(1).split("@")[0].toLowerCase();
  await fuehreBefehlAus(env, chatId, befehl);
}

/** Ein Befehl, egal ob getippt oder gesprochen. */
async function fuehreBefehlAus(env, chatId, befehl) {

  if (befehl === "start" || befehl === "hilfe" || befehl === "help") {
    await telegram(env, "sendMessage", {
      chat_id: chatId,
      text:
        "Berisa Bau — Social-Bot\n\n" +
        "/neu     Vorschlag schicken (sofort)\n" +
        "/status  wie viel noch im Vorrat liegt\n" +
        "/hilfe   diese Übersicht\n\n" +
        "Du kannst auch eine Sprachnachricht schicken, etwa\n" +
        "„gib mir einen neuen Vorschlag“ oder „wie ist der Stand“.\n\n" +
        "Bei jedem Vorschlag: ✅ Freigeben oder ❌ Ablehnen.",
    });
    return;
  }

  if (befehl === "status") {
    try {
      const { vorrat, alleGezeigt } = await naechsterKandidat(env);
      const schon = await gezeigt(env, vorrat.tag);
      await telegram(env, "sendMessage", {
        chat_id: chatId,
        text:
          `Vorrat für ${vorrat.tag}: ${vorrat.eintraege.length} Kandidaten, ` +
          `${schon.length} gezeigt.\n` +
          (alleGezeigt ? "Alle durch — /neu füllt nach." : "Mit /neu geht es weiter."),
      });
    } catch (fehler) {
      await telegram(env, "sendMessage", { chat_id: chatId, text: `Vorrat nicht lesbar: ${fehler.message}` });
    }
    return;
  }

  // /anders und /vorschlag bleiben als Zweitnamen bestehen, stehen aber nicht
  // mehr in der Hilfe: /neu liefert ohnehin immer den nächsten noch nicht
  // gezeigten Kandidaten, also genau das, was /anders versprochen hat. Ein
  // eigener Eintrag in der Hilfe hätte einen Unterschied angekündigt, den es
  // weder hier noch in src/main.py gibt.
  if (befehl === "neu" || befehl === "anders" || befehl === "vorschlag") {
    try {
      const { vorrat, eintrag, alleGezeigt } = await naechsterKandidat(env);
      if (alleGezeigt) {
        await telegram(env, "sendMessage", {
          chat_id: chatId,
          text: "Alle Kandidaten aus dem Vorrat sind durch. Ich lasse neue rendern — dauert etwa eine Minute.",
        });
        await githubAnstossen(env, "vorrat-auffuellen", { anzahl: 5 });
        return;
      }
      await schickeVorschlag(env, chatId, eintrag, vorrat.tag);
    } catch (fehler) {
      await telegram(env, "sendMessage", { chat_id: chatId, text: `Ging nicht: ${fehler.message}` });
    }
    return;
  }

  await telegram(env, "sendMessage", {
    chat_id: chatId,
    text: `Unbekannter Befehl /${befehl}. /hilfe zeigt, was geht.`,
  });
}

async function behandleTaste(env, anfrage) {
  const chatId = anfrage.message?.chat?.id;
  if (!erlaubt(env, chatId)) return;

  const [aktion, id] = (anfrage.data || "").split(":");

  if (aktion === "nein") {
    await telegram(env, "answerCallbackQuery", {
      callback_query_id: anfrage.id,
      text: "Abgelehnt — nächster Vorschlag …",
    });
    const { vorrat, eintrag, alleGezeigt } = await naechsterKandidat(env);
    if (alleGezeigt) {
      await telegram(env, "sendMessage", {
        chat_id: chatId,
        text: "Keine Alternative mehr im Vorrat. Ich lasse nachrendern.",
      });
      await githubAnstossen(env, "vorrat-auffuellen", { anzahl: 5 });
      return;
    }
    await schickeVorschlag(env, chatId, eintrag, vorrat.tag);
    return;
  }

  if (aktion === "ok") {
    // Veröffentlichen kann der Worker nicht — das braucht die Graph API und
    // den Verlauf im Repo. Also den Workflow anstossen und sofort Bescheid geben.
    await telegram(env, "answerCallbackQuery", {
      callback_query_id: anfrage.id,
      text: "Freigegeben — wird veröffentlicht …",
    });
    const ok = await githubAnstossen(env, "beitrag-freigeben", { plan_id: id });
    await telegram(env, "sendMessage", {
      chat_id: chatId,
      text: ok
        ? `✅ ${id} freigegeben. Die Veröffentlichung läuft, das dauert rund eine Minute.`
        : `⚠️ ${id} konnte nicht angestossen werden — GITHUB_TOKEN fehlt oder ist ungültig.`,
    });
  }
}

export default {
  async fetch(anfrage, env) {
    const url = new URL(anfrage.url);

    if (url.pathname === "/" || url.pathname === "/gesundheit") {
      return new Response("Social-Bot laeuft.\n", { status: 200 });
    }

    if (url.pathname !== "/telegram" || anfrage.method !== "POST") {
      return new Response("nicht gefunden", { status: 404 });
    }

    // Telegram schickt das Geheimnis in diesem Kopf mit — so kann niemand
    // sonst den Worker als Bot missbrauchen.
    if (env.WEBHOOK_GEHEIMNIS &&
        anfrage.headers.get("x-telegram-bot-api-secret-token") !== env.WEBHOOK_GEHEIMNIS) {
      return new Response("verboten", { status: 403 });
    }

    let aktualisierung;
    try {
      aktualisierung = await anfrage.json();
    } catch {
      return new Response("kein JSON", { status: 400 });
    }

    // Die Arbeit dauert unter zwei Sekunden (ein Vorrats-Bild verschicken,
    // kein Rendern). Telegram wartet bis zu 60 Sekunden auf die Antwort,
    // also wird hier bewusst abgewartet statt im Hintergrund gearbeitet -
    // so gehen Fehler nicht still verloren.
    try {
      if (aktualisierung.callback_query) {
        await behandleTaste(env, aktualisierung.callback_query);
      } else if (aktualisierung.message) {
        await behandleNachricht(env, aktualisierung.message);
      }
    } catch (fehler) {
      console.error("Verarbeitung fehlgeschlagen:", fehler);
    }

    // Immer 200 - sonst stellt Telegram dieselbe Nachricht wieder und wieder zu.
    return new Response("ok", {
      status: 200,
      headers: { "content-type": "text/plain" },
    });
  },
};
