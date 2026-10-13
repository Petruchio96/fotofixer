// The Photo List's state: the photos, what is known about each one, the
// selection, and the Show filter. Plain JavaScript with no DOM, so Node's
// test runner checks it (web/tests/photo_store.test.mjs). The rules follow
// the desktop app's Photo List (gui/window_mixins/photo_list.py and
// gui/presenters/inspector_state.py).

export const VIEWS = ["all", "needs", "has"];

/** Two entries are the same photo when their path, size, and date match. */
export function photoKey(entry) {
  return `${entry.relPath}|${entry.size}|${entry.lastModified}`;
}

function naturalCompare(a, b) {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
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
   * Add entries ({name, relPath, size, lastModified, getFile, handle}).
   * Photos already in the list are skipped. Each batch is sorted by path so
   * a folder's photos appear in name order.
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
        dates: null, // the date tags as ExifTool text, for later phases
        make: null,
        model: null,
        error: null,
        thumb: null, // a blob: URL once the thumbnail exists
        thumbFailed: false,
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
    this._emit({ type: "info", id });
  }

  setThumb(id, url) {
    const photo = this.photos.get(id);
    if (!photo) return;
    photo.thumb = url;
    photo.thumbFailed = url === null;
    this._emit({ type: "thumb", id });
  }

  remove(ids) {
    const removing = new Set(ids);
    for (const id of removing) {
      this.photos.delete(id);
      this.selection.delete(id);
      this.onlySelectedIds?.delete(id);
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
    this.view = "all";
    this._emit({ type: "removed", ids });
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
    if (this.onlySelectedIds) return this.onlySelectedIds.has(id);
    if (this.view === "needs") return !this.hasGps(id);
    if (this.view === "has") return this.hasGps(id);
    return true;
  }

  /** A photo shown because of Only Show Selected Photos but deselected since. */
  isFaded(id) {
    return this.onlySelectedIds !== null && !this.selection.has(id);
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
    if (this.onlySelectedIds) return "No photos are selected.";
    if (this.view === "needs") return "No photos need GPS. Every photo shown here has coordinates.";
    if (this.view === "has") return "None of these photos have GPS yet.";
    return "";
  }

  // ----- the selection -----

  toggle(id) {
    if (!this.photos.has(id)) return;
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
    for (const member of visible.slice(low, high + 1)) this.selection.add(member);
    this._emit({ type: "selection" });
  }

  /** Select every photo shown (not the ones hidden by the filter). */
  selectAll() {
    for (const id of this.visibleIds()) this.selection.add(id);
    this._emit({ type: "selection" });
  }

  deselectAll() {
    this.selection.clear();
    this._emit({ type: "selection" });
  }

  selectedIds() {
    return this.order.filter((id) => this.selection.has(id));
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
export function tileTooltip(photo) {
  let where = "No GPS";
  if (photo.gps) where = `GPS: ${formatCoordinates(photo.gps)}`;
  else if (photo.status === "error") where = `Could not be read: ${photo.error}`;
  else if (photo.status === "pending") where = "Reading…";
  return `${photo.name}\n${where}\nClick to select or deselect; Shift-click to select a range`;
}
