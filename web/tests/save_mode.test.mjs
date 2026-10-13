import { test } from "node:test";
import assert from "node:assert/strict";
import { detectSaveMode, saveModeText, photoSavesInPlace, zipName, downloadBarText, downloadButtonLabel, backupName, isBackupName } from "../app/save_mode.js";

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

test("a photo saves in place only with a file handle", () => {
  assert.equal(photoSavesInPlace({ handle: {} }), true);
  assert.equal(photoSavesInPlace({ handle: null }), false);
});

test("download names and texts", () => {
  assert.equal(zipName(new Date(2026, 9, 13, 4, 7)), "fotofixer-changed-photos-20261013-0407.zip");
  assert.equal(downloadBarText(1), "1 changed photo ready to download");
  assert.equal(downloadBarText(3), "3 changed photos ready to download");
  assert.equal(downloadButtonLabel(1), "Download 1 Photo");
  assert.equal(downloadButtonLabel(3), "Download 3 Photos (.zip)");
});

test("backup names", () => {
  assert.equal(backupName("IMG_0995.jpg"), "IMG_0995_original.jpg");
  assert.equal(backupName("noext"), "noext_original");
  assert.equal(isBackupName("IMG_0995_original.jpg"), true);
  assert.equal(isBackupName("IMG_0995.jpg"), false);
});
