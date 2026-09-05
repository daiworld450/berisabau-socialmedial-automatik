#!/bin/sh
# Holt einen Twitch-Stream und macht daraus Clip-Vorschläge.
#
# So geht es:
#   1. Diese Datei doppelklicken
#   2. Die Adresse des VODs einfügen (die Seite mit /videos/ darin)
#   3. Warten
#
# Alles andere passiert von selbst: Werkzeuge nachinstallieren, Ton laden,
# Text erkennen, auswerten, Ergebnisordner öffnen.
#
# Warum ein VOD und nicht der Live-Stream: erst in der Aufzeichnung zählt
# die Zeit ab einer festen Sekunde null. Live säßen die Clips daneben.
#
# Warum über den Ton und nicht über den Chat: Twitch verlangt für Chatabrufe
# einen signierten Nachweis aus einem angemeldeten Browser. Ohne den wird
# jeder Abruf mit "failed integrity check" abgewiesen. Der Ton ist frei
# abrufbar - und liefert ohnehin das bessere Ergebnis, weil daraus die
# Untertitel und die Zitate für die Hooks entstehen.
#
# Der lange Teil ist die Spracherkennung: rechne bei zweieinhalb Stunden
# Stream mit ein bis drei Stunden. Der Rechner darf dabei nicht schlafen.

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

# Die Kategorie geht in die Hashtags ein (#justchatting, #cs2 ...) und
# beeinflusst die Bildaufteilung. Bei K1ANUSH ist Just Chatting der
# Regelfall, deshalb steht sie als Vorgabe da - Enter genuegt.
if [ -z "$SPIEL" ]; then
  printf "Kategorie des Streams [Just Chatting]: "
  read -r SPIEL
fi
[ -z "$SPIEL" ] && SPIEL="Just Chatting"

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

if ! "$PY" -c "import faster_whisper" >/dev/null 2>&1; then
  echo "Richte Spracherkennung ein. Das sind einige hundert Megabyte,"
  echo "einmalig. Bei langsamer Leitung dauert es ein paar Minuten."
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet yt-dlp faster-whisper
fi

# --------------------------------------------------------------------------
# Ton laden
# --------------------------------------------------------------------------
TON="$ZIEL/ton.m4a"
if [ -s "$TON" ]; then
  echo "Ton liegt schon vor, wird nicht neu geladen."
else
  echo "Lade den Ton des Streams..."
  echo
  if ! "$VENV/bin/yt-dlp" -f bestaudio --extract-audio --audio-format m4a \
       -o "$TON" "$URL"; then
    echo
    echo "Der Ton liess sich nicht laden. Haeufigste Gruende:"
    echo "  - das VOD ist nur fuer Abonnenten sichtbar"
    echo "  - die Aufzeichnung ist schon geloescht"
    echo "  - keine Internetverbindung"
    printf "Zum Schliessen Enter druecken. "; read -r _; exit 1
  fi
fi

# --------------------------------------------------------------------------
# Text erkennen - der lange Teil
# --------------------------------------------------------------------------
TEXT="$ZIEL/transkript.json"
if [ -s "$TEXT" ]; then
  echo "Transkript liegt schon vor, wird nicht neu erkannt."
else
  echo
  echo "Erkenne den gesprochenen Text."
  echo "Das dauert bei zweieinhalb Stunden Stream ein bis drei Stunden."
  echo "Der Rechner darf dabei nicht in den Ruhezustand gehen."
  echo "(Abbrechen mit Strg+C ist gefahrlos - Ton und Fortschritt bleiben.)"
  echo
  cd "$WERK"
  if ! "$PY" src/clipwerk/transkript.py "$TON" --ziel "$TEXT"; then
    echo
    echo "Die Spracherkennung ist gescheitert."
    printf "Zum Schliessen Enter druecken. "; read -r _; exit 1
  fi
fi

# --------------------------------------------------------------------------
# Auswerten
# --------------------------------------------------------------------------
echo
echo "Werte aus..."
echo
cd "$WERK"
python3 src/main.py clip analyse \
  --transkript "$TEXT" \
  --stream-id "$VOD" \
  --streamer K1ANUSH \
  --spiel "$SPIEL" \
  --ziel "$ZIEL/vorschlaege" \
  --aufnehmen

echo
echo "=============================================="
echo "  Fertig"
echo "=============================================="
echo
echo "  $ZIEL/vorschlaege/bericht.md      die Clips zum Nachlesen"
echo "  $ZIEL/vorschlaege/untertitel/     zum Einbrennen oder Hochladen"
echo
echo "Darin steht je Clip: Zeitstempel, Kategorie, Punktzahl, Hook,"
echo "Schnittplan, Untertitel, Titel, Caption und Hashtags."
echo
echo "Veroeffentlichungsplan anzeigen:"
echo "  python3 src/main.py clip plan --clips \"$ZIEL/vorschlaege/clips.json\""
echo

command -v open >/dev/null 2>&1 && open "$ZIEL/vorschlaege" 2>/dev/null || true

printf "Auch das Video laden und die Clips fertig rendern? [j/N] "
read -r MITVIDEO
case "$MITVIDEO" in
  j|J) : ;;
  *)
    printf "Zum Schliessen Enter druecken. "; read -r _
    exit 0 ;;
esac

VIDEO="$ZIEL/vod.mp4"
if [ ! -s "$VIDEO" ]; then
  echo "Lade das Video. Das koennen mehrere Gigabyte sein..."
  "$VENV/bin/yt-dlp" "$URL" -o "$VIDEO"
fi

echo
echo "Erzeuge die Renderbefehle..."
python3 src/main.py clip rendern \
  --clips "$ZIEL/vorschlaege/clips.json" \
  --video "$VIDEO"

echo
echo "Zum Rendern:  sh \"$ZIEL/vorschlaege/rendern.sh\""
echo "Dafuer wird ffmpeg gebraucht:  brew install ffmpeg"
echo
command -v open >/dev/null 2>&1 && open "$ZIEL/vorschlaege" 2>/dev/null || true
printf "Zum Schliessen Enter druecken. "
read -r _
