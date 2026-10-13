// The Photo List's state: the photos, what is known about each one, the
// selection, the Show filter (Location) or camera filter (Date & Time),
// the source photo, and pick mode. Plain JavaScript with no DOM, so Node's
// test runner checks it (web/tests/photo_store.test.mjs). The rules follow
// the desktop app's Photo List (gui/window_mixins/photo_list.py,
// location_editor.py, date_time_editor.py, and
// gui/presenters/inspector_state.py).

export const VIEWS = ["all", "needs", "has"];
export const UNKNOWN_CAMERA = "Unknown Camera";

/** Two entries are the same photo when their path, size, and date match. */
export function photoKey(entry) {
  return `${entry.relPath}|${entry.size}|${entry.lastModified}`;
}

function naturalCompare(a, b) {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
}

function caseless(a, b) {
  return a.toLowerCase() < b.toLowerCase() ? -1 : a.toLowerCase() > b.toLowerCase() ? 1 : 0;
}

export function sameGps(a, b) {
  if (a == null || b == null) return a == null && b == null;
  return a.latitude === b.latitude && a.longitude === b.longitude;
}

// The tags a date change writes (core/photo_dates.py DATE_TAKEN_TAGS and
// OFFSET_TAGS); a missing tag and a null one are the same thing.
const DATE_TAGS = ["DateTimeOriginal", "CreateDate", "ModifyDate", "OffsetTimeOriginal", "OffsetTimeDigitized", "OffsetTime"];

export function sameDates(a, b) {
  return DATE_TAGS.every((tag) => (a?.[tag] ?? null) === (b?.[tag] ?? null));
}

/** Cameras sorted by name, Unknown Camera last (services/date_time_service.py). */
export function sortCameras(cameras) {
  return [...cameras].sort((a, b) => (a === UNKNOWN_CAMERA) - (b === UNKNOWN_CAMERA) || caseless(a, b));
}

export class PhotoStore {
  constructor() {
    this.photos = new Map(); // id -> photo
    this.order = []; // ids in list order
    this.selection = new Set();
    // "location" (GPS groups, the Show filter) or "date" (camera groups,
    // the camera filter): the list follows the Photos to Change tab.
    this.mode = "location";
    this.view = "all";
    this.cameraFilter = "all";
    // While "Only Show Selected Photos" is on: the ids it showed when it was
    // turned on (photos deselected since stay visible, faded). null = off.
    this.onlySelectedIds = null;
    // The photo the New Location was copied from: a photo is either the
    // source or being changed, never both, so it can't be selected.
    this.sourceId = null;
    // The photo the correct time was copied from (Date & Time): it can be
    // selected; Shift leaves it out.
    this.timeSourceId = null;
    // Pick mode: "location" (From a Photo in the Photo List on the Location
    // tab: the grid shows Has GPS) or "time" (the Date & Time tab: the view
    // stays). Remembers what to put back after.
    this.picking = null;
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
        dates: null, // the date tags as ExifTool text (tag -> text | null)
        make: null,
        model: null,
        // From the Python bridge's describe: for the Date & Time mode.
        dateTaken: null, // ISO text, for sorting
        dateText: "", // "10/03/2026 9:14:02am"
        offsetText: "", // "MDT"
        camera: null,
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
    if (photo.originalGps === undefined && !info.error) {
      photo.originalGps = photo.gps ?? null;
      photo.originalDates = { ...(photo.dates ?? {}) };
    }
    this._emit({ type: "info", id });
  }

  /** What the Date & Time mode shows (from the bridge's describe). */
  setDescription(id, description) {
    const photo = this.photos.get(id);
    if (!photo) return;
    Object.assign(photo, description);
    this._emit({ type: "info", id });
  }

  /**
   * After a write: the photo's GPS now and, in download mode, the changed
   * file. A photo waits for Download only while it differs from the
   * version the visitor has (the original file, or the last download); an
   * undo back to that state drops the changed bytes.
   */
  setGps(id, gps, bytes = null) {
    const photo = this.photos.get(id);
    if (!photo) return;
    photo.gps = gps;
    if (bytes) this._setBytes(photo, bytes, this._atBaseline(photo));
    this._emit({ type: "info", id });
  }

  /** Back to the version the visitor has: the same GPS and the same date tags. */
  _atBaseline(photo) {
    return sameGps(photo.gps, photo.originalGps ?? null) && sameDates(photo.dates, photo.originalDates);
  }

