// FotoFixer – When & Where, the web version: everything runs in the
// visitor's browser. This module wires the pieces together and runs the
// pipelines: loading (file -> bytes -> ExifTool in the worker -> the Photo
// List, one photo at a time, the thumbnail made on this thread) and
// changing (Apply / Remove GPS / undo / redo -> ExifTool in the worker ->
// the file on disk, or a download).

import { PhotoStore, formatCoordinates } from "./photo_store.js";
import { createPhotoListView } from "./photo_list_view.js";
import { createChangePane } from "./summary_view.js";
import { PICK_PROMPT } from "./location_view.js";
import { ExifClient } from "./exif_client.js";
import { detectSaveMode, saveModeText, zipName, backupName, isBackupName } from "./save_mode.js";
import { entriesFromFolderPicker, entriesFromFileList, entriesFromDrop, entryFromFileHandle } from "./file_sources.js";
import { thumbnailFromPreview, thumbnailFromFile } from "./thumbnails.js";
import { isJpegName, isHeifName } from "./file_types.js";
import { EditHistory, EDIT_GPS } from "./edit_history.js";
import { overwriteQuestion, changeMessage } from "./location_state.js";
import { askOverwrite, confirmRemoveGps, showFailures, showNotice, showSettings } from "./dialogs.js";
import { buildStoredZip } from "./zip_store.js";

const saveMode = detectSaveMode();
const modeText = saveModeText(saveMode);

// ----- settings (this browser only) -----

const SETTINGS_KEY = "fotofixer.settings";
function loadSettings() {
  try {
    return { keepBackups: false, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? "{}") };
  } catch {
    return { keepBackups: false };
  }
}
function saveSettings(settings) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    // Private windows may refuse; the settings then last for the tab.
  }
}
let settings = loadSettings();

// ----- header -----

const modeBadge = document.getElementById("saveMode");
modeBadge.textContent = modeText.short;
modeBadge.title = modeText.long;
modeBadge.classList.add(saveMode);
const undoButton = document.getElementById("undoButton");
const redoButton = document.getElementById("redoButton");
document.getElementById("settingsButton").addEventListener("click", async () => {
  const result = await showSettings({ keepBackups: settings.keepBackups, canSaveInPlace: saveMode === "inplace" });
  if (result) {
    settings = { ...settings, ...result };
    saveSettings(settings);
  }
});

const store = new PhotoStore();
const history = new EditHistory();
const exif = new ExifClient(new URL("../worker/exif_worker.js", import.meta.url));

function photosWord(count) {
  return count === 1 ? "photo" : "photos";
}

// ----- the loading pipeline -----

const readQueue = []; // ids waiting for ExifTool
let batch = null; // {done, total, openOnFinish, started} while a batch is being read
let reading = false;
let lastMessage = { text: "", options: {} }; // shown again once the progress row goes away

async function addEntries(entries) {
  const wasEmpty = store.photos.size === 0;
  const { added, skipped } = store.add(entries);
  const parts = [];
  if (added.length) parts.push(`${added.length} ${photosWord(added.length)} added`);
  if (skipped) parts.push(`${skipped} already in the list`);
  if (!added.length && !skipped) parts.push("No photos found (JPG, HEIC, and camera RAW files are supported)");
  setMessage(parts.join(" · "));
  if (added.length) queueReads(added, wasEmpty);
  return added;
}

function queueReads(ids, openOnFinish = false) {
  readQueue.push(...ids);
  if (batch) batch.total += ids.length;
  else batch = { done: 0, total: ids.length, openOnFinish, started: performance.now() };
  listView.setProgress({ ...batch, cancellable: true });
  if (!reading) readNext();
}

async function readNext() {
  reading = true;
  while (readQueue.length) {
    const id = readQueue.shift();
    const photo = store.get(id);
    if (photo) await readPhoto(photo);
    if (batch) {
      batch.done += 1;
      listView.setProgress({ ...batch, cancellable: true });
    }
  }
  reading = false;
  const finished = batch;
  batch = null;
  setMessage(lastMessage.text, lastMessage.options);
  if (finished) console.debug(`read ${finished.done} photos in ${((performance.now() - finished.started) / 1000).toFixed(1)} s`);
  // A list that was empty opens on Needs GPS (or All if none need GPS);
  // adding to a list keeps the current view.
  if (finished?.openOnFinish && store.photos.size && !store.picking) store.setView(store.openingView());
}

