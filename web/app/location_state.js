// What the Location tab shows for the current selection and New Location:
// a port of gui/presenters/inspector_state.py (labels, hints, which
// buttons are enabled, and why not). Plain JavaScript, tested in Node.

function photosWord(count) {
  return count === 1 ? `${count} Photo` : `${count} Photos`;
}

/**
 * @param selectedIds   the photos selected in the Photo List (to change)
 * @param photos        id -> {name, gps}
 * @param newLocation   {latitude, longitude} parsed from the fields, or null
 * @param fieldsEmpty   both fields blank
 * @param sourceId      the photo the location was copied from, or null
 */
export function buildLocationState({ selectedIds, photos, newLocation, fieldsEmpty, sourceId = null }) {
  const count = selectedIds.length;
  const gpsOf = (id) => photos.get(id)?.gps ?? null;
  const withGps = selectedIds.filter((id) => gpsOf(id) !== null);

  // Apply: every selected photo except the source photo.
  const sourceSelected = sourceId !== null && selectedIds.includes(sourceId);
  const targets = selectedIds.filter((id) => id !== sourceId);
  const canApply = targets.length > 0 && newLocation !== null;
  const applyLabel = targets.length ? `Apply Location to ${photosWord(targets.length)}` : "Apply Location to Selected Photos";
  const overwriteIds = canApply ? targets.filter((id) => gpsOf(id) !== null) : [];

  let hint = "";
  let hintTone = "info";
  if (count === 0) {
    hint = "Select the photos to change in the Photo List.";
  } else if (targets.length === 0) {
    hint = "The selected photo is the source of the new location, so it isn't changed. Select the photos to give its location to.";
  } else if (newLocation === null && fieldsEmpty) {
    hint = "Set a new location above: copy it from a photo, type, or paste one.";
  } else if (newLocation === null) {
    hint = "The new location isn't valid. Check the latitude and longitude.";
    hintTone = "error";
  } else if (overwriteIds.length) {
    const n = overwriteIds.length;
    hint = `${photosWord(n).toLowerCase()} already ${n === 1 ? "has" : "have"} GPS, which will be replaced.`;
    hintTone = "warning";
  } else if (sourceSelected) {
    hint = "The source photo isn't changed.";
  }

  const removeLabel = withGps.length ? `Remove GPS from Selected ${photosWord(withGps.length)}` : "Remove GPS from Selected Photos";

  return {
    canApply,
    applyLabel,
    targets,
    overwriteIds,
    hint,
    hintTone,
    canRemove: withGps.length > 0,
    removeLabel,
    removeIds: withGps,
  };
}

/** The question asked when some targets already have GPS. */
export function overwriteQuestion(overwriteCount, otherCount) {
  const have = overwriteCount === 1 ? "has" : "have";
  const photos = overwriteCount === 1 ? "1 photo" : `${overwriteCount} photos`;
  const already = `${photos.charAt(0).toUpperCase()}${photos.slice(1)} already ${have} GPS coordinates.`;
  const undoTip = "Click Undo if you accidentally overwrite GPS data.";
  return otherCount
    ? `${already} Choose Skip to keep the existing GPS data, Replace to overwrite them. ${undoTip}`
    : `${already} Choose Replace to overwrite them. ${undoTip}`;
}

/** The message after a change, like the desktop's. */
export function changeMessage({ action, count, skipped = 0, backups = 0 }) {
  const photos = (n) => (n === 1 ? "1 photo" : `${n} photos`);
  let message = action === "apply" ? `Applied GPS to ${photos(count)}.` : `Removed GPS from ${photos(count)}.`;
  if (skipped) message += ` Skipped ${skipped} that already ${skipped === 1 ? "has" : "had"} GPS.`;
  if (backups) {
    const copies = backups === 1 ? "a backup of the original" : `${backups} backups of the originals`;
    message += ` Saved ${copies} next to ${backups === 1 ? "it" : "them"}.`;
  }
  return message;
}
