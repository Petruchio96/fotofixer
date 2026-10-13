// Every button needs a hover hint (the same rule as the desktop app). The
// app makes buttons through el(), which refuses one without a title; this
// checks nothing bypasses it, and that static HTML buttons have titles.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function filesUnder(dir, extension) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return ["vendor", "tests", "node_modules"].includes(entry.name) ? [] : filesUnder(full, extension);
    return entry.name.endsWith(extension) ? [full] : [];
  });
}

test("static HTML buttons have a title", () => {
  for (const file of filesUnder(webRoot, ".html")) {
    const html = readFileSync(file, "utf8");
    for (const tag of html.match(/<button\b[^>]*>/g) ?? []) {
      assert.match(tag, /\btitle="[^"]+"/, `${path.relative(webRoot, file)}: ${tag}`);
    }
  }
});

test("buttons are only made through el() (which requires a title)", () => {
  for (const file of filesUnder(path.join(webRoot, "app"), ".js")) {
    const source = readFileSync(file, "utf8");
    if (path.basename(file) === "dom.js") continue;
    assert.doesNotMatch(source, /createElement\(\s*["']button["']\s*\)/, path.relative(webRoot, file));
    assert.doesNotMatch(source, /<button/, path.relative(webRoot, file));
  }
});
