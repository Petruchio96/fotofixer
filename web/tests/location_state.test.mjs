import { test } from "node:test";
import assert from "node:assert/strict";
import { buildLocationState, overwriteQuestion, changeMessage } from "../app/location_state.js";

const london = { latitude: 51.5007, longitude: -0.1246 };
const photos = new Map([
  ["a", { name: "a.jpg", gps: null }],
  ["b", { name: "b.jpg", gps: { latitude: 1, longitude: 2 } }],
  ["c", { name: "c.jpg", gps: { latitude: 3, longitude: 4 } }],
]);

test("nothing selected", () => {
  const state = buildLocationState({ selectedIds: [], photos, newLocation: london, fieldsEmpty: false });
  assert.equal(state.canApply, false);
  assert.equal(state.applyLabel, "Apply Location to Selected Photos");
  assert.equal(state.hint, "Select the photos to change in the Photo List.");
  assert.equal(state.canRemove, false);
  assert.equal(state.removeLabel, "Remove GPS from Selected Photos");
});

test("fields empty, invalid, and valid", () => {
  let state = buildLocationState({ selectedIds: ["a"], photos, newLocation: null, fieldsEmpty: true });
  assert.match(state.hint, /Set a new location above/);
  assert.equal(state.hintTone, "info");
  state = buildLocationState({ selectedIds: ["a"], photos, newLocation: null, fieldsEmpty: false });
  assert.match(state.hint, /isn't valid/);
  assert.equal(state.hintTone, "error");
  state = buildLocationState({ selectedIds: ["a"], photos, newLocation: london, fieldsEmpty: false });
  assert.equal(state.canApply, true);
  assert.equal(state.applyLabel, "Apply Location to 1 Photo");
  assert.equal(state.hint, "");
});

test("overwrite warning and the source photo", () => {
  let state = buildLocationState({ selectedIds: ["a", "b", "c"], photos, newLocation: london, fieldsEmpty: false });
  assert.equal(state.applyLabel, "Apply Location to 3 Photos");
  assert.deepEqual(state.overwriteIds, ["b", "c"]);
  assert.equal(state.hint, "2 photos already have GPS, which will be replaced.");
  assert.equal(state.hintTone, "warning");
  assert.equal(state.removeLabel, "Remove GPS from Selected 2 Photos");
  assert.deepEqual(state.removeIds, ["b", "c"]);
  // The source photo is never a target.
  state = buildLocationState({ selectedIds: ["b"], photos, newLocation: london, fieldsEmpty: false, sourceId: "b" });
  assert.equal(state.canApply, false);
  assert.match(state.hint, /source of the new location/);
  state = buildLocationState({ selectedIds: ["a", "b"], photos, newLocation: london, fieldsEmpty: false, sourceId: "b" });
  assert.deepEqual(state.targets, ["a"]);
  assert.equal(state.hint, "The source photo isn't changed.");
});

test("the overwrite question and the change messages", () => {
  assert.match(overwriteQuestion(1, 2), /^1 photo already has GPS coordinates\. Choose Skip/);
  assert.match(overwriteQuestion(2, 0), /^2 photos already have GPS coordinates\. Choose Replace/);
  assert.equal(changeMessage({ action: "apply", count: 3 }), "Applied GPS to 3 photos.");
  assert.equal(changeMessage({ action: "apply", count: 1, skipped: 1, backups: 1 }), "Applied GPS to 1 photo. Skipped 1 that already has GPS. Saved a backup of the original next to it.");
  assert.equal(changeMessage({ action: "remove", count: 2, backups: 2 }), "Removed GPS from 2 photos. Saved 2 backups of the originals next to them.");
});
