// The web app's file types must match the desktop's core/file_types.py.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { JPEG_EXTENSIONS, RAW_EXTENSIONS, HEIF_EXTENSIONS, isSupportedName, isRawName, isHeifName, isJpegName, ACCEPT_ATTRIBUTE } from "../app/file_types.js";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

function pythonSet(source, name) {
  const match = source.match(new RegExp(`${name} = \\{([^}]*)\\}`));
  assert.ok(match, `${name} not found in core/file_types.py`);
  return [...match[1].matchAll(/"(\.[a-z0-9]+)"/g)].map((m) => m[1]).sort();
}

test("extension lists match core/file_types.py", () => {
  const python = readFileSync(path.join(repoRoot, "core", "file_types.py"), "utf8");
  assert.deepEqual([...JPEG_EXTENSIONS].sort(), pythonSet(python, "JPEG_EXTENSIONS"));
  assert.deepEqual([...RAW_EXTENSIONS].sort(), pythonSet(python, "RAW_EXTENSIONS"));
  assert.deepEqual([...HEIF_EXTENSIONS].sort(), pythonSet(python, "HEIF_EXTENSIONS"));
});

test("name checks ignore case and reject other files", () => {
  assert.equal(isSupportedName("IMG_0001.CR3"), true);
  assert.equal(isSupportedName("photo.JPEG"), true);
  assert.equal(isSupportedName("photo.png"), false);
  assert.equal(isSupportedName("noext"), false);
  assert.equal(isRawName("a.dng"), true);
  assert.equal(isHeifName("a.HEIC"), true);
  assert.equal(isJpegName("a.jpg"), true);
  assert.equal(isJpegName("a.heic"), false);
  assert.ok(ACCEPT_ATTRIBUTE.split(",").includes(".cr3"));
});
