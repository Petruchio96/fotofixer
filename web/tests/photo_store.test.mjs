import { test } from "node:test";
import assert from "node:assert/strict";
import { PhotoStore, photoKey, tileTooltip, sortCameras, UNKNOWN_CAMERA } from "../app/photo_store.js";

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

test("download mode: a change waits for Download; undoing it back to the original drops the bytes", () => {
  const { store, ids } = storeWith("a.jpg");
  const london = { latitude: 51.5007, longitude: -0.1246 };
  store.setInfo(ids[0], { gps: null });
  const changed = new Uint8Array([1, 2, 3]);
  store.setGps(ids[0], london, changed);
  assert.deepEqual(store.pendingDownloadIds(), ids);
  assert.equal(store.get(ids[0]).bytes, changed);
  // Undo writes the original state back: nothing to download, no bytes kept.
  store.setGps(ids[0], null, new Uint8Array([4]));
  assert.deepEqual(store.pendingDownloadIds(), []);
  assert.equal(store.get(ids[0]).bytes, null);
  // Changed and downloaded: the download is the new baseline, kept in memory.
  store.setGps(ids[0], london, changed);
  store.markDownloaded(ids);
  assert.deepEqual(store.pendingDownloadIds(), []);
  assert.equal(store.get(ids[0]).bytes, changed);
  assert.deepEqual(store.get(ids[0]).originalGps, london);
  // A later change back to no GPS differs from the downloaded version: pending again.
  const again = new Uint8Array([5]);
  store.setGps(ids[0], null, again);
  assert.deepEqual(store.pendingDownloadIds(), ids);
  assert.equal(store.get(ids[0]).bytes, again);
});

test("Date & Time mode: camera groups, date order, the camera filter, and camera checkboxes", () => {
  const { store, ids } = storeWith("a.jpg", "b.jpg", "c.jpg", "d.jpg");
  store.setInfo(ids[0], { dates: {} });
  store.setDescription(ids[0], { dateTaken: "2026-10-03T10:00:00", dateText: "10/03/2026 10:00:00am", offsetText: "", camera: "Canon EOS R8" });
  store.setDescription(ids[1], { dateTaken: null, dateText: "", offsetText: "", camera: "Canon EOS R8" });
  store.setDescription(ids[2], { dateTaken: "2026-10-03T09:00:00", dateText: "10/03/2026 9:00:00am", offsetText: "MDT", camera: "Canon EOS R8" });
  store.setDescription(ids[3], { dateTaken: "2026-10-03T08:00:00", dateText: "", offsetText: "", camera: null });
  store.setMode("date");
  const groups = store.groups();
  assert.deepEqual(groups.map((g) => g.title), ["Canon EOS R8 (3)", "Unknown Camera (1)"]);
  assert.deepEqual(groups[0].ids, [ids[2], ids[0], ids[1]], "date order, undated last");
  assert.deepEqual(store.cameras(), ["Canon EOS R8", UNKNOWN_CAMERA]);
  assert.deepEqual(sortCameras(["Unknown Camera", "b cam", "A cam"]), ["A cam", "b cam", "Unknown Camera"]);
  store.setCameraFilter("Canon EOS R8");
  assert.deepEqual(store.visibleIds(), [ids[0], ids[1], ids[2]]);
  assert.equal(store.groups().length, 1);
  store.setCameraFilter("all");
  store.selectCamera("Canon EOS R8", true);
  assert.equal(store.cameraSelected("Canon EOS R8"), true);
  assert.equal(store.cameraSelected(UNKNOWN_CAMERA), false);
  store.selectCamera("Canon EOS R8", false);
  assert.equal(store.selection.size, 0);
  // Removing the filtered camera's last photo falls back to All.
  store.setCameraFilter(UNKNOWN_CAMERA);
  store.remove([ids[3]]);
  assert.equal(store.cameraFilter, "all");
  store.setMode("location");
  assert.equal(store.groups()[0].key, "needs");
});