/** The photo as it is now: the changed bytes waiting for Download, else the file. */
async function photoBytes(photo) {
  if (photo.bytes) return photo.bytes.slice();
  const file = await photo.getFile();
  return new Uint8Array(await file.arrayBuffer());
}

async function readPhoto(photo) {
  const started = performance.now();
  try {
    const file = photo.bytes ? null : await photo.getFile();
    const bytes = photo.bytes ? photo.bytes.slice() : new Uint8Array(await file.arrayBuffer());
    const reply = await exif.read(photo.name, bytes);
    if (!store.get(photo.id)) return; // removed while being read
    if (!reply.ok) {
      store.setInfo(photo.id, { error: reply.error });
      return;
    }
    const readMs = Math.round(performance.now() - started);
    const { gps, dates, make, model } = reply.tags;
    store.setInfo(photo.id, { gps, dates, make, model });
    await makeThumbnail(photo, file, reply.preview);
    console.debug(`${photo.name}: ExifTool ${readMs} ms, thumbnail ${Math.round(performance.now() - started) - readMs} ms`);
  } catch (error) {
    if (store.get(photo.id)) {
      store.setInfo(photo.id, { error: error.message === "cancelled" ? "Reading was cancelled" : String(error.message ?? error) });
    }
  }
}

async function makeThumbnail(photo, file, preview) {
  try {
    let blob = null;
    if (preview) {
      blob = await thumbnailFromPreview(preview.bytes, preview);
    } else if (file && (isJpegName(photo.name) || isHeifName(photo.name))) {
      // No embedded preview: decode the photo itself. HEIC works where the
      // browser decodes it (Safari); elsewhere the tile keeps the icon.
      blob = await thumbnailFromFile(file).catch(() => null);
    }
    store.setThumb(photo.id, blob ? URL.createObjectURL(blob) : null);
  } catch {
    store.setThumb(photo.id, null);
  }
}

function cancelLoading() {
  const waiting = readQueue.splice(0, readQueue.length);
  exif.cancelPending();
  for (const id of waiting) if (store.get(id)) store.setInfo(id, { error: "Reading was cancelled" });
}

// Free thumbnail memory when photos leave the list.
store.subscribe((change) => {
  if (change.type !== "removed") return;
  for (const id of change.ids) {
    const index = readQueue.indexOf(id);
    if (index >= 0) readQueue.splice(index, 1);
  }
});
const revoke = (photo) => photo.thumb && URL.revokeObjectURL(photo.thumb);
const originalRemove = store.remove.bind(store);
store.remove = (ids) => { for (const id of ids) { const photo = store.get(id); if (photo) revoke(photo); } originalRemove(ids); };
const originalClear = store.clear.bind(store);
store.clear = () => { for (const photo of store.photos.values()) revoke(photo); originalClear(); };

function setMessage(text, options = {}) {
  lastMessage = { text, options };
  listView.setMessage(text, options);
}

// ----- changing photos -----

let writing = false;

/**
 * Write gpsById (id -> {latitude, longitude} | null) into the photos, one
 * at a time: in place through the file handle when the photo has one
 * (with a backup copy first, when asked and the photo had GPS), else into
 * memory for Download. A failure on one photo never stops the others.
 */
