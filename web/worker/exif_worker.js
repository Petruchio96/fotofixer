// ExifTool (WebAssembly) and the app's Python logic (Pyodide) in a Web
// Worker, so the page stays responsive.
//
// Messages in:
//   {id, type: "read", name, bytes}
//   {id, type: "write", name, bytes, tags: {tag: value}}
//   {id, type: "parse", op, a, b}
//   {id, type: "dates", op, payload}
// Messages out:
//   read:  {id, ok: true, tags: {...}, preview: {bytes, orientation, width,
//           height} | null}
//   write: {id, ok: true, bytes}            (the changed file)
//   parse: {id, ok: true, result}           (see parseCoordinates)
//   dates: {id, ok: true, result}           (see web/bridge/fotofixer_bridge.py)
//   any:   {id, ok: false, error}
//   and once: {type: "python-ready", ok, error?} when Pyodide has loaded.
//
// The vendored ExifTool package keeps one Perl instance and no queue; the
// page's ExifClient sends one read or write at a time, and this worker
// answers them in order, so the instance is never used by two calls at
// once. Parse messages run alongside; they only touch Pyodide.

// zeroperl decides "browser or Node" by looking for window and document. A
// worker has neither, so without this it would try Node's fs module.
globalThis.window = globalThis;
globalThis.document = {};

const WASM_URL = new URL("../vendor/zeroperl.wasm", import.meta.url);
const exiftoolReady = import("../vendor/exiftool.js");
const wasmFetch = () => fetch(WASM_URL);

// ----- reading -----

// What the Photo List needs, in one ExifTool call: GPS, the date tags (for
// the Date & Time tab later), the camera, and the small EXIF thumbnail that
// JPEGs and most RAW files carry near their start. -n keeps values numeric
// (signed coordinates, the orientation as 1-8); -b gives binary tags as
// base64 text.
const READ_ARGS = [
  "-json", "-n", "-b",
  "-GPSLatitude", "-GPSLongitude",
  "-DateTimeOriginal", "-CreateDate", "-ModifyDate",
  "-OffsetTimeOriginal", "-OffsetTimeDigitized", "-OffsetTime",
  "-Make", "-Model", "-Orientation", "-ImageSize",
  "-ThumbnailImage",
];
// Files without a small thumbnail (DNGs, some RAW files) have a larger
// PreviewImage; it is read only then, since it can be hundreds of KB.
const PREVIEW_ARGS = ["-json", "-b", "-PreviewImage"];
const DATE_TAGS = ["DateTimeOriginal", "CreateDate", "ModifyDate", "OffsetTimeOriginal", "OffsetTimeDigitized", "OffsetTime"];

