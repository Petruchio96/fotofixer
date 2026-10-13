import { test } from "node:test";
import assert from "node:assert/strict";
import { EditHistory } from "../app/edit_history.js";

const london = { latitude: 51.5007, longitude: -0.1246 };

test("records only photos in both maps and walks undo and redo", () => {
  const history = new EditHistory();
  assert.equal(history.canUndo, false);
  history.record({
    before: new Map([["a", null], ["b", london]]),
    after: new Map([["a", london], ["c", london]]),
    backups: [{ name: "x_original.jpg" }],
    snapshot: { entries: [], selectedIds: ["a"] },
  });
  assert.deepEqual([...history.undoStates().keys()], ["a"]);
  assert.equal(history.canUndo, true);
  assert.equal(history.canRedo, false);
  assert.equal(history.backups.length, 1);
  history.markUndone();
  assert.equal(history.canUndo, false);
  assert.deepEqual(history.redoStates().get("a"), london);
  history.setBackups([]);
  history.markRedone();
  assert.equal(history.canUndo, true);
  assert.equal(history.backups.length, 0);
});

test("an edit with nothing in common keeps no snapshot or backups", () => {
  const history = new EditHistory();
  history.record({ before: new Map([["a", null]]), after: new Map([["b", london]]), backups: [{}], snapshot: { selectedIds: [] } });
  assert.equal(history.canUndo, false);
  assert.equal(history.snapshot, null);
  assert.deepEqual(history.backups, []);
});

test("forgetting photos shrinks or clears the edit", () => {
  const history = new EditHistory();
  history.record({ before: new Map([["a", null], ["b", null]]), after: new Map([["a", london], ["b", london]]) });
  history.forget(["a"]);
  assert.deepEqual([...history.undoStates().keys()], ["b"]);
  history.forget(["b"]);
  assert.equal(history.canUndo, false);
});
