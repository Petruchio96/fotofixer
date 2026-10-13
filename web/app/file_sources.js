// Where photos come from: an opened folder (File System Access API, with
// write access), file and folder inputs, and drag and drop. Each source
// yields entries the PhotoStore understands:
//
//   {name, relPath, size, lastModified, handle, getFile}
//
// handle is a FileSystemFileHandle when the browser gave one (Chrome/Edge:
// an opened or dropped folder or file), which later phases write back
// through; otherwise null and the photo can only be downloaded.

import { isSupportedName } from "./file_types.js";

function isHidden(name) {
  return name.startsWith(".");
}

function entryFromFile(file, relPath, handle = null) {
  return {
    name: file.name,
    relPath,
    size: file.size,
    lastModified: file.lastModified,
    handle,
    getFile: async () => (handle ? handle.getFile() : file),
  };
}

/** Walk a directory handle; subfolders too when recursive. */
export async function entriesFromDirectoryHandle(directory, { recursive = true, prefix = "" } = {}) {
  const entries = [];
  const base = prefix + directory.name + "/";
  for await (const [name, handle] of directory.entries()) {
    if (isHidden(name)) continue;
    if (handle.kind === "directory") {
      if (recursive) entries.push(...(await entriesFromDirectoryHandle(handle, { recursive, prefix: base })));
    } else if (isSupportedName(name)) {
      const file = await handle.getFile();
      entries.push(entryFromFile(file, base + name, handle));
    }
  }
  return entries;
}

/** A file input's files (a folder input gives webkitRelativePath). */
export function entriesFromFileList(files) {
  const entries = [];
  for (const file of files) {
    if (isHidden(file.name) || !isSupportedName(file.name)) continue;
    entries.push(entryFromFile(file, file.webkitRelativePath || file.name));
  }
  return entries;
}

// Drag and drop without file handles (Safari, Firefox): the older
// webkitGetAsEntry tree, read one folder at a time.
function readAllDirectoryEntries(reader) {
  return new Promise((resolve, reject) => {
    const all = [];
    const readBatch = () =>
      reader.readEntries((batch) => {
        if (!batch.length) resolve(all);
        else {
          all.push(...batch);
          readBatch();
        }
      }, reject);
    readBatch();
  });
}

function fileOfEntry(entry) {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

async function entriesFromLegacyEntry(entry, prefix) {
  if (isHidden(entry.name)) return [];
  if (entry.isFile) {
    if (!isSupportedName(entry.name)) return [];
    const file = await fileOfEntry(entry);
    return [entryFromFile(file, prefix + entry.name)];
  }
  if (entry.isDirectory) {
    const children = await readAllDirectoryEntries(entry.createReader());
    const out = [];
    for (const child of children) out.push(...(await entriesFromLegacyEntry(child, prefix + entry.name + "/")));
    return out;
  }
  return [];
}

/** The files and folders dropped on the page. */
export async function entriesFromDrop(dataTransfer) {
  const items = [...dataTransfer.items].filter((item) => item.kind === "file");
  const entries = [];
  for (const item of items) {
    if (typeof item.getAsFileSystemHandle === "function") {
      // Chrome/Edge: handles, so dropped photos can be saved in place too.
      const handle = await item.getAsFileSystemHandle();
      if (!handle) {
        // No handle for this item (for example a file from another app):
        // fall back to the plain File.
        const file = item.getAsFile();
        if (file && !isHidden(file.name) && isSupportedName(file.name)) entries.push(entryFromFile(file, file.name));
        continue;
      }
      if (handle.kind === "directory") {
        entries.push(...(await entriesFromDirectoryHandle(handle)));
      } else if (!isHidden(handle.name) && isSupportedName(handle.name)) {
        entries.push(entryFromFile(await handle.getFile(), handle.name, handle));
      }
    } else if (typeof item.webkitGetAsEntry === "function" && item.webkitGetAsEntry()) {
      entries.push(...(await entriesFromLegacyEntry(item.webkitGetAsEntry(), "")));
    } else {
      const file = item.getAsFile();
      if (file && !isHidden(file.name) && isSupportedName(file.name)) entries.push(entryFromFile(file, file.name));
    }
  }
  return entries;
}

/** Chrome/Edge: the folder picker, asking for write access. */
export async function entriesFromFolderPicker() {
  const directory = await window.showDirectoryPicker({ mode: "readwrite" });
  return { folderName: directory.name, entries: await entriesFromDirectoryHandle(directory) };
}
