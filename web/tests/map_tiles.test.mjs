// The web map's tile sources must match the desktop's core/map_tiles.py.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { STREET_MAP, SATELLITE_MAP, ESRI_SATELLITE_MAP, MIN_ZOOM, MAX_ZOOM, CONTIGUOUS_US_CORNERS, tileUrl } from "../app/map_tiles.js";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const python = readFileSync(path.join(repoRoot, "core", "map_tiles.py"), "utf8");

function pythonSource(name) {
  const block = python.slice(python.indexOf(`${name} = TileSource(`));
  const url = [...block.matchAll(/"([^"]*)"/g)].map((m) => m[1]);
  // url_template is one or more adjacent string literals after key and name.
  const start = block.indexOf("url_template=");
  const end = block.indexOf("max_zoom=");
  const template = [...block.slice(start, end).matchAll(/"([^"]*)"/g)].map((m) => m[1]).join("");
  const maxZoom = Number(block.match(/max_zoom=(\d+)/)[1]);
  return { key: url[0], name: url[1], template, maxZoom };
}

test("the three sources match the Python ones", () => {
  for (const [js, name] of [[STREET_MAP, "STREET_MAP"], [SATELLITE_MAP, "SATELLITE_MAP"], [ESRI_SATELLITE_MAP, "ESRI_SATELLITE_MAP"]]) {
    const py = pythonSource(name);
    assert.equal(js.key, py.key, name);
    assert.equal(js.name, py.name, name);
    assert.equal(js.urlTemplate, py.template, name);
    assert.equal(js.maxZoom, py.maxZoom, name);
  }
  assert.equal(MIN_ZOOM, Number(python.match(/MIN_ZOOM = (\d+)/)[1]));
  assert.equal(MAX_ZOOM, Number(python.match(/MAX_ZOOM = (\d+)/)[1]));
  assert.match(python, /\(49\.38, -124\.85\), \(24\.52, -66\.95\)/);
  assert.deepEqual(CONTIGUOUS_US_CORNERS, [[49.38, -124.85], [24.52, -66.95]]);
});

test("tile addresses, with the key encoded", () => {
  assert.equal(tileUrl(STREET_MAP, 3, 1, 2), "https://tile.openstreetmap.org/3/1/2.png");
  assert.equal(tileUrl(SATELLITE_MAP, 3, 1, 2), "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/3/2/1");
  assert.equal(tileUrl(ESRI_SATELLITE_MAP, 3, 1, 2, "a b/c"), "https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/3/2/1?token=a%20b%2Fc");
});
