// ExifTool (WebAssembly) in a Web Worker, so the page stays responsive.
//
// Messages in:  {id, type: "read", name, bytes}
// Messages out: {id, ok: true, tags: {...}, preview: {bytes, orientation,
//                width, height} | null}  or  {id, ok: false, error}
//
// The vendored package keeps one Perl instance and no queue; the page's
// ExifClient sends one request at a time, and this worker answers them in
// order, so the instance is never used by two calls at once.

// zeroperl decides "browser or Node" by looking for window and document. A
// worker has neither, so without this it would try Node's fs module.
globalThis.window = globalThis;
globalThis.document = {};

const WASM_URL = new URL("../vendor/zeroperl.wasm", import.meta.url);
const exiftoolReady = import("../vendor/exiftool.js");
const wasmFetch = () => fetch(WASM_URL);

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

self.onmessage = async (event) => {
  const { id, type, name, bytes } = event.data;
  if (type !== "read") return;
  try {
    const exiftool = await exiftoolReady;
    const { tags, preview } = await readOne(exiftool, name, bytes);
    self.postMessage({ id, ok: true, tags, preview }, preview ? [preview.bytes.buffer] : []);
  } catch (error) {
    self.postMessage({ id, ok: false, error: String(error?.message ?? error) });
  }
};
