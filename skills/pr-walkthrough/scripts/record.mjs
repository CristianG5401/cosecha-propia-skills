#!/usr/bin/env node
import { existsSync } from 'fs';
import { readFile, rename, unlink } from 'fs/promises';
import path from 'path';

import { chromium } from 'playwright';

const DEFAULT_DURATION_S = 3;
const BEAT_PAD_S = 0.4;
const VIEWPORT = { width: 1280, height: 720 };
const WAIT_FOR_TIMEOUT_MS = 15_000;

/**
 * Playwright play action from a beat.
 *
 * @typedef {object} Play
 * @property {'goto' | 'click' | 'hover' | 'wait' | 'fill' | 'waitFor'} [do]
 * @property {string} [url]
 * @property {string} [text]
 * @property {string} [selector]
 * @property {string} [value]
 */

/**
 * One walkthrough beat.
 *
 * @typedef {object} Beat
 * @property {string} id
 * @property {string} [narration]
 * @property {string} [action]
 * @property {Play} [play]
 */

/**
 * beats.json document.
 *
 * @typedef {object} BeatsDoc
 * @property {string} [start_url]
 * @property {Beat[]} [beats]
 */

/**
 * Print usage and exit.
 */
function usage() {
  console.error('Usage: node record.mjs <workdir>');
  process.exit(1);
}

/**
 * Parse durations.txt lines `NN <seconds>` into a map of id → seconds.
 *
 * @param {string} text - Raw durations.txt contents
 * @returns {Map<string, number>}
 */
function parseDurations(text) {
  const map = new Map();
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }
    const match = trimmed.match(/^(\S+)\s+(\S+)/);
    if (!match) {
      continue;
    }
    const seconds = Number(match[2]);
    if (!Number.isFinite(seconds)) {
      continue;
    }
    map.set(match[1], seconds);
  }
  return map;
}

/**
 * Remaining hold after play so the beat matches TTS duration + pad.
 *
 * @param {number} durationS
 * @param {number} elapsedS
 * @returns {number}
 */
function remainingWaitS(durationS, elapsedS) {
  return Math.max(0, durationS + BEAT_PAD_S - elapsedS);
}

/**
 * Resolve the Playwright locator. `play.selector` wins over `play.text`.
 * CSS locators use `.first()` so a multi-match does not trip strict mode.
 * Fill without selector uses `getByLabel` so the control is targeted, not the label node.
 *
 * @param {import('playwright').Page} page
 * @param {Play} play
 * @param {boolean} [forFill]
 * @returns {import('playwright').Locator}
 */
function resolveLocator(page, play, forFill) {
  if (play.selector) {
    return page.locator(play.selector).first();
  }
  if (!play.text) {
    throw new Error('play requires selector or text');
  }
  if (forFill) {
    return page.getByLabel(play.text, { exact: false }).first();
  }
  return page.getByText(play.text, { exact: false }).first();
}

/**
 * Run one beat's play action on the page.
 *
 * @param {import('playwright').Page} page
 * @param {Play | undefined} play
 * @param {string} startUrl
 */
async function runPlay(page, play, startUrl) {
  if (!play || play.do === 'wait') {
    return;
  }

  switch (play.do) {
    case 'goto': {
      const url = play.url || startUrl;
      await page.goto(url, { waitUntil: 'domcontentloaded' });
      return;
    }
    case 'click': {
      if (!play.selector && !play.text) {
        throw new Error('play.click requires selector or text');
      }
      await resolveLocator(page, play).click();
      return;
    }
    case 'hover': {
      if (!play.selector && !play.text) {
        throw new Error('play.hover requires selector or text');
      }
      await resolveLocator(page, play).hover();
      return;
    }
    case 'fill': {
      if (!play.value) {
        throw new Error('play.fill requires value');
      }
      if (!play.selector && !play.text) {
        throw new Error('play.fill requires selector or text');
      }
      await resolveLocator(page, play, true).fill(play.value);
      return;
    }
    case 'waitFor': {
      if (!play.selector && !play.text) {
        throw new Error('play.waitFor requires selector or text');
      }
      await resolveLocator(page, play).waitFor({
        state: 'visible',
        timeout: WAIT_FOR_TIMEOUT_MS,
      });
      return;
    }
    default:
      throw new Error(`Unknown play.do: ${play.do}`);
  }
}

/**
 * Record a headed Chromium walkthrough into workdir/screencast.webm.
 *
 * @param {string} workdir
 */
async function record(workdir) {
  const beatsPath = path.join(workdir, 'beats.json');
  const durationsPath = path.join(workdir, 'durations.txt');

  if (!existsSync(beatsPath)) {
    throw new Error(`beats.json missing in ${workdir}`);
  }
  if (!existsSync(durationsPath)) {
    throw new Error(`durations.txt missing in ${workdir}`);
  }

  /** @type {BeatsDoc} */
  const beatsDoc = JSON.parse(await readFile(beatsPath, 'utf8'));
  const startUrl = beatsDoc.start_url;
  if (!startUrl) {
    throw new Error('beats.json missing start_url');
  }

  const beats = Array.isArray(beatsDoc.beats) ? [...beatsDoc.beats] : [];
  if (beats.length === 0) {
    throw new Error('beats.json has no beats');
  }
  beats.sort((a, b) => String(a.id).localeCompare(String(b.id), undefined, { numeric: true }));

  const durations = parseDurations(await readFile(durationsPath, 'utf8'));

  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    recordVideo: {
      dir: workdir,
      size: VIEWPORT,
    },
  });
  const page = await context.newPage();
  const video = page.video();

  try {
    // Always land on start_url first. If beat 01 is also a goto, navigating twice is ok.
    await page.goto(startUrl, { waitUntil: 'domcontentloaded' });

    for (const beat of beats) {
      const lookedUp = durations.get(String(beat.id));
      const durationS = Number.isFinite(lookedUp) ? lookedUp : DEFAULT_DURATION_S;
      const t0 = Date.now();
      await runPlay(page, beat.play, startUrl);
      const elapsed = (Date.now() - t0) / 1000;
      const waitS = remainingWaitS(durationS, elapsed);
      await page.waitForTimeout(waitS * 1000);
    }
  } finally {
    await context.close();
    await browser.close();
  }

  if (!video) {
    throw new Error('Playwright did not record a video');
  }

  const videoPath = await video.path();
  const dest = path.join(workdir, 'screencast.webm');
  if (path.resolve(videoPath) !== path.resolve(dest)) {
    if (existsSync(dest)) {
      await unlink(dest);
    }
    await rename(videoPath, dest);
  }

  if (!existsSync(dest)) {
    throw new Error(`screencast.webm was not written to ${dest}`);
  }

  console.log(dest);
}

/**
 * CLI entry: record workdir into screencast.webm.
 */
async function main() {
  if (process.argv.length !== 3 || !process.argv[2]) {
    usage();
  }

  const workdir = path.resolve(process.argv[2]);
  if (!existsSync(workdir)) {
    console.error(`Error: workdir not found: ${workdir}`);
    process.exit(1);
  }

  await record(workdir);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
