// The Location tab: the New Location box (copy from a photo, type or paste
// coordinates), the hint, Apply, and Remove GPS. What it shows comes from
// location_state.js; the writing itself lives in main.js.

import { el, clear, gpsPin, photoIcon, mapIcon } from "./dom.js";
import { ACCEPT_ATTRIBUTE } from "./file_types.js";
import { formatCoordinates } from "./photo_store.js";
import { buildLocationState } from "./location_state.js";

export const PICK_BUTTON_TEXT = "From a Photo in the Photo List";
const PICK_BUTTON_TIP = "Click this, then click a photo with GPS in the Photo List to copy its location. The photos selected to change stay selected.";
const PICK_DISABLED_TIP = "No photo in the Photo List has GPS coordinates to copy, other than the photos selected to change (a photo can't be both).";
export const PICK_PROMPT = "Click a photo on the left to copy its location. Only photos with GPS can be picked. Press Esc or Cancel to stop.";

// Typing pauses this long before the text is parsed (through Python).
const PARSE_DELAY_MS = 150;

/**
 * actions: {parse(op, a, b) -> Promise, togglePick(), locationFromFile(file),
 *           apply(state), removeGps(state), onLocationChange()}
 * Returns {setFields(lat, lon, {sourceId}), clearFields(), state()}.
 */
