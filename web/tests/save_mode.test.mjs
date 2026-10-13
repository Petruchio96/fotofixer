import { test } from "node:test";
import assert from "node:assert/strict";
import { detectSaveMode, saveModeText } from "../app/save_mode.js";

test("Chrome and Edge (showDirectoryPicker) save in place; everything else downloads", () => {
  assert.equal(detectSaveMode({ showDirectoryPicker() {} }), "inplace");
  assert.equal(detectSaveMode({}), "download");
  assert.equal(detectSaveMode({ showDirectoryPicker: undefined }), "download");
});

test("each mode explains itself", () => {
  assert.match(saveModeText("inplace").short, /saved straight into your files/);
  assert.match(saveModeText("download").short, /download/i);
  assert.match(saveModeText("download").long, /Chrome or Edge/);
});
