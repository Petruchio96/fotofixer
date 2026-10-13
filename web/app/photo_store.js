// The Photo List's state: the photos, what is known about each one, the
// selection, the Show filter, the location source, and pick mode. Plain
// JavaScript with no DOM, so Node's test runner checks it
// (web/tests/photo_store.test.mjs). The rules follow the desktop app's
// Photo List (gui/window_mixins/photo_list.py, location_editor.py, and
// gui/presenters/inspector_state.py).

export const VIEWS = ["all", "needs", "has"];

/** Two entries are the same photo when their path, size, and date match. */
export function photoKey(entry) {
  return `${entry.relPath}|${entry.size}|${entry.lastModified}`;
}

function naturalCompare(a, b) {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
}

export function sameGps(a, b) {
  if (a == null || b == null) return a == null && b == null;
  return a.latitude === b.latitude && a.longitude === b.longitude;
}

export class PhotoStore {
  constructor() {
    this.photos = new Map(); // id -> photo
    this.order = []; // ids in list order
    this.selection = new Set();
    this.view = "all";
    // While "Only Show Selected Photos" is on: the ids it showed when it was
    // turned on (photos deselected since stay visible, faded). null = off.
    this.onlySelectedIds = null;
    // The photo the New Location was copied from: a photo is either the
    // source or being changed, never both, so it can't be selected.
    this.sourceId = null;
    // Pick mode ("From a Photo in the Photo List"): the grid shows Has GPS
    // and a click copies a location. Remembers what to put back after.
    this.picking = false;
    this._beforePick = null;
    this.listeners = new Set();
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  _emit(change) {
    for (const listener of this.listeners) listener(change, this);
  }

  // ----- the list -----

  /**
   * Add entries ({name, relPath, size, lastModified, getFile, handle,
   * parent}). Photos already in the list are skipped. Each batch is sorted
   * by path so a folder's photos appear in name order.
   */
  add(entries) {
    const added = [];
    let skipped = 0;
    const sorted = [...entries].sort((a, b) => naturalCompare(a.relPath, b.relPath));
    for (const entry of sorted) {
      const id = photoKey(entry);
      if (this.photos.has(id)) {
        skipped += 1;
        continue;
      }
      this.photos.set(id, {
        ...entry,
        id,
        status: "pending", // "pending" | "ready" | "error"
        gps: null, // {latitude, longitude} once read
        originalGps: undefined, // the GPS when first read (for download mode)
        dates: null, // the date tags as ExifTool text, for later phases
        make: null,
        model: null,
        error: null,
        thumb: null, // a blob: URL once the thumbnail exists
        thumbFailed: false,
        // Download mode: the changed file, until it is downloaded.
        bytes: null,
        pendingDownload: false,
        downloaded: false,
      });
      this.order.push(id);
      added.push(id);
    }
    if (added.length) this._emit({ type: "added", ids: added });
    return { added, skipped };
  }

  get(id) {
    return this.photos.get(id);
  }

  /** What ExifTool found: {gps, dates, make, model} or {error}. */
  setInfo(id, info) {
    const photo = this.photos.get(id);
    if (!photo) return;
    Object.assign(photo, info, { status: info.error ? "error" : "ready" });
    if (photo.originalGps === undefined && !info.error) photo.originalGps = photo.gps ?? null;
    this._emit({ type: "info", id });
  }

  /**
   * After a write: the photo's GPS now and, in download mode, the changed
   * file. A photo waits for Download only while its GPS differs from the
   * version the visitor has (the original file, or the last download); an
   * undo back to that state drops the changed bytes.
   */
  setGps(id, gps, bytes = null) {
    const photo = this.photos.get(id);
    if (!photo) return;
    photo.gps = gps;
    if (bytes) {
      photo.pendingDownload = !sameGps(gps, photo.originalGps ?? null);
      // Never downloaded and back to the original: the original file will do.
      photo.bytes = photo.pendingDownload || photo.downloaded ? bytes : null;
    }
    this._emit({ type: "info", id });
  }

  setThumb(id, url) {
    const photo = this.photos.get(id);
    if (!photo) return;
    photo.thumb = url;
    photo.thumbFailed = url === null;
    this._emit({ type: "thumb", id });
  }

  /** The changed photos waiting for Download. */
  pendingDownloadIds() {
    return this.order.filter((id) => this.photos.get(id).pendingDownload);
  }

  /** The visitor has these changed photos now: they become the baseline. */
  markDownloaded(ids) {
    for (const id of ids) {
      const photo = this.photos.get(id);
      if (!photo) continue;
      photo.pendingDownload = false;
      photo.downloaded = true;
      photo.originalGps = photo.gps;
    }
    this._emit({ type: "downloads" });
  }

  remove(ids) {
    const removing = new Set(ids);
    for (const id of removing) {
      this.photos.delete(id);
      this.selection.delete(id);
      this.onlySelectedIds?.delete(id);
      if (this.sourceId === id) this.sourceId = null;
    }
    this.order = this.order.filter((id) => !removing.has(id));
    if (this.onlySelectedIds && this.onlySelectedIds.size === 0) this.onlySelectedIds = null;
    this._emit({ type: "removed", ids: [...removing] });
  }

  clear() {
    const ids = [...this.order];
    this.photos.clear();
    this.order = [];
    this.selection.clear();
    this.onlySelectedIds = null;
    this.sourceId = null;
    this.view = "all";
    this._emit({ type: "removed", ids });
  }

  /** The list as it is, to put back after undo/redo. */
  snapshot() {
    return {
      entries: this.order.map((id) => this.photos.get(id)),
      selectedIds: this.selectedIds(),
    };
  }

  /** Put a snapshot's photos back (re-adding ones removed since) and reselect. */
  restoreSnapshot(snapshot) {
    const missing = snapshot.entries.filter((photo) => !this.photos.has(photo.id));
    const readded = [];
    if (missing.length) readded.push(...this.add(missing.map((photo) => ({ ...photo, status: "pending", thumb: null }))).added);
    this.selection = new Set(snapshot.selectedIds.filter((id) => this.photos.has(id) && id !== this.sourceId));
    this._emit({ type: "selection" });
    return readded;
  }

  // ----- what is known -----

  hasGps(id) {
    return this.photos.get(id)?.gps != null;
  }

  counts() {
    let has = 0;
    let pending = 0;
    for (const photo of this.photos.values()) {
      if (photo.gps) has += 1;
      if (photo.status === "pending") pending += 1;
    }
    return { total: this.photos.size, has, needs: this.photos.size - has, pending };
  }

  /** The view a list opens on after its first photos load. */
  openingView() {
    return this.counts().needs > 0 ? "needs" : "all";
  }

  gpsStates(ids) {
    return new Map(ids.map((id) => [id, this.photos.get(id)?.gps ?? null]));
  }

  // ----- the Show filter -----

  setView(view) {
    if (!VIEWS.includes(view)) throw new Error(`unknown view ${view}`);
    this.view = view;
    // Clicking a view button turns Only Show Selected Photos off.
    this.onlySelectedIds = null;
    this._emit({ type: "view" });
  }

  get onlySelected() {
    return this.onlySelectedIds !== null;
  }

  setOnlySelected(on) {
    this.onlySelectedIds = on && this.selection.size ? new Set(this.selection) : null;
    this._emit({ type: "view" });
  }

  _inView(id) {
    if (this.picking) return this.hasGps(id);
    if (this.onlySelectedIds) return this.onlySelectedIds.has(id);
    if (this.view === "needs") return !this.hasGps(id);
    if (this.view === "has") return this.hasGps(id);
    return true;
  }

  /** A photo shown because of Only Show Selected Photos but deselected since. */
  isFaded(id) {
    return this.onlySelectedIds !== null && !this.picking && !this.selection.has(id);
  }

  visibleIds() {
    return this.order.filter((id) => this._inView(id));
  }

  /**
   * The grid's groups in order: photos without GPS first, then photos with
   * GPS, each under a heading with its count. Empty groups are left out.
   */
  groups() {
    const needs = [];
    const has = [];
    for (const id of this.visibleIds()) (this.hasGps(id) ? has : needs).push(id);
    const counts = this.counts();
    const groups = [];
    if (needs.length) {
      groups.push({ key: "needs", title: `Photos without GPS Coordinates (${counts.needs})`, ids: needs });
    }
    if (has.length) {
      groups.push({ key: "has", title: `Photos with GPS Coordinates (${counts.has})`, ids: has });
    }
    return groups;
  }

  /** Why the grid is empty, or "" when it is not. */
  emptyMessage() {
    if (this.visibleIds().length) return "";
    if (!this.photos.size) return 'Click "+ Add Photos" to get started, or drop photos here.';
    if (this.picking) return "No photo here has GPS to copy.";
    if (this.onlySelectedIds) return "No photos are selected.";
    if (this.view === "needs") return "No photos need GPS. Every photo shown here has coordinates.";
    if (this.view === "has") return "None of these photos have GPS yet.";
    return "";
  }

  // ----- the selection -----

  canSelect(id) {
    return this.photos.has(id) && id !== this.sourceId;
  }

  toggle(id) {
    if (!this.canSelect(id)) return;
    if (this.selection.has(id)) this.selection.delete(id);
    else this.selection.add(id);
    this._emit({ type: "selection" });
  }

  /** Shift-click: select every visible photo from the anchor to this one. */
  selectRange(anchorId, id) {
    const visible = this.visibleIds();
    const from = visible.indexOf(anchorId);
    const to = visible.indexOf(id);
    if (from < 0 || to < 0) return this.toggle(id);
    const [low, high] = from < to ? [from, to] : [to, from];
    for (const member of visible.slice(low, high + 1)) if (this.canSelect(member)) this.selection.add(member);
    this._emit({ type: "selection" });
  }

  /** Select every photo shown (not the ones hidden by the filter, nor the source). */
  selectAll() {
    for (const id of this.visibleIds()) if (this.canSelect(id)) this.selection.add(id);
    this._emit({ type: "selection" });
  }

  deselectAll() {
    this.selection.clear();
    this._emit({ type: "selection" });
  }

  /** Select exactly these (after a change: the photos that failed, to retry). */
  select(ids) {
    this.selection = new Set(ids.filter((id) => this.canSelect(id)));
    this._emit({ type: "selection" });
  }

  selectedIds() {
    return this.order.filter((id) => this.selection.has(id));
  }

  // ----- the location source and pick mode -----

  /** Make a photo the location source (it is deselected), or null for none. */
  setSource(id) {
    this.sourceId = id;
    if (id !== null) this.selection.delete(id);
    this._emit({ type: "selection" });
  }

  /** Photos that can be the location source: with GPS and not selected to change. */
  pickableCount() {
    return this.order.filter((id) => this.hasGps(id) && !this.selection.has(id)).length;
  }

  /** While picking: why a photo can't be picked ("No GPS", "Being Changed"), or "". */
  pickLabel(id) {
    if (!this.picking) return "";
    if (!this.hasGps(id)) return "No GPS";
    return this.selection.has(id) ? "Being Changed" : "";
  }

  setPicking(on) {
    if (on === this.picking) return;
    if (on) {
      this._beforePick = { view: this.view, onlySelectedIds: this.onlySelectedIds };
      this.onlySelectedIds = null;
      this.picking = true;
    } else {
      this.picking = false;
      if (this._beforePick) {
        this.view = this._beforePick.view;
        // Only Show Selected Photos comes back if there is still a selection.
        this.onlySelectedIds = this._beforePick.onlySelectedIds && this.selection.size ? new Set(this.selection) : null;
      }
      this._beforePick = null;
    }
    this._emit({ type: "view" });
  }

  // ----- the summary above the Photos to Change tabs -----

  summary() {
    const selected = this.selectedIds();
    const count = selected.length;
    if (count === 0) {
      return { title: "No Photos Selected", text: "Click photos in the Photo List to select them." };
    }
    if (count === 1) {
      const photo = this.photos.get(selected[0]);
      const text = photo.gps
        ? `${photo.name} · GPS: ${formatCoordinates(photo.gps)}`
        : `${photo.name} · No GPS`;
      return { title: "1 Photo Selected", text };
    }
    const withGps = selected.filter((id) => this.hasGps(id)).length;
    return {
      title: `${count} Photos Selected`,
      text: `${count - withGps} without GPS · ${withGps} with GPS`,
    };
  }
}

export function formatCoordinates(gps) {
  return `${gps.latitude.toFixed(6)}, ${gps.longitude.toFixed(6)}`;
}

/** The hover text of a tile. */
export function tileTooltip(photo, { isSource = false, pickLabel = "" } = {}) {
  let where = "No GPS";
  if (photo.gps) where = `GPS: ${formatCoordinates(photo.gps)}`;
  else if (photo.status === "error") where = `Could not be read: ${photo.error}`;
  else if (photo.status === "pending") where = "Reading…";
  const lines = [photo.name, where];
  if (isSource) lines.push("The New Location comes from this photo, so it can't be selected to change.");
  else if (pickLabel === "No GPS") lines.push("No GPS to copy.");
  else if (pickLabel === "Being Changed") lines.push("Selected to change, so it can't be the source too.");
  else if (pickLabel === "" && photo.pendingDownload) lines.push("Changed; waiting for Download.");
  lines.push(isSource ? "" : "Click to select or deselect; Shift-click to select a range");
  return lines.filter(Boolean).join("\n");
}