export function createLocationView(container, store, actions) {
  let newLocation = null; // parsed {latitude, longitude} or null
  let parseTimer = null;
  let parseSerial = 0;
  let settingFields = false;
  let state = null;
  let pythonReady = false;

  // ----- New Location box -----
  const pickButton = el("button", { className: "btn pick", title: PICK_BUTTON_TIP, "aria-pressed": "false", onclick: () => actions.togglePick() }, PICK_BUTTON_TEXT);
  const fileInput = el("input", { type: "file", accept: ACCEPT_ATTRIBUTE, className: "hidden-input" });
  fileInput.addEventListener("change", () => { if (fileInput.files[0]) actions.locationFromFile(fileInput.files[0]); fileInput.value = ""; });
  const fromFileButton = el("button", { className: "btn pick", title: "Choose any photo on this computer and use its GPS coordinates", onclick: () => fileInput.click() }, "From a Photo on This Computer");
  // Opens the map: click it or drag the pin to fill the fields.
  const mapButton = el("button", {
    className: "btn pick",
    title: "Open a map: click it, or drag the pin, to set the New Location. Photos in the Photo List with GPS show as dots.",
    onclick: () => actions.openMap(),
  }, [mapIcon(), "Pick from a Map"]);

  // The source card: which photo the location came from.
  const sourceThumb = el("div", { className: "source-thumb" });
  const sourceTitle = el("div", { className: "source-title" });
  const sourceDetail = el("div", { className: "source-detail" });
  const sourceClear = el("button", { className: "source-clear", title: "Clear the location", onclick: () => clearFields() }, "✕");
  const sourceCard = el("div", { className: "source-card", hidden: true }, [sourceThumb, el("div", { className: "source-text" }, [sourceTitle, sourceDetail]), sourceClear]);

  const latitude = el("input", { className: "field", id: "latitude", placeholder: "e.g. 40.5865 or 40° 35' 11\" N", autocomplete: "off", spellcheck: "false" });
  const longitude = el("input", { className: "field", id: "longitude", placeholder: "e.g. -111.6558 or 111° 39' 21\" W", autocomplete: "off", spellcheck: "false" });
  for (const field of [latitude, longitude]) {
    field.addEventListener("input", () => onFieldInput(field));
    field.addEventListener("blur", () => validateField(field));
  }
  const pasteButton = el("button", { className: "btn", title: "Paste coordinates copied from a map or another photo (decimal, DMS, or DDM)", onclick: () => paste() }, "Paste");
  const clearButton = el("button", { className: "btn", title: "Empty the latitude and longitude fields", onclick: () => clearFields() }, "Clear");

  const group = el("div", { className: "group" }, [
    el("h3", { textContent: "New Location" }),
    el("div", { className: "label", textContent: "Copy location" }),
    el("div", { className: "button-row" }, [pickButton, fromFileButton, fileInput]),
    el("div", { className: "button-row" }, [mapButton]),
    sourceCard,
    el("div", { className: "fields" }, [
      el("div", {}, [el("label", { className: "label", for: "latitude", textContent: "Latitude" }), latitude]),
      el("div", {}, [el("label", { className: "label", for: "longitude", textContent: "Longitude" }), longitude]),
    ]),
    el("div", { className: "button-row" }, [pasteButton, clearButton]),
  ]);

  // ----- hint, Apply, Remove GPS -----
  const hint = el("div", { className: "hint" });
  const applyButton = el("button", { className: "btn accent", disabled: true, title: "Write the New Location into the selected photos", onclick: () => actions.apply(state) }, "Apply Location to Selected Photos");
  const removeButton = el("button", { className: "btn remove", disabled: true, title: "Delete the GPS coordinates stored in the selected photos that have them. You can undo this afterwards.", onclick: () => actions.removeGps(state) }, "Remove GPS from Selected Photos");
  const pythonNote = el("div", { className: "note python-note", textContent: "Loading the coordinate parser…" });

  clear(container);
  container.append(group, hint, applyButton, removeButton, pythonNote);

  // ----- fields -----

  function fieldsEmpty() {
    return !latitude.value.trim() && !longitude.value.trim();
  }

  /** Fill both fields without the auto-split kicking in. */
  function setFields(lat, lon, { sourceId = null } = {}) {
    settingFields = true;
    latitude.value = lat;
    longitude.value = lon;
    settingFields = false;
    latitude.classList.remove("invalid");
    longitude.classList.remove("invalid");
    store.setSource(sourceId);
    parseFields();
  }

  function clearFields() {
    setFields("", "");
  }

  /**
   * Typing or pasting "40.5865, -111.6558" into either field splits it into
   * the two fields. Editing by hand means the location no longer comes from
   * the source photo.
   */
  function onFieldInput(field) {
    if (settingFields) return;
    if (store.sourceId !== null) store.setSource(null);
    clearTimeout(parseTimer);
    parseTimer = setTimeout(async () => {
      const text = field.value;
      const serial = ++parseSerial;
      const pair = await actions.parse("pair", text);
      if (serial !== parseSerial) return;
      if (pair.ok && pair.result) {
        setFields(pair.result[0], pair.result[1]);
        return;
      }
      parseFields();
    }, PARSE_DELAY_MS);
  }

  async function parseFields() {
    const serial = ++parseSerial;
    const reply = await actions.parse("manual", latitude.value, longitude.value);
    if (serial !== parseSerial) return;
    newLocation = reply.ok && reply.result ? { latitude: reply.result[0], longitude: reply.result[1] } : null;
    render();
    actions.onLocationChange?.(newLocation);
  }

  async function validateField(field) {
    const text = field.value.trim();
    if (!text) {
      field.classList.remove("invalid");
      field.title = "";
      return;
    }
    const reply = await actions.parse(field === latitude ? "latitude" : "longitude", text);
    field.classList.toggle("invalid", !reply.ok);
    field.title = reply.ok ? "" : field === latitude
      ? `Invalid latitude (${reply.error}). Use decimal, DMS, or DDM within -90 to 90`
      : `Invalid longitude (${reply.error}). Use decimal, DMS, or DDM within -180 to 180`;
  }

  async function paste() {
    let text = "";
    try {
      text = (await navigator.clipboard.readText()).trim();
    } catch {
      actions.message?.("The browser didn't allow reading the clipboard. Paste into the Latitude field instead (Ctrl+V).", "error");
      latitude.focus();
      return;
    }
    const pair = await actions.parse("pair", text);
    if (pair.ok && pair.result) setFields(pair.result[0], pair.result[1]);
    else actions.message?.("The clipboard doesn't contain coordinates.", "error");
  }

  // ----- drawing -----

  function renderSourceCard() {
    const source = store.sourceId !== null ? store.get(store.sourceId) : null;
    sourceCard.hidden = source === null;
    if (!source) return;
    sourceTitle.textContent = `From ${source.name}`;
    sourceDetail.textContent = newLocation ? formatCoordinates(newLocation) : "";
    clear(sourceThumb);
    if (source.thumb) sourceThumb.append(el("img", { src: source.thumb, alt: "" }));
    else sourceThumb.append(photoIcon());
    sourceThumb.append(gpsPin());
  }

  function render() {
    const photos = new Map([...store.photos].map(([id, photo]) => [id, { name: photo.name, gps: photo.gps }]));
    state = buildLocationState({
      selectedIds: store.selectedIds(),
      photos,
      newLocation,
      fieldsEmpty: fieldsEmpty(),
      sourceId: store.sourceId,
    });
    state.newLocation = newLocation;
    const picking = store.picking;
    applyButton.textContent = state.applyLabel;
    applyButton.disabled = !state.canApply || picking || !pythonReady;
    removeButton.textContent = state.removeLabel;
    removeButton.disabled = !state.canRemove || picking;
    hint.textContent = state.hint;
    hint.className = `hint ${state.hintTone}`;
    hint.hidden = !state.hint;
    const canPick = store.pickableCount() > 0;
    pickButton.textContent = picking ? "Cancel" : PICK_BUTTON_TEXT;
    pickButton.title = picking ? "Stop picking a photo" : canPick ? PICK_BUTTON_TIP : PICK_DISABLED_TIP;
    pickButton.disabled = !picking && !canPick;
    pickButton.setAttribute("aria-pressed", picking ? "true" : "false");
    pickButton.classList.toggle("on", picking);
    for (const control of [fromFileButton, mapButton, latitude, longitude, pasteButton, clearButton, sourceClear]) control.disabled = picking;
    renderSourceCard();
  }

  store.subscribe(() => render());
  render();

  return {
    setFields,
    clearFields,
    state: () => state,
    newLocation: () => newLocation,
    /** The fields as typed, and the source photo, for the map's Back. */
    fields: () => ({ latitude: latitude.value, longitude: longitude.value, sourceId: store.sourceId }),
    setPythonReady(ok, error) {
      pythonReady = ok;
      pythonNote.textContent = ok ? "" : `The coordinate parser could not load: ${error}`;
      pythonNote.hidden = ok;
      render();
    },
  };
}
