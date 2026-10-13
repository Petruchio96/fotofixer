import { test } from "node:test";
import assert from "node:assert/strict";
import { satelliteSourceFor, MapHistory, photosAtSpot, hoverText, readoutText, doneButtonLabel } from "../app/map_state.js";

test("Satellite is Esri with a key, USGS without", () => {
  assert.equal(satelliteSourceFor("").key, "satellite");
  assert.equal(satelliteSourceFor("abc").key, "esri");
  assert.equal(satelliteSourceFor("abc").name, "Satellite");
  assert.equal(satelliteSourceFor("").name, "US Satellite");
});

test("Back steps through the locations set on the map, newest first", () => {
  const history = new MapHistory();
  assert.equal(history.canGoBack, false);
  history.remember({ latitude: "1", longitude: "2", sourceId: "a" });
  history.remember({ latitude: "3", longitude: "4" });
  assert.deepEqual(history.back(), { latitude: "3", longitude: "4", sourceId: null });
  assert.deepEqual(history.back(), { latitude: "1", longitude: "2", sourceId: "a" });
  assert.equal(history.back(), null);
  history.remember({ latitude: "", longitude: "" });
  history.clear();
  assert.equal(history.canGoBack, false);
});

test("dots within 2 px share a spot; nearby but separate dots don't", () => {
  const points = [
    { id: "a", x: 100, y: 100 },
    { id: "b", x: 101, y: 101 },
    { id: "c", x: 106, y: 100 },
  ];
  assert.deepEqual(photosAtSpot(points, "a"), ["a", "b"]);
  assert.deepEqual(photosAtSpot(points, "c"), ["c"]);
  assert.deepEqual(photosAtSpot(points, "zzz"), []);
});

test("hover text, readout, and the closing button's label", () => {
  assert.equal(hoverText(["a.jpg"]), "a.jpg");
  assert.equal(hoverText(["a", "b", "c", "d", "e"]), "a, b, c and 2 more");
  assert.equal(readoutText(40.2338451, -111.6585312), "40.233845, -111.658531");
  assert.equal(doneButtonLabel(true), "Select Location");
  assert.equal(doneButtonLabel(false), "Cancel");
});
