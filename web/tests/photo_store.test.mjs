import { test } from "node:test";
import assert from "node:assert/strict";
import { PhotoStore, photoKey, tileTooltip } from "../app/photo_store.js";

function entry(relPath, extra = {}) {
  return { name: relPath.split("/").pop(), relPath, size: 100, lastModified: 1, handle: null, getFile: async () => null, ...extra };
}

function storeWith(...paths) {
  const store = new PhotoStore();
  const { added } = store.add(paths.map((p) => entry(p)));
  return { store, ids: added };
}

test("adds photos sorted by path, skips duplicates", () => {
  const store = new PhotoStore();
  const first = store.add([entry("trip/IMG_10.CR3"), entry("trip/IMG_2.CR3")]);
  assert.deepEqual(first.added.map((id) => store.get(id).name), ["IMG_2.CR3", "IMG_10.CR3"]);
  const again = store.add([entry("trip/IMG_2.CR3"), entry("trip/IMG_3.CR3")]);
  assert.equal(again.skipped, 1);
  assert.equal(again.added.length, 1);
  assert.equal(store.photos.size, 3);
  // A same-named file with another size or date is another photo.
  assert.notEqual(photoKey(entry("a.jpg")), photoKey(entry("a.jpg", { size: 101 })));
});

test("counts, groups, and the opening view follow the GPS read", () => {
  const { store, ids } = storeWith("a.jpg", "b.jpg", "c.jpg");
  assert.deepEqual(store.counts(), { total: 3, has: 0, needs: 3, pending: 3 });
  store.setInfo(ids[0], { gps: { latitude: 1, longitude: 2 }, dates: {}, make: null, model: null });
  store.setInfo(ids[1], { gps: null, dates: {}, make: null, model: null });
  store.setInfo(ids[2], { error: "Unknown file type" });
  assert.deepEqual(store.counts(), { total: 3, has: 1, needs: 2, pending: 0 });
  assert.equal(store.get(ids[2]).status, "error");
  const groups = store.groups();
  assert.deepEqual(groups.map((g) => [g.key, g.title, g.ids.length]), [
    ["needs", "Photos without GPS Coordinates (2)", 2],
    ["has", "Photos with GPS Coordinates (1)", 1],
  ]);
  assert.equal(store.openingView(), "needs");
  store.setInfo(ids[1], { gps: { latitude: 3, longitude: 4 } });
  store.setInfo(ids[2], { gps: { latitude: 5, longitude: 6 }, error: null });
  assert.equal(store.openingView(), "all");
});

test("the Show filter narrows the grid and explains an empty one", () => {
  const { store, ids } = storeWith("a.jpg", "b.jpg");
  store.setInfo(ids[0], { gps: { latitude: 1, longitude: 2 } });
  store.setView("needs");
  assert.deepEqual(store.visibleIds(), [ids[1]]);
  store.setView("has");
  assert.deepEqual(store.visibleIds(), [ids[0]]);
  assert.equal(store.emptyMessage(), "");
  store.setInfo(ids[1], { gps: { latitude: 1, longitude: 2 } });
  store.setView("needs");
  assert.equal(store.emptyMessage(), "No photos need GPS. Every photo shown here has coordinates.");
  assert.throws(() => store.setView("other"));
  const empty = new PhotoStore();
  assert.match(empty.emptyMessage(), /Add Photos/);
});

test("selection: toggle, shift ranges over visible photos, select all shown", () => {
  const { store, ids } = storeWith("a.jpg", "b.jpg", "c.jpg", "d.jpg");
  store.toggle(ids[0]);
  store.toggle(ids[0]);
  assert.equal(store.selection.size, 0);
  store.selectRange(ids[3], ids[1]);
  assert.deepEqual(store.selectedIds(), [ids[1], ids[2], ids[3]]);
  store.deselectAll();
  store.setInfo(ids[0], { gps: { latitude: 1, longitude: 2 } });
  store.setView("needs");
  store.selectAll();
  assert.deepEqual(store.selectedIds(), [ids[1], ids[2], ids[3]], "Select All skips hidden photos");
  // Removing takes the photos out of the selection too.
  store.remove([ids[1]]);
  assert.deepEqual(store.selectedIds(), [ids[2], ids[3]]);
  assert.equal(store.photos.size, 3);
});

test("Only Show Selected Photos keeps deselected photos visible but faded, and a view button turns it off", () => {
  const { store, ids } = storeWith("a.jpg", "b.jpg", "c.jpg");
  store.toggle(ids[0]);
  store.toggle(ids[1]);
  store.setOnlySelected(true);
  assert.deepEqual(store.visibleIds(), [ids[0], ids[1]]);
  store.toggle(ids[1]);
  assert.deepEqual(store.visibleIds(), [ids[0], ids[1]]);
  assert.equal(store.isFaded(ids[1]), true);
  assert.equal(store.isFaded(ids[0]), false);
  store.setView("all");
  assert.equal(store.onlySelected, false);
  assert.deepEqual(store.visibleIds(), ids);
  store.deselectAll();
  store.setOnlySelected(true);
  assert.equal(store.onlySelected, false, "nothing selected: the toggle stays off");
});

test("the summary above the tabs", () => {
  const { store, ids } = storeWith("a.jpg", "b.jpg", "c.jpg");
  assert.deepEqual(store.summary(), { title: "No Photos Selected", text: "Click photos in the Photo List to select them." });
  store.setInfo(ids[0], { gps: { latitude: 40.4863251, longitude: -111.8134149 } });
  store.toggle(ids[0]);
  assert.deepEqual(store.summary(), { title: "1 Photo Selected", text: "a.jpg · GPS: 40.486325, -111.813415" });
  store.deselectAll();
  store.toggle(ids[1]);
  assert.deepEqual(store.summary(), { title: "1 Photo Selected", text: "b.jpg · No GPS" });
  store.selectAll();
  assert.deepEqual(store.summary(), { title: "3 Photos Selected", text: "2 without GPS · 1 with GPS" });
});

test("tile hover text", () => {
  const { store, ids } = storeWith("a.jpg");
  assert.match(tileTooltip(store.get(ids[0])), /^a\.jpg\nReading…/);
  store.setInfo(ids[0], { gps: { latitude: 1, longitude: 2 } });
  assert.match(tileTooltip(store.get(ids[0])), /GPS: 1\.000000, 2\.000000/);
  store.setInfo(ids[0], { gps: null, error: "Unknown file type" });
  assert.match(tileTooltip(store.get(ids[0])), /Could not be read: Unknown file type/);
});

test("clear empties everything and goes back to All", () => {
  const { store, ids } = storeWith("a.jpg", "b.jpg");
  store.toggle(ids[0]);
  store.setView("needs");
  let removed = null;
  store.subscribe((change) => { if (change.type === "removed") removed = change.ids; });
  store.clear();
  assert.deepEqual(removed, ids);
  assert.equal(store.photos.size, 0);
  assert.equal(store.selection.size, 0);
  assert.equal(store.view, "all");
});