test("time picking shows every camera, then puts the camera filter back", () => {
  const { store, ids } = storeWith("canon.cr3", "phone.jpg", "phone2.jpg");
  store.setDescription(ids[0], { dateTaken: "2026-10-03T10:00:00", dateText: "x", offsetText: "", camera: "Canon EOS R8" });
  store.setDescription(ids[1], { dateTaken: "2026-10-03T12:00:00", dateText: "y", offsetText: "", camera: "Apple iPhone 13" });
  store.setDescription(ids[2], { dateTaken: "2026-10-03T12:05:00", dateText: "z", offsetText: "", camera: "Apple iPhone 13" });
  store.setMode("date");
  store.setCameraFilter("Canon EOS R8");
  store.toggle(ids[0]);
  assert.deepEqual(store.visibleIds(), [ids[0]]);
  store.setPicking("time");
  assert.equal(store.cameraFilter, "all");
  assert.deepEqual(new Set(store.visibleIds()), new Set(ids), "the other camera's photos can be picked");
  assert.equal(store.pickLabel(ids[0]), "Being Changed");
  store.setPicking(null);
  assert.equal(store.cameraFilter, "Canon EOS R8", "the filter comes back after a pick or a cancel");
  assert.deepEqual(store.visibleIds(), [ids[0]]);
  // A camera whose photos were removed while picking falls back to All.
  store.setCameraFilter("Apple iPhone 13");
  store.setPicking("time");
  store.remove([ids[1], ids[2]]);
  store.setPicking(null);
  assert.equal(store.cameraFilter, "all");
});

test("pick mode kinds: time picking keeps the view and labels photos without a date", () => {
  const { store, ids } = storeWith("a.jpg", "b.jpg", "c.jpg");
  store.setInfo(ids[0], { gps: { latitude: 1, longitude: 2 } });
  store.setDescription(ids[0], { dateTaken: "2026-10-03T10:00:00", dateText: "x", offsetText: "", camera: "A" });
  store.setDescription(ids[1], { dateTaken: null, dateText: "", offsetText: "", camera: "A" });
  store.setDescription(ids[2], { dateTaken: "2026-10-03T11:00:00", dateText: "y", offsetText: "", camera: "A" });
  store.toggle(ids[2]);
  assert.equal(store.timePickableCount(), 1);
  store.setPicking("time");
  assert.deepEqual(store.visibleIds(), ids, "the view stays");
  assert.equal(store.pickLabel(ids[0]), "");
  assert.equal(store.pickLabel(ids[1]), "No Date");
  assert.equal(store.pickLabel(ids[2]), "Being Changed");
  store.setPicking(null);
  store.setPicking("location");
  assert.deepEqual(store.visibleIds(), [ids[0]], "location picking shows Has GPS");
  assert.equal(store.pickLabel(ids[1]), "No GPS");
  // A selected photo with GPS can be picked as the location source (it is deselected then).
  store.toggle(ids[0]);
  assert.equal(store.pickLabel(ids[0]), "");
  assert.equal(store.pickableCount(), 1);
  store.setSource(ids[0]);
  assert.equal(store.selection.has(ids[0]), false, "becoming the source deselects it");
  store.setSource(null);
  store.setPicking(null);
  store.setTimeSource(ids[0]);
  assert.equal(store.canSelect(ids[0]), true, "the time source stays selectable");
  store.setMode("date");
  assert.equal(store.markedSourceId(), ids[0]);
  store.setMode("location");
  assert.equal(store.markedSourceId(), null);
});

test("a date write marks the photo for Download; undoing it back to the original clears that", () => {
  const { store, ids } = storeWith("a.cr3");
  store.setInfo(ids[0], { gps: null, dates: { DateTimeOriginal: "2026:10:03 09:14:02", OffsetTime: null } });
  store.setDates(ids[0], { DateTimeOriginal: "2026:10:03 10:14:02", "QuickTime:CreateDate": "x", OffsetTime: "" }, new Uint8Array([1]));
  assert.equal(store.get(ids[0]).dates.DateTimeOriginal, "2026:10:03 10:14:02");
  assert.equal(store.get(ids[0]).dates.OffsetTime, null);
  assert.equal("QuickTime:CreateDate" in store.get(ids[0]).dates, false);
  assert.deepEqual(store.pendingDownloadIds(), ids);
  // Undo writes the original tags back (a tag that wasn't there as ""): no download needed.
  store.setDates(ids[0], { DateTimeOriginal: "2026:10:03 09:14:02", "QuickTime:CreateDate": "y", OffsetTime: "" }, new Uint8Array([2]));
  assert.deepEqual(store.pendingDownloadIds(), []);
  assert.equal(store.get(ids[0]).bytes, null);
  store.setDates(ids[0], { DateTimeOriginal: "2026:10:03 10:14:02" }, new Uint8Array([3]));
  store.markDownloaded(ids);
  assert.deepEqual(store.pendingDownloadIds(), []);
  // After the download, the downloaded dates are the baseline.
  store.setDates(ids[0], { DateTimeOriginal: "2026:10:03 09:14:02" }, new Uint8Array([4]));
  assert.deepEqual(store.pendingDownloadIds(), ids);
});