function decodeBase64(text) {
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function previewFrom(record, tag) {
  const value = record[tag];
  if (typeof value !== "string" || !value.startsWith("base64:")) return null;
  const orientation = Number.isInteger(record.Orientation) && record.Orientation >= 1 && record.Orientation <= 8 ? record.Orientation : 1;
  const size = String(record.ImageSize ?? "").match(/\d+/g);
  const [width, height] = size && size.length === 2 ? size.map(Number) : [null, null];
  return { bytes: decodeBase64(value.slice("base64:".length)), orientation, width, height };
}

function cleanError(text) {
  // ExifTool's "Error: Unknown file type - /name.ext" -> "Unknown file type".
  return String(text ?? "ExifTool failed").replace(/^Error:\s*/i, "").replace(/\s*-\s*\/[^\n]*$/, "").trim();
}

async function readOne(exiftool, name, bytes) {
  const first = await exiftool.parseMetadata({ name, data: bytes }, { args: READ_ARGS, fetch: wasmFetch, transform: JSON.parse });
  if (!first.success) throw new Error(cleanError(first.error));
  const record = first.data[0] ?? {};
  const tags = {
    gps: typeof record.GPSLatitude === "number" && typeof record.GPSLongitude === "number"
      ? { latitude: record.GPSLatitude, longitude: record.GPSLongitude }
      : null,
    dates: Object.fromEntries(DATE_TAGS.map((tag) => [tag, record[tag] == null || record[tag] === "" ? null : String(record[tag])])),
    make: record.Make ?? null,
    model: record.Model ?? null,
    orientation: record.Orientation ?? 1,
  };
  let preview = previewFrom(record, "ThumbnailImage");
  if (!preview) {
    const second = await exiftool.parseMetadata({ name, data: bytes }, { args: PREVIEW_ARGS, fetch: wasmFetch, transform: JSON.parse });
    if (second.success) preview = previewFrom({ ...record, ...(second.data[0] ?? {}) }, "PreviewImage");
  }
  return { tags, preview };
}

// ----- writing -----

/**
 * Write tags into a copy of the photo: {tag: value}, an empty value
 * deletes the tag (the page builds the dicts: GPS like the desktop's
 * write_gps / clear_gps, dates from the Python bridge). The package writes
 * to a copy (-o) and returns it.
 */
async function writeOne(exiftool, name, bytes, tags) {
  const result = await exiftool.writeMetadata({ name, data: bytes }, tags, { fetch: wasmFetch });
  if (!result.success) throw new Error(cleanError(result.error));
  return new Uint8Array(result.data);
}

// ----- Python (Pyodide) -----

// The app's own modules (core/, services/, the Qt-free Date & Time
// presenter) and the bridge that takes JSON, zipped by
// packaging/fetch_web_vendor.py.
const PYODIDE_DIR = new URL("../vendor/pyodide/", import.meta.url);
const PY_ZIP_URL = new URL("../py/fotofixer_py.zip", import.meta.url);
// The time zone database (core/time_zones.py needs it for daylight saving
// and zone abbreviations); the wheel is vendored next to Pyodide.
const TZDATA_URL = new URL("../vendor/pyodide/tzdata-2025.3-py2.py3-none-any.whl", import.meta.url);
const PY_SETUP = `
import sys
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/web/bridge")
import fotofixer_bridge
`;

const pythonReady = (async () => {
  const { loadPyodide } = await import("../vendor/pyodide/pyodide.mjs");
  const pyodide = await loadPyodide({ indexURL: PYODIDE_DIR.href });
  await pyodide.loadPackage(TZDATA_URL.href);
  const archive = await (await fetch(PY_ZIP_URL)).arrayBuffer();
  pyodide.unpackArchive(archive, "zip", { extractDir: "/app" });
  pyodide.runPython(PY_SETUP);
  const bridge = pyodide.pyimport("fotofixer_bridge");
  return { parse: bridge.parse, dates: bridge.dates };
})();
pythonReady.then(
  () => self.postMessage({ type: "python-ready", ok: true }),
  (error) => self.postMessage({ type: "python-ready", ok: false, error: String(error?.message ?? error) }),
);

async function parseCoordinates(op, a, b) {
  const { parse } = await pythonReady;
  return JSON.parse(parse(op, a, b));
}

/** The Date & Time tab's logic (see web/bridge/fotofixer_bridge.py). */
async function dates(op, payload) {
  const bridge = await pythonReady;
  return JSON.parse(bridge.dates(op, JSON.stringify(payload ?? {})));
}

// ----- messages -----

self.onmessage = async (event) => {
  const { id, type, name, bytes } = event.data;
  try {
    if (type === "read") {
      const exiftool = await exiftoolReady;
      const { tags, preview } = await readOne(exiftool, name, bytes);
      self.postMessage({ id, ok: true, tags, preview }, preview ? [preview.bytes.buffer] : []);
    } else if (type === "write") {
      const exiftool = await exiftoolReady;
      const out = await writeOne(exiftool, name, bytes, event.data.tags);
      self.postMessage({ id, ok: true, bytes: out }, [out.buffer]);
    } else if (type === "parse") {
      const reply = await parseCoordinates(event.data.op, event.data.a, event.data.b);
      self.postMessage({ id, ...reply });
    } else if (type === "dates") {
      const reply = await dates(event.data.op, event.data.payload);
      self.postMessage({ id, ...reply });
    } else {
      self.postMessage({ id, ok: false, error: `unknown message type ${type}` });
    }
  } catch (error) {
    self.postMessage({ id, ok: false, error: String(error?.message ?? error) });
  }
};
