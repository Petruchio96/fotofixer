// How changed photos get back to the visitor's computer. Plain functions
// (no DOM) so the tests can check them.
//
// "inplace":  the browser has the File System Access API (Chrome and Edge
//             on a computer): an opened folder is read-write, and changes
//             go straight into the original files.
// "download": every other browser (Safari, Firefox, iPads): the app can
//             read the files it is given but not write them, so changed
//             photos come back as downloads.
//
// Within a Chrome/Edge session both can occur: photos from an opened or
// dropped folder have a file handle (saved in place); photos from the file
// inputs don't (downloaded).

export function detectSaveMode(env = globalThis) {
  return typeof env.showDirectoryPicker === "function" ? "inplace" : "download";
}

export function saveModeText(mode) {
  if (mode === "inplace") {
    return {
      short: "Changes are saved straight into your files",
      long: "Your photos stay on this computer. Changes are saved straight into the files in the folder you open; photos chosen with Choose Photos download instead.",
    };
  }
  return {
    short: "Changed photos download when you click Download",
    long: "Your photos stay on this computer. This browser can't write into your files, so changed photos download when you click Download. For saving in place, use Chrome or Edge on a computer.",
  };
}

/** A photo is saved in place when the browser gave a writable handle for it. */
export function photoSavesInPlace(photo) {
  return photo.handle != null;
}

const pad = (n) => String(n).padStart(2, "0");

/** The zip's name when several changed photos download together. */
export function zipName(now = new Date()) {
  return `fotofixer-changed-photos-${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}.zip`;
}

/** The download bar's text. */
export function downloadBarText(count) {
  return count === 1 ? "1 changed photo ready to download" : `${count} changed photos ready to download`;
}

export function downloadButtonLabel(count) {
  return count === 1 ? "Download 1 Photo" : `Download ${count} Photos (.zip)`;
}

/** The backup copy's name: IMG_0995.jpg -> IMG_0995_original.jpg. */
export function backupName(name) {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? `${name}_original` : `${name.slice(0, dot)}_original${name.slice(dot)}`;
}

export function isBackupName(name) {
  const dot = name.lastIndexOf(".");
  return (dot < 0 ? name : name.slice(0, dot)).endsWith("_original");
}