async function writeStates(gpsById, { text, makeBackups }) {
  const ids = [...gpsById.keys()];
  const done = [];
  const failed = [];
  const backups = [];
  writing = true;
  listView.setBusy(true);
  document.body.classList.add("busy");
  updateUndoRedo();
  listView.setProgress({ text, done: 0, total: ids.length, cancellable: false });
  try {
    for (const [index, id] of ids.entries()) {
      const photo = store.get(id);
      if (!photo) continue;
      const gps = gpsById.get(id);
      try {
        const bytes = await photoBytes(photo);
        let backupBytes = null;
        if (makeBackups && photo.handle && photo.parent && photo.gps && settings.keepBackups && !isBackupName(photo.name)) {
          backupBytes = bytes.slice();
        }
        const reply = await exif.write(photo.name, bytes, gps);
        if (!reply.ok) throw new Error(reply.error);
        if (photo.handle) {
          const backup = backupBytes ? await makeBackup(photo, backupBytes) : null;
          const writable = await photo.handle.createWritable();
          await writable.write(reply.bytes);
          await writable.close();
          if (backup) backups.push(backup);
          store.setGps(id, gps);
        } else {
          store.setGps(id, gps, reply.bytes);
        }
        done.push(id);
      } catch (error) {
        failed.push(`${photo.name}: ${error.message ?? error}`);
      }
      listView.setProgress({ text, done: index + 1, total: ids.length, cancellable: false });
    }
  } finally {
    writing = false;
    listView.setBusy(false);
    document.body.classList.remove("busy");
    listView.setProgress(null);
  }
  return { done, failed, backups };
}

/**
 * Copy the original next to the photo as <name>_original.<ext> before its
 * first change. An existing backup is left alone (it holds the true
 * original). Returns {name, parent, entry} for the Photo List and undo, or
 * null when a backup was already there.
 */
async function makeBackup(photo, originalBytes) {
  const name = backupName(photo.name);
  let exists = true;
  try {
    await photo.parent.getFileHandle(name);
  } catch {
    exists = false;
  }
  if (exists) return null;
  const handle = await photo.parent.getFileHandle(name, { create: true });
  const writable = await handle.createWritable();
  await writable.write(originalBytes);
  await writable.close();
  const folder = photo.relPath.slice(0, photo.relPath.length - photo.name.length);
  const entry = await entryFromFileHandle(handle, folder + name, photo.parent);
  return { name, parent: photo.parent, entry };
}

/** Undo: delete the backups the undone change made, and take them out of the list. */
async function deleteBackups(backups) {
  const failed = [];
  const ids = [];
  for (const backup of backups) {
    try {
      await backup.parent.removeEntry(backup.name);
    } catch (error) {
      failed.push(`${backup.name}: could not delete the backup (${error.message ?? error})`);
    }
    const id = `${backup.entry.relPath}|${backup.entry.size}|${backup.entry.lastModified}`;
    if (store.get(id)) ids.push(id);
  }
  if (ids.length) store.remove(ids);
  return failed;
}

function rememberEdit({ before, after, backups, snapshot }) {
  history.record({ before, after, backups, snapshot, kind: EDIT_GPS });
  updateUndoRedo();
}

function updateUndoRedo() {
  undoButton.disabled = !history.canUndo || writing || store.picking;
  redoButton.disabled = !history.canRedo || writing || store.picking;
}

/** The photos to keep selected after a change: the targets that failed, to retry. */
function failedTargets(selected, targets, done) {
  const changed = new Set(done);
  const wanted = new Set(targets);
  return selected.filter((id) => wanted.has(id) && !changed.has(id));
}

async function finishChange({ action, selected, targetIds, before, after, skipped = 0, result }) {
  if (result.done.length) {
    rememberEdit({
      before: new Map(result.done.map((id) => [id, before.get(id)])),
      after: new Map(result.done.map((id) => [id, after.get(id)])),
      backups: result.backups,
      snapshot: result.snapshot,
    });
  } else {
    history.clear();
    updateUndoRedo();
  }
  store.select(failedTargets(selected, targetIds, result.done));
  if (result.backups.length) addEntries(result.backups.map((backup) => backup.entry));
  if (result.done.length) {
    setMessage(changeMessage({ action, count: result.done.length, skipped, backups: result.backups.length }), { tone: "success", undo: true });
  }
  if (result.failed.length) reportFailures(action === "apply" ? "apply GPS to" : "remove GPS from", result.failed);
}

