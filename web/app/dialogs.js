// Questions and notices as <dialog> elements. None of them block: each
// returns a promise that settles when the dialog closes (the desktop rule:
// open() plus a callback, never a blocking exec()).

import { el, clear } from "./dom.js";
import { APP_VERSION, PROJECT_URL } from "./version.js";

function openDialog({ title, body, buttons, defaultValue = "cancel", tone = "info" }) {
  return new Promise((resolve) => {
    const dialog = el("dialog", { className: `app-dialog ${tone}` });
    const row = el("div", { className: "dialog-buttons" });
    let settled = false;
    const close = (value) => {
      if (settled) return;
      settled = true;
      dialog.close();
      dialog.remove();
      resolve(value);
    };
    for (const button of buttons) {
      row.append(el("button", {
        className: `btn ${button.className ?? ""}`,
        title: button.title,
        autofocus: button.value === defaultValue,
        onclick: () => close(button.value),
      }, button.label));
    }
    dialog.append(el("h2", { textContent: title }), ...(Array.isArray(body) ? body : [body]), row);
    dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(defaultValue); });
    dialog.addEventListener("click", (event) => { if (event.target === dialog) close(defaultValue); });
    document.body.append(dialog);
    dialog.showModal();
  });
}

function detailsList(summary, lines) {
  const details = el("details", {}, [el("summary", { textContent: summary })]);
  details.append(el("pre", { className: "dialog-details", textContent: lines.join("\n") }));
  return details;
}

/**
 * Some targets already have GPS: Cancel, Skip Photos with GPS (only when
 * some have none), or Replace. Resolves "replace" | "skip" | "cancel".
 */
export function askOverwrite({ question, entries, otherCount }) {
  const buttons = [{ label: "Cancel", value: "cancel", title: "Change nothing" }];
  if (otherCount) buttons.push({ label: "Skip Photos with GPS", value: "skip", title: "Write the location only into the photos without GPS" });
  buttons.push({ label: "Replace", value: "replace", className: "danger", title: "Write the location into every selected photo, replacing existing GPS" });
  return openDialog({
    title: "Replace Existing GPS?",
    tone: "warning",
    body: [el("p", { textContent: question }), detailsList("Show the photos", entries)],
    buttons,
  });
}

/** Remove GPS from these photos? Resolves true to go ahead. */
export async function confirmRemoveGps(names) {
  const photos = names.length === 1 ? "1 photo" : `${names.length} photos`;
  const answer = await openDialog({
    title: "Remove GPS?",
    tone: "warning",
    body: [
      el("p", { textContent: `Remove the GPS coordinates from ${photos}? You can undo this afterwards.` }),
      detailsList("Show the photos", names),
    ],
    buttons: [
      { label: "Cancel", value: "cancel", title: "Change nothing" },
      { label: "Remove GPS", value: "remove", className: "danger", title: "Delete the GPS tags from these photos" },
    ],
  });
  return answer === "remove";
}

/** Change Time Zone's "Keep the clock time": asks first. Resolves true to keep it on. */
export async function confirmKeepClock(text) {
  const answer = await openDialog({
    title: "Keep the Clock Time?",
    body: el("p", { textContent: text }),
    buttons: [
      { label: "Cancel", value: "cancel", title: "Leave the clock times to change with the zone" },
      { label: "Keep Clock Time", value: "keep", className: "primary", title: "Keep the clock times and change only the time zone" },
    ],
    defaultValue: "keep",
  });
  return answer === "keep";
}

/** Which files could not be changed, and why. */
export function showFailures(action, failures) {
  const count = failures.length;
  return openDialog({
    title: "Some Photos Were Not Changed",
    tone: "error",
    body: [
      el("p", { textContent: `Could not ${action} ${count} photo${count === 1 ? "" : "s"}. The other photos were changed.` }),
      detailsList("Show each file and the reason", failures),
    ],
    buttons: [{ label: "OK", value: "ok", title: "Close" }],
    defaultValue: "ok",
  });
}

/** A plain notice with one OK button. */
export function showNotice(title, text, tone = "info") {
  return openDialog({
    title,
    tone,
    body: el("p", { textContent: text }),
    buttons: [{ label: "OK", value: "ok", title: "Close" }],
    defaultValue: "ok",
  });
}

