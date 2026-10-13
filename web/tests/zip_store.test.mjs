import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { buildStoredZip, crc32 } from "../app/zip_store.js";

test("crc32 of a known string", () => {
  assert.equal(crc32(new TextEncoder().encode("123456789")), 0xcbf43926);
  assert.equal(crc32(new Uint8Array(0)), 0);
});

test("a stored zip holds the files with their folders and bytes", () => {
  const files = [
    { name: "trip/IMG_1.jpg", bytes: new Uint8Array([0xff, 0xd8, 1, 2, 3]) },
    { name: "IMG_2.CR3", bytes: new Uint8Array(70000).map((_, i) => i % 251) },
  ];
  const zip = buildStoredZip(files, new Date(2026, 9, 13, 4, 30, 0));
  assert.equal(zip[0], 0x50);
  assert.equal(zip[1], 0x4b);
  // Unpack with Python's zipfile, which validates the CRCs.
  const dir = mkdtempSync(path.join(tmpdir(), "fotofixer-zip-"));
  try {
    const zipPath = path.join(dir, "test.zip");
    writeFileSync(zipPath, zip);
    const listing = execFileSync("python3", ["-I", "-c", `
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    assert z.testzip() is None, "bad CRC"
    for info in z.infolist():
        print(info.filename, info.file_size, info.compress_type, info.date_time)
    z.extractall(sys.argv[2])
`, zipPath, dir]).toString();
    assert.match(listing, /trip\/IMG_1\.jpg 5 0 \(2026, 10, 13, 4, 30, 0\)/);
    assert.match(listing, /IMG_2\.CR3 70000 0/);
    assert.deepEqual([...readFileSync(path.join(dir, "trip", "IMG_1.jpg"))], [0xff, 0xd8, 1, 2, 3]);
    assert.equal(readFileSync(path.join(dir, "IMG_2.CR3")).length, 70000);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
