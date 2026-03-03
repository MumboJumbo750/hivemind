#!/usr/bin/env node
/**
 * deploy-local.js — Kopiert out/ in die installierte VS Code Extension.
 *
 * Wird automatisch nach `npm run compile` via `postcompile`-Hook aufgerufen.
 * Löst das Problem, dass VS Code die installierte (ggf. ältere) Extension-Version
 * aus ~/.vscode/extensions/ lädt und nicht den frisch gebauten out/-Ordner.
 *
 * Nach dem Kopieren: VS Code Developer → Reload Window (Ctrl+Shift+P).
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const EXT_ID = 'hivemind.hivemind-vscode-0.1.0';
const SRC = path.join(__dirname, '..', 'out');
const DEST = path.join(os.homedir(), '.vscode', 'extensions', EXT_ID, 'out');

if (!fs.existsSync(SRC)) {
  console.error(`[deploy-local] out/ nicht gefunden: ${SRC}`);
  process.exit(1);
}

if (!fs.existsSync(DEST)) {
  console.warn(`[deploy-local] Zielverzeichnis nicht gefunden: ${DEST}`);
  console.warn('[deploy-local] Extension nicht installiert? Kein Auto-Deploy.');
  process.exit(0); // kein Fehler — Extension evtl. nicht lokal installiert
}

const files = fs.readdirSync(SRC);
let copied = 0;
for (const file of files) {
  const src = path.join(SRC, file);
  const dest = path.join(DEST, file);
  if (fs.statSync(src).isFile()) {
    fs.copyFileSync(src, dest);
    copied++;
  }
}

console.log(`[deploy-local] ${copied} Dateien → ${DEST}`);
console.log('[deploy-local] Bitte VS Code neu laden: Ctrl+Shift+P → Developer: Reload Window');