  /** After a date write: the tags written ("" deletes) merged into the photo's. */
  setDates(id, tags, bytes = null) {
    const photo = this.photos.get(id);
    if (!photo) return;
    const dates = { ...(photo.dates ?? {}) };
    for (const [tag, value] of Object.entries(tags)) {
      if (tag.includes(":")) continue; // QuickTime copies: not kept per tag
      dates[tag] = value === "" || value === null ? null : value;
    }
    photo.dates = dates;
    if (bytes) this._setBytes(photo, bytes, this._atBaseline(photo));
    this._emit({ type: "info", id });
  }

  _setBytes(photo, bytes, backToBaseline) {
    photo.pendingDownload = !backToBaseline;
    photo.bytes = photo.pendingDownload || photo.downloaded ? bytes : null;
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
      photo.originalDates = { ...(photo.dates ?? {}) };
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
      if (this.timeSourceId === id) this.timeSourceId = null;
    }
    this.order = this.order.filter((id) => !removing.has(id));
    if (this.onlySelectedIds && this.onlySelectedIds.size === 0) this.onlySelectedIds = null;
    if (this.cameraFilter !== "all" && !this.cameras().includes(this.cameraFilter)) this.cameraFilter = "all";
    this._emit({ type: "removed", ids: [...removing] });
  }

  clear() {
    const ids = [...this.order];
    this.photos.clear();
    this.order = [];
    this.selection.clear();
    this.onlySelectedIds = null;
    this.sourceId = null;
    this.timeSourceId = null;
    this.view = "all";
    this.cameraFilter = "all";
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

  hasDate(id) {
    return Boolean(this.photos.get(id)?.dateTaken);
  }

  cameraOf(id) {
    return this.photos.get(id)?.camera || UNKNOWN_CAMERA;
  }

  /** The cameras in the list, sorted by name, Unknown Camera last. */
  cameras() {
    return sortCameras(new Set(this.order.map((id) => this.cameraOf(id))));
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

  // ----- the mode and filters -----

  /** The Photos to Change tab: "location" or "date". The selection is kept. */
  setMode(mode) {
    if (mode === this.mode) return;
    this.mode = mode;
    this.onlySelectedIds = null;
    this._emit({ type: "view" });
  }

  setView(view) {
    if (!VIEWS.includes(view)) throw new Error(`unknown view ${view}`);
    this.view = view;
    // Clicking a view button turns Only Show Selected Photos off.
    this.onlySelectedIds = null;
    this._emit({ type: "view" });
  }

  /** Date & Time mode: "all" or one camera's name. */
  setCameraFilter(camera) {
    this.cameraFilter = camera;
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
    if (this.picking === "location") return this.hasGps(id);
    if (this.mode === "date") return this.cameraFilter === "all" || this.cameraOf(id) === this.cameraFilter;
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
   * The grid's groups in order. Location: photos without GPS first, then
   * with, each under a heading with its count. Date & Time: one group per
   * camera (sorted by name, Unknown Camera last), photos in date order
   * (then by name), photos without a date last.
   */
  groups() {
    if (this.mode === "date") return this._cameraGroups();
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

  _cameraGroups() {
    const byCamera = new Map();
    for (const id of this.visibleIds()) {
      const camera = this.cameraOf(id);
      if (!byCamera.has(camera)) byCamera.set(camera, []);
      byCamera.get(camera).push(id);
    }
    const totals = new Map();
    for (const id of this.order) totals.set(this.cameraOf(id), (totals.get(this.cameraOf(id)) ?? 0) + 1);
    return sortCameras(byCamera.keys()).map((camera) => {
      const ids = byCamera.get(camera).sort((a, b) => {
        const pa = this.photos.get(a);
        const pb = this.photos.get(b);
        if (Boolean(pa.dateTaken) !== Boolean(pb.dateTaken)) return pa.dateTaken ? -1 : 1;
        if (pa.dateTaken !== pb.dateTaken) return pa.dateTaken < pb.dateTaken ? -1 : 1;
        return caseless(pa.name, pb.name);
      });
      return { key: `camera:${camera}`, camera, title: `${camera} (${totals.get(camera)})`, ids };
    });
  }

  /** Why the grid is empty, or "" when it is not. */
  emptyMessage() {
    if (this.visibleIds().length) return "";
    if (!this.photos.size) return 'Click "+ Add Photos" to get started, or drop photos here.';
    if (this.picking === "location") return "No photo here has GPS to copy.";
    if (this.onlySelectedIds) return "No photos are selected.";
    if (this.mode === "date") return "No photos from this camera.";
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

  /** A camera heading's checkbox: select or deselect every photo from it. */
  selectCamera(camera, on) {
    for (const id of this.order) {
      if (this.cameraOf(id) !== camera || !this.canSelect(id)) continue;
      if (on) this.selection.add(id);
      else this.selection.delete(id);
    }
    this._emit({ type: "selection" });
  }

  /** Whether every photo from a camera is selected (for its checkbox). */
  cameraSelected(camera) {
    const ids = this.order.filter((id) => this.cameraOf(id) === camera && this.canSelect(id));
    return ids.length > 0 && ids.every((id) => this.selection.has(id));
  }

  selectedIds() {
    return this.order.filter((id) => this.selection.has(id));
  }

  // ----- the sources and pick mode -----

  /** Make a photo the location source (it is deselected), or null for none. */
  setSource(id) {
    this.sourceId = id;
    if (id !== null) this.selection.delete(id);
    this._emit({ type: "selection" });
  }

  /** The photo whose time is used (Date & Time); it stays selectable. */
  setTimeSource(id) {
    this.timeSourceId = id;
    this._emit({ type: "selection" });
  }

  /** The source marked SOURCE in the grid: the one for the current tab. */
  markedSourceId() {
    return this.mode === "date" ? this.timeSourceId : this.sourceId;
  }

  /** Photos that can be the location source: with GPS and not selected to change. */
  pickableCount() {
    return this.order.filter((id) => this.hasGps(id) && !this.selection.has(id)).length;
  }

  /** Photos whose time can be used: with a date and not selected. */
  timePickableCount() {
    return this.order.filter((id) => this.hasDate(id) && !this.selection.has(id)).length;
  }

  /** While picking: why a photo can't be picked ("No GPS", "No Date", "Being Changed"), or "". */
  pickLabel(id) {
    if (!this.picking) return "";
    if (this.picking === "time") {
      if (!this.hasDate(id)) return "No Date";
    } else if (!this.hasGps(id)) {
      return "No GPS";
    }
    return this.selection.has(id) ? "Being Changed" : "";
  }

  /** Enter pick mode ("location" or "time"), or leave it (null). */
  setPicking(kind) {
    if (kind === this.picking) return;
    if (kind) {
      this._beforePick = { view: this.view, onlySelectedIds: this.onlySelectedIds };
      this.onlySelectedIds = null;
      this.picking = kind;
    } else {
      this.picking = null;
      if (this._beforePick) {
        this.view = this._beforePick.view;
        // Only Show Selected Photos comes back if there is still a selection.
        this.onlySelectedIds = this._beforePick.onlySelectedIds && this.selection.size ? new Set(this.selection) : null;
      }
      this._beforePick = null;
    }
    this._emit({ type: "view" });
  }

  // ----- the summary above the Photos to Change tabs (Location) -----

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
export function tileTooltip(photo, { isSource = false, pickLabel = "", dateMode = false } = {}) {
  let where = "No GPS";
  if (photo.gps) where = `GPS: ${formatCoordinates(photo.gps)}`;
  else if (photo.status === "error") where = `Could not be read: ${photo.error}`;
  else if (photo.status === "pending") where = "Reading…";
  const lines = [photo.name];
  if (dateMode && photo.status === "ready") {
    lines.push(photo.dateTaken ? `Taken ${photo.dateText}${photo.offsetText ? ` ${photo.offsetText}` : ""}` : "No date");
    lines.push(photo.camera || UNKNOWN_CAMERA);
  } else {
    lines.push(where);
  }
  if (isSource) lines.push(dateMode ? "The time comes from this photo; it is never changed itself." : "The New Location comes from this photo, so it can't be selected to change.");
  else if (pickLabel === "No GPS") lines.push("No GPS to copy.");
  else if (pickLabel === "No Date") lines.push("No date to copy.");
  else if (pickLabel === "Being Changed") lines.push("Selected to change, so it can't be the source too.");
  else if (pickLabel === "" && photo.pendingDownload) lines.push("Changed; waiting for Download.");
  lines.push(isSource && !dateMode ? "" : "Click to select or deselect; Shift-click to select a range");
  return lines.filter(Boolean).join("\n");
}
