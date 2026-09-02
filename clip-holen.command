#!/bin/sh
# Holt einen Twitch-Stream und macht daraus Clip-Vorschläge.
#
# So geht es:
#   1. Diese Datei doppelklicken
#   2. Die Adresse des VODs einfügen (das ist die Seite mit /videos/ darin)
#   3. Warten
#
# Alles andere passiert von selbst: Werkzeuge nachinstallieren, Chat laden,
# auswerten, Ergebnisordner öffnen.
#
# Warum ein VOD und nicht der Live-Stream: Chat und Transkript zählen beim
# VOD ab derselben Sekunde null. Live kommen sie aus zwei Quellen mit zwei
# Nullpunkten, und die Clips säßen um Sekunden daneben.
#
# Zwei Durchgänge, weil sie unterschiedlich lange dauern:
#   Chat-Modus      wenige Minuten, findet die Momente
#   Voller Durchlauf  Stunden, bringt Untertitel und fertige Videos
# Der erste läuft immer, der zweite nur auf Nachfrage.

set -e

WERK=$(cd "$(dirname "$0")" && pwd)
ARBEIT="$HOME/Desktop/K1ANUSH Clips"
VENV="$ARBEIT/.werkzeug"

echo
echo "=============================================="
echo "  Clip-Werk - Stream holen und auswerten"
echo "=============================================="
echo

# --------------------------------------------------------------------------
# Python
# --------------------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "Fehler: python3 ist nicht installiert."
  echo
  echo "Auf dem Mac bekommst du es mit:"
  echo "    xcode-select --install"
  echo "oder von https://www.python.org/downloads/"
  echo
  printf "Zum Schliessen Enter druecken. "
  read -r _
  exit 1
fi

mkdir -p "$ARBEIT"

# --------------------------------------------------------------------------
# Adresse erfragen
# --------------------------------------------------------------------------
if [ -n "$1" ]; then
  URL="$1"
else
  echo "Adresse des VODs einfuegen und Enter druecken."
  echo "Sie sieht so aus:  https://www.twitch.tv/videos/2401234567"
  echo
  echo "Zu finden auf dem Twitch-Kanal unter 'Videos'. Ein Live-Stream"
  echo "geht nicht - erst wenn die Aufzeichnung da ist."
  echo
  printf "Adresse: "
  read -r URL
fi

case "$URL" in
  *twitch.tv/videos/*) : ;;
  "")
    echo
    echo "Keine Adresse eingegeben. Abgebrochen."
    printf "Zum Schliessen Enter druecken. "; read -r _; exit 0 ;;
  *)
    echo
    echo "Das sieht nicht nach einem VOD aus:"
    echo "  $URL"
    echo
    echo "Gebraucht wird eine Adresse mit /videos/ darin, nicht die"
    echo "Kanalseite. Also nicht  twitch.tv/k1anush , sondern"
    echo "twitch.tv/videos/2401234567 ."
    printf "Zum Schliessen Enter druecken. "; read -r _; exit 1 ;;
esac

# VOD-Nummer aus der Adresse ziehen - sie wird zur Stream-ID und sorgt
# dafuer, dass derselbe Stream nie zweimal in die Datenbank wandert.
VOD=$(printf '%s' "$URL" | sed -n 's#.*/videos/\([0-9][0-9]*\).*#\1#p')
if [ -z "$VOD" ]; then
  echo "Konnte die Videonummer nicht aus der Adresse lesen."
  printf "Zum Schliessen Enter druecken. "; read -r _; exit 1
fi

ZIEL="$ARBEIT/$VOD"
mkdir -p "$ZIEL"
echo
echo "Video $VOD"
echo "Ablage: $ZIEL"
echo

# --------------------------------------------------------------------------
# Werkzeuge - in einen eigenen Ordner, nicht ins System
# --------------------------------------------------------------------------
if [ ! -x "$VENV/bin/python" ]; then
  echo "Richte die Werkzeuge ein (einmalig, dauert ein paar Minuten)..."
  python3 -m venv "$VENV"
fi
PY="$VENV/bin/python"

if ! "$PY" -c "import chat_downloader" >/dev/null 2>&1; then
  echo "Lade Chat-Werkzeug..."
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet chat-downloader yt-dlp
fi

# --------------------------------------------------------------------------
# Durchgang 1: Chat
# --------------------------------------------------------------------------
CHAT="$ZIEL/chat.json"
if [ -s "$CHAT" ]; then
  echo "Chat liegt schon vor, wird nicht neu geladen."
else
  echo "Lade den Chat. Bei einem langen Stream dauert das einige Minuten."
  echo "(Abbrechen mit Strg+C ist jederzeit gefahrlos.)"
  echo
  # Fortschritt bleibt sichtbar, Fehlermeldungen wandern ins Protokoll.
  # Ein Python-Stacktrace hilft an dieser Stelle niemandem weiter; wer ihn
  # braucht, findet ihn in der Datei.
  LOG="$ZIEL/chat-protokoll.txt"
  if ! "$VENV/bin/chat_downloader" "$URL" --output "$CHAT" 2>"$LOG"; then
    echo
    echo "Der Chat liess sich nicht laden. Haeufigste Gruende:"
    echo "  - das VOD ist nur fuer Abonnenten sichtbar"
    echo "  - die Aufzeichnung ist schon geloescht"
    echo "  - keine Internetverbindung"
    echo
    echo "Letzte Zeilen des Protokolls:"
    tail -n 3 "$LOG" 2>/dev/null | sed 's/^/  /'
    echo
    echo "Vollstaendig in: $LOG"
    printf "Zum Schliessen Enter druecken. "; read -r _; exit 1
  fi
  rm -f "$LOG"