// Where a visitor gets a free ArcGIS key for Esri's satellite imagery.
const ESRI_SIGN_UP_URL = "https://location.arcgis.com/sign-up/";
const ESRI_CREATE_KEY_URL = "https://developers.arcgis.com/documentation/security-and-authentication/api-key-authentication/tutorials/create-an-api-key/";

/**
 * Settings (saved in this browser only): the backups option and the Esri
 * key. Resolves {keepBackups, esriKey} on Save, null on Cancel.
 */
export async function showSettings({ keepBackups, canSaveInPlace, esriKey = "" }) {
  const checkbox = el("input", { type: "checkbox", id: "keepBackups", checked: keepBackups });
  let key = esriKey;
  const keyStatus = el("div", { className: "note key-status" });
  const keyInput = el("input", { className: "field", type: "password", id: "esriKey", placeholder: esriKey ? "Paste a new key to replace it" : "Paste your ArcGIS API key", autocomplete: "off" });
  keyInput.addEventListener("input", () => { key = keyInput.value.trim() || key; renderKey(); });
  const pasteButton = el("button", { className: "btn", title: "Paste a key from the clipboard", onclick: async () => {
    try { keyInput.value = (await navigator.clipboard.readText()).trim(); key = keyInput.value || key; renderKey(); } catch { keyInput.focus(); }
  } }, "Paste");
  const removeButton = el("button", { className: "btn remove", title: "Forget the key; the map's Satellite button goes back to USGS imagery", onclick: () => { key = ""; keyInput.value = ""; renderKey(); } }, "Remove Key");
  function renderKey() {
    const saved = key ? (key === esriKey ? "A key is saved in this browser." : "A new key will be saved.") : "No key: the map's Satellite button shows USGS imagery (United States only).";
    keyStatus.textContent = saved;
    keyStatus.classList.toggle("ok", Boolean(key));
    removeButton.disabled = !key;
  }
  renderKey();
  const body = [
    el("h3", { textContent: "Backups" }),
    el("label", { className: "check-row", for: "keepBackups" }, [checkbox, el("span", { textContent: "Keep Backup Copies of Originals" })]),
    el("p", { className: "note", textContent: canSaveInPlace
      ? "Before a photo's first GPS change, a copy named <name>_original.<ext> is saved next to it in the opened folder, if the photo had GPS (adding GPS to a photo without any loses nothing). Backups are added to the Photo List, not selected. Undo deletes the backups it made."
      : "Only when photos are saved in place (Chrome or Edge with an opened folder). In this browser changed photos download, so the originals stay as they are." }),
    el("h3", { textContent: "Esri Satellite Map" }),
    el("p", { className: "note" }, [
      "Worldwide satellite imagery on the map needs your own free API key from an ",
      el("a", { href: ESRI_SIGN_UP_URL, target: "_blank", rel: "noopener", textContent: "ArcGIS Location Platform" }),
      " account (a Public key with only the Static basemap tiles privilege; ",
      el("a", { href: ESRI_CREATE_KEY_URL, target: "_blank", rel: "noopener", textContent: "Esri's instructions" }),
      "). The key stays in this browser and goes only to Esri with each map tile. Without a key the Satellite button shows USGS imagery, United States only.",
    ]),
    keyStatus,
    keyInput,
    el("div", { className: "dialog-row" }, [pasteButton, removeButton]),
    el("p", { className: "note", textContent: "Settings are saved in this browser only." }),
    // The version (the same number as the desktop app and the container
    // image), so a visitor can tell whether the site runs the latest one.
    el("p", { className: "note version" }, [
      `FotoFixer – When & Where ${APP_VERSION}. `,
      el("a", { href: PROJECT_URL, target: "_blank", rel: "noopener", textContent: "Project page and releases" }),
      ".",
    ]),
  ];
  const answer = await openDialog({
    title: "Settings",
    body,
    buttons: [
      { label: "Cancel", value: "cancel", title: "Close without saving" },
      { label: "Save", value: "save", className: "primary", title: "Save the settings in this browser" },
    ],
    defaultValue: "cancel",
  });
  return answer === "save" ? { keepBackups: checkbox.checked, esriKey: key } : null;
}

export { clear };