async function applyLocation(state) {
  if (writing || !state?.canApply) return;
  const { targets, overwriteIds, newLocation } = state;
  let targetIds = targets;
  let skipped = 0;
  if (overwriteIds.length) {
    const entries = overwriteIds.map((id) => `${store.get(id).name}: ${formatCoordinates(store.get(id).gps)}`);
    const choice = await askOverwrite({
      question: overwriteQuestion(overwriteIds.length, targets.length - overwriteIds.length),
      entries,
      otherCount: targets.length - overwriteIds.length,
    });
    if (choice === "cancel") {
      setMessage("Nothing was changed.");
      return;
    }
    if (choice === "skip") {
      const keep = new Set(overwriteIds);
      targetIds = targets.filter((id) => !keep.has(id));
      skipped = keep.size;
    }
  }
  const selected = store.selectedIds();
  const snapshot = store.snapshot();
  const before = store.gpsStates(targetIds);
  const after = new Map(targetIds.map((id) => [id, newLocation]));
  const result = await writeStates(after, { text: "Applying GPS", makeBackups: true });
  await finishChange({ action: "apply", selected, targetIds, before, after, skipped, result: { ...result, snapshot } });
}

async function removeGps(state) {
  if (writing || !state?.canRemove) return;
  const ids = state.removeIds;
  if (!(await confirmRemoveGps(ids.map((id) => store.get(id).name)))) return;
  const selected = store.selectedIds();
  const snapshot = store.snapshot();
  const before = store.gpsStates(ids);
  const after = new Map(ids.map((id) => [id, null]));
  const result = await writeStates(after, { text: "Removing GPS", makeBackups: true });
  await finishChange({ action: "remove", selected, targetIds: ids, before, after, result: { ...result, snapshot } });
}

async function undo() {
  const states = history.undoStates();
  if (writing || !states.size) return;
  if (history.snapshot) {
    const readded = store.restoreSnapshot(history.snapshot);
    if (readded.length) queueReads(readded);
  }
  // Undo puts the photos back: it never backs up the version it's undoing.
  const result = await writeStates(states, { text: "Undoing the GPS change", makeBackups: false });
  const failed = [...result.failed, ...(await deleteBackups(history.backups))];
  history.markUndone();
  updateUndoRedo();
  if (history.snapshot) store.select(history.snapshot.selectedIds);
  setMessage("GPS change undone.");
  if (failed.length) reportFailures("undo the GPS change for", failed);
}

async function redo() {
  const states = history.redoStates();
  if (writing || !states.size) return;
  const result = await writeStates(states, { text: "Redoing the GPS change", makeBackups: true });
  history.setBackups(result.backups);
  history.markRedone();
  updateUndoRedo();
  if (result.backups.length) addEntries(result.backups.map((backup) => backup.entry));
  setMessage("GPS change redone.", { undo: true });
  if (result.failed.length) reportFailures("redo the GPS change for", result.failed);
}

function reportFailures(action, failures) {
  setMessage(`Could not ${action} ${failures.length} ${photosWord(failures.length)}.`, { tone: "error" });
  showFailures(action, failures);
}

// ----- downloads (photos without a file handle) -----

function triggerDownload(blob, name) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 60000);
}

async function downloadChanged() {
  const ids = store.pendingDownloadIds();
  if (!ids.length) return;
  try {
    if (ids.length === 1) {
      const photo = store.get(ids[0]);
      triggerDownload(new Blob([photo.bytes]), photo.name);
    } else {
      const entries = ids.map((id) => {
        const photo = store.get(id);
        return { name: photo.relPath, bytes: photo.bytes, date: new Date(photo.lastModified) };
      });
      triggerDownload(new Blob([buildStoredZip(entries)], { type: "application/zip" }), zipName());
    }
  } catch (error) {
    await showNotice("Could Not Download", String(error.message ?? error), "error");
    return;
  }
  // The files are out of the app's hands now: undo would change copies
  // nobody has, so the history ends here.
  store.markDownloaded(ids);
  history.clear();
  updateUndoRedo();
  setMessage(ids.length === 1 ? "1 photo downloaded. Replace the original on your computer with it." : `${ids.length} photos downloaded as a zip. Replace the originals on your computer with them.`, { tone: "success" });
}

// ----- the location source -----

function useLocationFromPhoto(id) {
  const photo = store.get(id);
  if (!photo?.gps) return false;
  changePane.location.setFields(photo.gps.latitude.toFixed(6), photo.gps.longitude.toFixed(6), { sourceId: id });
  setMessage(`Using the location from ${photo.name}. Now select the photos to change and click Apply.`, { tone: "success" });
  return true;
}

