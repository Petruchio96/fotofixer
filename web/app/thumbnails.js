// Thumbnails from the previews ExifTool pulls out of the files, or from the
// files themselves when the browser can decode them. Does what the desktop's
// gui/thumbnail_loader.py does: crop a padded preview to the photo's shape
// (Canon CR3 thumbnails are 4:3 with black bars around a 3:2 photo), then
// rotate it upright with the photo's EXIF orientation.

// Twice the 128 px tile image, so thumbnails stay sharp on high-DPI screens.
export const THUMBNAIL_SIZE = 256;

function makeCanvas(width, height) {
  if (typeof OffscreenCanvas === "function") return new OffscreenCanvas(width, height);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

function canvasToBlob(canvas) {
  if (canvas.convertToBlob) return canvas.convertToBlob({ type: "image/jpeg", quality: 0.85 });
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("could not encode the thumbnail"))), "image/jpeg", 0.85),
  );
}

/**
 * The part of the preview that is the photo. Previews are stored unrotated
 * and so is the photo size ExifTool reports, so this happens before the
 * rotation. A difference under 1% is left alone.
 */
function cropRect(bitmap, width, height) {
  const full = { sx: 0, sy: 0, sw: bitmap.width, sh: bitmap.height };
  if (!width || !height) return full;
  const target = width / height;
  const actual = bitmap.width / bitmap.height;
  if (Math.abs(target - actual) / target < 0.01) return full;
  if (actual > target) {
    const sw = Math.round(bitmap.height * target);
    return { sx: Math.round((bitmap.width - sw) / 2), sy: 0, sw, sh: bitmap.height };
  }
  const sh = Math.round(bitmap.width / target);
  return { sx: 0, sy: Math.round((bitmap.height - sh) / 2), sw: bitmap.width, sh };
}

/**
 * Draw the source rectangle rotated/mirrored per the EXIF orientation
 * (1 upright, 2 mirrored, 3 rotated 180, 4 flipped, 5-8 transposed and
 * rotated). dw x dh is the unrotated drawing size; the canvas is dh x dw
 * for orientations 5-8.
 */
async function render(bitmap, src, orientation) {
  const scale = THUMBNAIL_SIZE / Math.max(src.sw, src.sh);
  const dw = Math.max(1, Math.round(src.sw * scale));
  const dh = Math.max(1, Math.round(src.sh * scale));
  const swap = orientation >= 5;
  const canvas = makeCanvas(swap ? dh : dw, swap ? dw : dh);
  const ctx = canvas.getContext("2d");
  switch (orientation) {
    case 2: ctx.transform(-1, 0, 0, 1, dw, 0); break;
    case 3: ctx.transform(-1, 0, 0, -1, dw, dh); break;
    case 4: ctx.transform(1, 0, 0, -1, 0, dh); break;
    case 5: ctx.transform(0, 1, 1, 0, 0, 0); break;
    case 6: ctx.transform(0, 1, -1, 0, dh, 0); break;
    case 7: ctx.transform(0, -1, -1, 0, dh, dw); break;
    case 8: ctx.transform(0, -1, 1, 0, 0, dw); break;
    default: break;
  }
  ctx.drawImage(bitmap, src.sx, src.sy, src.sw, src.sh, 0, 0, dw, dh);
  bitmap.close();
  return canvasToBlob(canvas);
}

/** A thumbnail from an embedded JPEG preview (bytes) -> a JPEG Blob. */
export async function thumbnailFromPreview(bytes, { orientation = 1, width = null, height = null } = {}) {
  // The preview's own orientation tag (if any) is ignored, as on the
  // desktop: the RAW file's orientation applies.
  const bitmap = await createImageBitmap(new Blob([bytes], { type: "image/jpeg" }), { imageOrientation: "none" });
  return render(bitmap, cropRect(bitmap, width, height), orientation);
}

/**
 * A thumbnail by decoding the photo itself (JPEGs without an EXIF
 * thumbnail; HEIC where the browser can decode it, which is Safari).
 * The browser applies the file's own orientation and shrinks it while
 * decoding, so a 24-megapixel JPEG is never held at full size.
 */
export async function thumbnailFromFile(file) {
  const bitmap = await createImageBitmap(file, {
    imageOrientation: "from-image",
    resizeWidth: THUMBNAIL_SIZE * 2,
    resizeQuality: "high",
  });
  return render(bitmap, { sx: 0, sy: 0, sw: bitmap.width, sh: bitmap.height }, 1);
}
