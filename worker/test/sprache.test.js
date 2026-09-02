// ---------------------------------------------------------------------------
// sprache.test.js — Versteht der Bot, was gesprochen wurde?
//
// Geprüft wird nur die Zuordnung von freiem Text zu einem Befehl. Sie ist
// eine reine Funktion, also ohne Netz und ohne Umschrift testbar. Genau
// deshalb ist sie eine eigene Funktion.
//
// Die Beispiele sind so formuliert, wie der Inhaber tatsächlich spricht,
// nicht wie ein Befehl aussieht.
// ---------------------------------------------------------------------------

import { test } from "node:test";
import assert from "node:assert/strict";
import { befehlAusText } from "../src/index.js";

const FAELLE = [
  ["Nächste bitte", "neu"],
  ["Zeig mir mal was anderes", "neu"],
  ["Wie funktioniert das hier", "hilfe"],
  ["Gib mir mal einen neuen Vorschlag", "neu"],
  ["Zeig mir was für heute", "neu"],
  ["Hast du was anderes", "neu"],
  ["Nächster bitte", "neu"],
  ["Wie ist der Stand", "status"],
  ["Wie viele liegen noch im Vorrat", "status"],
  ["Status", "status"],
  ["Wie viel liegt noch da", "status"],
  ["Hilfe", "hilfe"],
  ["Was kannst du eigentlich", "hilfe"],
  ["Welche Befehle gibt es", "hilfe"],
];

for (const [gesagt, erwartet] of FAELLE) {
  test(`„${gesagt}" ergibt ${erwartet ?? "keinen Befehl"}`, () => {
    assert.equal(befehlAusText(gesagt), erwartet);
  });
}

test("Hilfe gewinnt vor Vorschlag, wenn beides vorkommt", () => {
  // Reihenfolge ist Absicht: wer nach Hilfe fragt, will keinen Vorschlag.
  assert.equal(befehlAusText("Hilfe, ich brauche einen neuen Vorschlag"), "hilfe");
});

test("Grossschreibung spielt keine Rolle", () => {
  assert.equal(befehlAusText("STATUS BITTE"), "status");
});

test("Unverstandenes gibt null zurueck, statt zu raten", () => {
  // Wichtig: lieber nachfragen als den falschen Befehl ausfuehren.
  assert.equal(befehlAusText("Das Wetter ist heute schön"), null);
  assert.equal(befehlAusText(""), null);
});