async function useLocationFromFile(file) {
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const reply = await exif.read(file.name, bytes);
    if (!reply.ok) {
      await showNotice("Could Not Read Photo", `Could not read GPS from ${file.name}: ${reply.error}`, "warning");
      return;
    }
    const gps = reply.tags.gps;
    if (!gps) {
      await showNotice("No GPS Coordinates", `${file.name} has no GPS coordinates.`);
      return;
    }
    changePane.location.setFields(gps.latitude.toFixed(6), gps.longitude.toFixed(6));
    setMessage(`Using the location from ${file.name}: ${formatCoordinates(gps)}.`, { tone: "success" });
  } catch (error) {
    await showNotice("Could Not Read Photo", String(error.message ?? error), "warning");
  }
}

function togglePick() {
  if (store.picking) store.setPicking(false);
  else if (store.pickableCount()) store.setPicking(true);
  updateUndoRedo();
}

// ----- the panes -----

const listView = createPhotoListView(document.getElementById("photoList"), store, {
  async openFolder() {
    try {
      const { folderName, entries } = await entriesFromFolderPicker();
      if (!entries.length) setMessage(`No photos in "${folderName}" or its subfolders.`);
      await addEntries(entries);
    } catch (error) {
      if (error?.name !== "AbortError") setMessage(`Could not open the folder: ${error.message ?? error}`, { tone: "error" });
    }
  },
  addFiles(files) {
    addEntries(entriesFromFileList(files));
  },
  async dropEntries(dataTransfer) {
    try {
      await addEntries(await entriesFromDrop(dataTransfer));
    } catch (error) {
      setMessage(`Could not read what was dropped: ${error.message ?? error}`, { tone: "error" });
    }
  },
  clearList() {
    cancelLoading();
    store.setPicking(false);
    store.clear();
    history.clear();
    updateUndoRedo();
    changePane.location.clearFields();
    setMessage("");
  },
  removeSelected() {
    const ids = store.selectedIds();
    store.remove(ids);
    setMessage(`${ids.length} ${photosWord(ids.length)} removed from the list`);
  },
  cancelLoading,
  pickPhoto(id) {
    if (useLocationFromPhoto(id)) store.setPicking(false);
    updateUndoRedo();
  },
  cancelPick: () => { if (store.picking) togglePick(); },
  undo,
  download: downloadChanged,
}, { canOpenFolder: saveMode === "inplace" });
listView.setPickPrompt(PICK_PROMPT);

const changePane = createChangePane(document.getElementById("photosToChange"), store, {
  saveModeText: modeText,
  locationActions: {
    parse: (op, a, b) => exif.parse(op, a, b),
    togglePick,
    locationFromFile: useLocationFromFile,
    apply: applyLocation,
    removeGps,
    message: (text, tone) => setMessage(text, { tone }),
  },
});

exif.onPythonReady = (reply) => changePane.location.setPythonReady(reply.ok, reply.error);

undoButton.addEventListener("click", undo);
redoButton.addEventListener("click", redo);
document.addEventListener("keydown", (event) => {
  if (!(event.ctrlKey || event.metaKey) || event.target.matches("input, textarea")) return;
  const key = event.key.toLowerCase();
  if (key === "z" && !event.shiftKey) { event.preventDefault(); undo(); }
  else if (key === "y" || (key === "z" && event.shiftKey)) { event.preventDefault(); redo(); }
});
store.subscribe((change) => { if (change.type === "view" || change.type === "removed") updateUndoRedo(); });
updateUndoRedo();

// A dropped file anywhere else must not open in the tab.
for (const type of ["dragover", "drop"]) {
  window.addEventListener(type, (event) => {
    if (event.target.closest?.(".pane-list")) return;
    event.preventDefault();
  });
}

// Leaving the page with changed photos not yet downloaded would lose them.
window.addEventListener("beforeunload", (event) => {
  if (store.pendingDownloadIds().length || writing) event.preventDefault();
});

// For automated checks against a local server only: the pieces a test
// drives without the native file pickers (see docs/ROADMAP.md, Tests).
if (["127.0.0.1", "localhost"].includes(location.hostname)) {
  window.fotofixerDebug = { store, history, addEntries, exif };
}