fi

echo
echo "Werte aus..."
echo
cd "$WERK"
python3 src/main.py clip analyse \
  --chat "$CHAT" \
  --stream-id "$VOD" \
  --streamer K1ANUSH \
  --ziel "$ZIEL/vorschlaege" \
  --aufnehmen

echo
echo "=============================================="
echo "  Fertig - erste Runde"
echo "=============================================="
echo
echo "Die Vorschlaege liegen in:"
echo "  $ZIEL/vorschlaege/bericht.md"
echo
echo "Darin steht je Clip: Zeitstempel, Kategorie, Punktzahl, Hook,"
echo "Schnittplan, Titel, Caption und Hashtags."
echo
echo "Was in dieser Runde fehlt: Untertitel und fertige Videodateien."
echo "Dafuer muessen Ton und Bild geladen und der Text erkannt werden -"
echo "das dauert bei einem langen Stream Stunden, nicht Minuten."
echo

command -v open >/dev/null 2>&1 && open "$ZIEL/vorschlaege" 2>/dev/null || true

printf "Jetzt den vollen Durchlauf starten (Untertitel + Videos)? [j/N] "
read -r WEITER
case "$WEITER" in
  j|J) : ;;
  *)
    echo
    echo "Gut. Du kannst diese Datei jederzeit erneut starten - der Chat"
    echo "ist gespeichert und wird nicht noch einmal geladen."
    printf "Zum Schliessen Enter druecken. "; read -r _
    exit 0 ;;
esac

# --------------------------------------------------------------------------
# Durchgang 2: Ton, Transkript, Video
# --------------------------------------------------------------------------
echo
if ! "$PY" -c "import whisper" >/dev/null 2>&1; then
  echo "Lade Spracherkennung. Das sind ueber ein Gigabyte, einmalig."
  "$VENV/bin/pip" install --quiet openai-whisper
fi

TON="$ZIEL/ton.m4a"
if [ ! -s "$TON" ]; then
  echo "Lade den Ton..."
  "$VENV/bin/yt-dlp" -f bestaudio "$URL" -o "$TON"
fi

TEXT="$ZIEL/ton.json"
if [ ! -s "$TEXT" ]; then
  echo
  echo "Erkenne den Text. Das ist der lange Teil - bei einem"
  echo "Sechs-Stunden-Stream durchaus eine halbe Nacht."
  echo "Der Rechner darf dabei nicht in den Ruhezustand gehen."
  echo
  "$VENV/bin/whisper" "$TON" --language de --model small \
    --output_format json --output_dir "$ZIEL"
fi

if [ ! -s "$TEXT" ]; then
  # Whisper benennt nach der Tondatei; falls anders, das erste JSON nehmen,
  # das nicht der Chat ist.
  GEFUNDEN=$(ls "$ZIEL"/*.json 2>/dev/null | grep -v 'chat\.json' | head -n 1)
  [ -n "$GEFUNDEN" ] && TEXT="$GEFUNDEN"
fi

VIDEO="$ZIEL/vod.mp4"
printf "Auch das Video laden und die Clips fertig rendern? [j/N] "
read -r MITVIDEO
case "$MITVIDEO" in
  j|J)
    if [ ! -s "$VIDEO" ]; then
      echo "Lade das Video. Das koennen mehrere Gigabyte sein..."
      "$VENV/bin/yt-dlp" "$URL" -o "$VIDEO"
    fi
    VIDEOARG="--video $VIDEO" ;;
  *) VIDEOARG="" ;;
esac

echo
echo "Werte erneut aus, diesmal mit Text..."
echo
# shellcheck disable=SC2086
python3 src/main.py clip analyse \
  --transkript "$TEXT" \
  --chat "$CHAT" \
  --stream-id "$VOD" \
  --streamer K1ANUSH \
  --ziel "$ZIEL/final" \
  $VIDEOARG

echo
echo "=============================================="
echo "  Fertig"
echo "=============================================="
echo
echo "  $ZIEL/final/bericht.md      die Clips zum Nachlesen"
echo "  $ZIEL/final/untertitel/     zum Einbrennen oder Hochladen"
if [ -n "$VIDEOARG" ]; then
  echo "  $ZIEL/final/rendern.sh      erzeugt die fertigen MP4s"
  echo
  echo "Zum Rendern im Terminal:  sh \"$ZIEL/final/rendern.sh\""
  echo "Dafuer wird ffmpeg gebraucht:  brew install ffmpeg"
fi
echo
echo "Veroeffentlichungsplan anzeigen:"
echo "  python3 src/main.py clip plan --clips \"$ZIEL/final/clips.json\""
echo

command -v open >/dev/null 2>&1 && open "$ZIEL/final" 2>/dev/null || true
printf "Zum Schliessen Enter druecken. "
read -r _
