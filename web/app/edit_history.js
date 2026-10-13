// Session-only undo/redo memory for GPS (and later date) edits: a port of
// services/gps_edit_history.py. Single-step: recording a new edit replaces
// the previous one. Lives in memory only.
//
// A state is the photo's GPS: {latitude, longitude} or null for none.
// Along with the states it keeps the Photo List as it was (which photos, in
// order, and which were selected) so undo and redo put the list back, and
// the backup files the edit made, which undo deletes (redo makes again).

export const EDIT_GPS = "gps";
export const EDIT_DATE = "date";

export class EditHistory {
  constructor() {
    this.clear();
  }

  clear() {
    this.before = new Map();
    this.after = new Map();
    this.kind = EDIT_GPS;
    this.snapshot = null; // {entries: [...], selectedIds: [...]}
    this.backups = []; // [{id, name, parent}] made by the edit
    this.undone = false;
  }

  /**
   * Remember an edit. Only photos present in both maps are kept, so photos
   * that failed to change are never "restored" by undo.
   */
  record({ before, after, snapshot = null, backups = [], kind = EDIT_GPS }) {
    const ids = [...after.keys()].filter((id) => before.has(id));
    this.before = new Map(ids.map((id) => [id, before.get(id)]));
    this.after = new Map(ids.map((id) => [id, after.get(id)]));
    this.snapshot = ids.length ? snapshot : null;
    this.backups = ids.length ? [...backups] : [];
    this.kind = kind;
    this.undone = false;
  }

  get canUndo() {
    return this.before.size > 0 && !this.undone;
  }

  get canRedo() {
    return this.after.size > 0 && this.undone;
  }

  /** States to write to undo the edit (empty if nothing to undo). */
  undoStates() {
    return this.canUndo ? new Map(this.before) : new Map();
  }

  /** States to write to redo the edit (empty if nothing to redo). */
  redoStates() {
    return this.canRedo ? new Map(this.after) : new Map();
  }

  markUndone() {
    this.undone = true;
  }

  markRedone() {
    this.undone = false;
  }

  /** After redo: the backups it made again, for the next undo. */
  setBackups(backups) {
    this.backups = [...backups];
  }

  /** The edit no longer applies to these photos (left the list for good). */
  forget(ids) {
    for (const id of ids) {
      this.before.delete(id);
      this.after.delete(id);
    }
    if (!this.before.size) this.clear();
  }
}
