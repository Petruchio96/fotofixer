// How changed photos get back to the visitor's computer. Plain functions
// (no DOM) so the tests can check them.
//
// "inplace":  the browser has the File System Access API (Chrome and Edge
//             on a computer): an opened folder is read-write, and changes
//             go straight into the original files.
// "download": every other browser (Safari, Firefox, iPads): the app can
//             read the files it is given but not write them, so changed
//             photos come back as downloads.

export function detectSaveMode(env = globalThis) {
  return typeof env.showDirectoryPicker === "function" ? "inplace" : "download";
}

export function saveModeText(mode) {
  if (mode === "inplace") {
    return {
      short: "Changes are saved straight into your files",
      long: "Your photos stay on this computer. Changes are saved straight into the files in the folder you open.",
    };
  }
  return {
    short: "Changed photos download when you click Download",
    long: "Your photos stay on this computer. This browser can't write into your files, so changed photos download when you click Download. For saving in place, use Chrome or Edge on a computer.",
  };
}
