// FotoFixer – When & Where, the web version: everything runs in the
// visitor's browser. This module wires the pieces together and runs the
// loading pipeline: file -> bytes -> ExifTool in the worker -> the Photo
// List, one photo at a time, with the thumbnail made on this thread.

import { PhotoStore } from "./photo_store.js";
import { createPhotoListView } from "./photo_list_view.js";
import { createSummaryView } from "./summary_view.js";
import { ExifClient } from "./exif_client.js";
import { detectSaveMode, saveModeText } from "./save_mode.js";
import { entriesFromFolderPicker, entriesFromFileList, entriesFromDrop } from "./file_sources.js";
import { thumbnailFromPreview, thumbnailFromFile } from "./thumbnails.js";
import { isJpegName, isHeifName } from "./file_types.js";
import { el } from "./dom.js";

const saveMode = detectSaveMode();
const modeText = saveModeText(saveMode);

// Header: the app name and which save mode this browser gets.
const modeBadge = document.getElementById("saveMode");
modeBadge.textContent = modeText.short;
modeBadge.title = modeText.long;
modeBadge.classList.add(saveMode);

const store = new PhotoStore();
const exif = new ExifClient(new URL("../worker/exif_worker.js", import.meta.url));

// ----- the loading pipeline -----

const readQueue = []; // ids waiting for ExifTool
let batch = null; // {done, total, openOnFinish} while a batch is being read
let reading = false;
let lastMessage = ""; // shown again once the progress row goes away

function photosWord(count) {
  return count === 1 ? "photo" : "photos";
}

async function addEntries(entries) {
  const wasEmpty = store.photos.size === 0;
  const { added, skipped } = store.add(entries);
  const parts = [];
  if (added.length) parts.push(`${added.length} ${photosWord(added.length)} added`);
  if (skipped) parts.push(`${skipped} already in the list`);
  if (!added.length && !skipped) parts.push("No photos found (JPG, HEIC, and camera RAW files are supported)");
  lastMessage = parts.join(" · ");
  listView.setMessage(lastMessage);
  if (!added.length) return;
  readQueue.push(...added);
  if (batch) batch.total += added.length;
  else batch = { done: 0, total: added.length, openOnFinish: wasEmpty, started: performance.now() };
  listView.setProgress(batch);
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
      listView.setProgress(batch);
    }
  }
  reading = false;
  const finished = batch;
  batch = null;
  listView.setMessage(lastMessage);
  if (finished) console.debug(`read ${finished.done} photos in ${((performance.now() - finished.started) / 1000).toFixed(1)} s`);
  // A list that was empty opens on Needs GPS (or All if none need GPS);
  // adding to a list keeps the current view.
  if (finished?.openOnFinish && store.photos.size) store.setView(store.openingView());
}

async function readPhoto(photo) {
  let file;
  const started = performance.now();
  try {
    file = await photo.getFile();
    const bytes = new Uint8Array(await file.arrayBuffer());
    const reply = await exif.read(photo.name, bytes);
    const readMs = Math.round(performance.now() - started);
    if (!store.get(photo.id)) return; // removed while being read
    if (!reply.ok) {
      store.setInfo(photo.id, { error: reply.error });
      return;
    }
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
    } else if (isJpegName(photo.name) || isHeifName(photo.name)) {
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

// ----- the panes -----

const listView = createPhotoListView(document.getElementById("photoList"), store, {
  async openFolder() {
    try {
      const { folderName, entries } = await entriesFromFolderPicker();
      if (!entries.length) listView.setMessage(`No photos in "${folderName}" or its subfolders.`);
      await addEntries(entries);
    } catch (error) {
      if (error?.name !== "AbortError") listView.setMessage(`Could not open the folder: ${error.message ?? error}`);
    }
  },
  addFiles(files) {
    addEntries(entriesFromFileList(files));
  },
  async dropEntries(dataTransfer) {
    try {
      await addEntries(await entriesFromDrop(dataTransfer));
    } catch (error) {
      listView.setMessage(`Could not read what was dropped: ${error.message ?? error}`);
    }
  },
  clearList() {
    cancelLoading();
    store.clear();
    listView.setMessage("");
  },
  removeSelected() {
    const ids = store.selectedIds();
    store.remove(ids);
    listView.setMessage(`${ids.length} ${photosWord(ids.length)} removed from the list`);
  },
  cancelLoading,
}, { canOpenFolder: saveMode === "inplace" });

createSummaryView(document.getElementById("photosToChange"), store, { saveModeText: modeText });

// A dropped file anywhere else must not open in the tab.
for (const type of ["dragover", "drop"]) {
  window.addEventListener(type, (event) => {
    if (event.target.closest?.(".pane-list")) return;
    event.preventDefault();
  });
}

// Unused but keeps the import list honest for the helper modules.
void el;
