// Which files the web app opens. Mirrors core/file_types.py (a test checks
// that the two lists match): only files cameras and phones make.

export const JPEG_EXTENSIONS = [".jpg", ".jpeg"];

export const RAW_EXTENSIONS = [
  ".cr2", ".cr3", ".dng", ".nef", ".nrw", ".arw", ".raf", ".orf", ".rw2", ".pef", ".srw",
];

export const HEIF_EXTENSIONS = [".heic", ".heif", ".hif"];

export const SUPPORTED_EXTENSIONS = new Set([...JPEG_EXTENSIONS, ...RAW_EXTENSIONS, ...HEIF_EXTENSIONS]);

export function extensionOf(name) {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot).toLowerCase();
}

export function isSupportedName(name) {
  return SUPPORTED_EXTENSIONS.has(extensionOf(name));
}

export function isRawName(name) {
  return RAW_EXTENSIONS.includes(extensionOf(name));
}

export function isHeifName(name) {
  return HEIF_EXTENSIONS.includes(extensionOf(name));
}

export function isJpegName(name) {
  return JPEG_EXTENSIONS.includes(extensionOf(name));
}

// For the file inputs' accept attribute.
export const ACCEPT_ATTRIBUTE = [...SUPPORTED_EXTENSIONS].join(",");
