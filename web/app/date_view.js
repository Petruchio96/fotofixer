// The Date & Time tab: four steps like the desktop's (select the photos,
// choose how to change them, correct the date and time or choose the zone,
// check and apply). What it shows comes from the Python presenter through
// the bridge (actions.dates("state", payload)); this module keeps only the
// tab's own state (the choice, the reference photo, what was typed, the
// zone, the sources) and draws.

import { el, clear, photoIcon } from "./dom.js";
import { ACCEPT_ATTRIBUTE } from "./file_types.js";

export const PICK_TIME_BUTTON_TEXT = "From a Photo in the Photo List";
const PICK_TIME_BUTTON_TIP = "Click this, then click a photo in the Photo List whose time is right (e.g. from your phone), taken at the same moment as the reference photo.";
const PICK_TIME_DISABLED_TIP = "Select the photos to change first; the photo with the right time must be in the Photo List and not selected.";
export const TIME_PICK_PROMPT = "Click the photo taken at the same moment as {reference}. Its time becomes {reference}'s correct time. Press Esc or Cancel to stop.";
const KEEP_CLOCK_TIP = "Off: the photos keep the moment they were taken; their clock times change to show it in the new zone (11:16 am MDT → 12:16 pm CDT). On: the clock times stay as they are and only the zone changes (11:16 am MDT → 11:16 am CDT), which moves the moment.";
const MIXED_ZONES_CHANGE_TIP = "The selected photos have more than one time zone. All of them will change to this time zone.";

const MODES = {
  shift: { title: "Shift Date and Time", detail: "The time was off. Correct one photo; the rest move by the same amount.", tip: "Move every selected photo by the same amount, keeping the time between them" },
  set: { title: "Set One Date and Time", detail: "Every selected photo gets the same date and time.", tip: "Give every selected photo one date and time" },
  zone: { title: "Change Time Zone", detail: "Correct photos with the wrong time zone.", tip: "Give the selected photos another time zone (the same moment, or the same clock time)" },
};

function isoNow() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/**
 * actions: {dates(op, payload) -> Promise, togglePickTime(), timeFromFile(file),
 *           apply(state), addPhotos(), confirmKeepClock(text) -> Promise<bool>,
 *           onStateChange(state)}
 */
export function createDateView(container, store, actions) {
  // The tab's own state (the desktop's _date_* fields).
  let mode = null; // "shift" | "set" | "zone" | null
  let choicesOpen = false;
  let reference = null; // id chosen with the arrows (null: the earliest)
  let typedReference = null; // ISO: the corrected date typed for the reference
  let setValue = null; // ISO
  let zoneKey = null; // null: each photo keeps its own zone
  let keepClock = false;
  let sourceInfo = null; // a photo from the computer: {name, dates, make, model}
  let state = null; // the last state from the bridge
  let serial = 0;
  let pythonReady = false;
  let refreshTimer = null;

  // ----- step 1: select -----
  const step1Summary = el("div", { className: "step-summary" });
  const step1Hint = el("div", { className: "note" });
  const addPhotosButton = el("button", { className: "btn primary", title: "Choose photos to add to the Photo List", onclick: () => actions.addPhotos() }, "+ Add Photos");
  const step1 = stepBox(1, "Select the photos to change", step1Summary, [step1Hint, addPhotosButton]);

  // ----- step 2: the three choices -----
  const cards = {};
  const changeButton = el("button", { className: "change-link", title: "Show all three choices, to pick another", onclick: () => { choicesOpen = true; refresh(); } }, "Change ▾");
  for (const [key, text] of Object.entries(MODES)) {
    cards[key] = el("button", { className: "card", title: text.tip, "aria-pressed": "false", onclick: () => chooseMode(key) }, [
      el("div", { className: "card-text" }, [el("div", { className: "card-title", textContent: text.title }), el("div", { className: "card-detail", textContent: text.detail })]),
    ]);
  }
  const cardList = el("div", { className: "cards" }, Object.values(cards));
  const step2 = stepBox(2, "Choose how to change Date & Time", el("div", { className: "step-summary" }), [cardList]);
  step2.querySelector(".step-head").append(changeButton);

  // ----- step 3: correct / enter / choose the zone -----
  const refThumb = el("div", { className: "source-thumb" });
  const refTitle = el("div", { className: "source-title" });
  const refDetail = el("div", { className: "source-detail" });
  const refEarliest = el("span", { className: "source-detail", textContent: "The earliest selected" });
  const refPosition = el("span", { className: "source-detail" });
  const refBack = el("button", { className: "arrow", title: "Use the previous selected photo (by date) as the reference", onclick: () => stepReference(-1) }, "‹");
  const refForward = el("button", { className: "arrow", title: "Use the next selected photo (by date) as the reference", onclick: () => stepReference(1) }, "›");
  const refCard = el("div", { className: "source-card ref-card" }, [
    refThumb,
    el("div", { className: "source-text" }, [refTitle, refDetail, el("div", { className: "ref-row" }, [refEarliest, el("span", { className: "spacer" }), refBack, refPosition, refForward])]),
  ]);
  const zoneSelect = el("select", { className: "select", "aria-label": "Time zone", title: "Choose the zone, then enter the time in it" });
  zoneSelect.addEventListener("change", () => zoneChosen(zoneSelect.value));
  const dateInput = el("input", { className: "field", type: "date", "aria-label": "Date", title: "The date" });
  const timeInput = el("input", { className: "field time", type: "time", step: "1", "aria-label": "Time", title: "The time (hours, minutes, seconds)" });
  for (const input of [dateInput, timeInput]) input.addEventListener("change", () => dateTyped());
  const clockRow = el("div", { className: "clock-row" }, [dateInput, timeInput]);
  const correctLabel = el("div", { className: "label" });
  const pickTimeButton = el("button", { className: "btn pick", title: PICK_TIME_BUTTON_TIP, "aria-pressed": "false", onclick: () => actions.togglePickTime() }, PICK_TIME_BUTTON_TEXT);
  const fileInput = el("input", { type: "file", accept: ACCEPT_ATTRIBUTE, className: "hidden-input" });
  fileInput.addEventListener("change", () => { if (fileInput.files[0]) actions.timeFromFile(fileInput.files[0]); fileInput.value = ""; });
  const timeFromFileButton = el("button", { className: "btn pick", title: "Choose a photo on your computer whose time is right, taken at the same moment as the reference photo", onclick: () => fileInput.click() }, "From a Photo on This Computer");
  const sourceTitle = el("div", { className: "source-title" });
  const sourceDetail = el("div", { className: "source-detail" });
  const sourceClear = el("button", { className: "source-clear", title: "Stop using this photo's time", onclick: () => clearTimeSource() }, "✕");
  const sourceThumb = el("div", { className: "source-thumb" });
  const sourceCard = el("div", { className: "source-card", hidden: true }, [sourceThumb, el("div", { className: "source-text" }, [sourceTitle, sourceDetail]), sourceClear]);
  const copyBlock = el("div", { className: "copy-block" }, [
    el("div", { className: "label", textContent: "Or copy the time from a photo taken at the same moment" }),
    el("div", { className: "button-row" }, [pickTimeButton, timeFromFileButton, fileInput]),
    sourceCard,
  ]);
  const keepClockCheck = el("input", { type: "checkbox", id: "keepClock", title: KEEP_CLOCK_TIP });
  keepClockCheck.addEventListener("change", () => keepClockClicked(keepClockCheck.checked));
  const keepClockRow = el("div", { className: "keep-clock" }, [
    el("label", { className: "check-row", for: "keepClock", title: KEEP_CLOCK_TIP }, [keepClockCheck, el("span", { textContent: "Keep the clock time (change only the time zone)" })]),
    el("div", { className: "note", textContent: "Apply the current time to the selected time zone.", title: KEEP_CLOCK_TIP }),
  ]);
  const step3 = stepBox(3, "Correct the date and time", el("div", { className: "step-summary" }), [refCard, correctLabel, zoneSelect, clockRow, copyBlock, keepClockRow]);

  // ----- step 4: check and apply -----
  const hint = el("div", { className: "hint" });
  const rows = el("div", { className: "changes" });
  const applyButton = el("button", { className: "btn accent", disabled: true, title: "Write the new dates into the selected photos", onclick: () => { if (state?.canApply) actions.apply(state); } }, "Apply");
  const step4 = stepBox(4, "Check the changes and apply", el("div", { className: "step-summary" }), [hint, rows, applyButton]);
  const pythonNote = el("div", { className: "note python-note", textContent: "Loading the date logic…" });

  clear(container);
  container.append(step1, step2, step3, step4, pythonNote);

  function stepBox(number, title, summary, children) {
    const head = el("div", { className: "step-head" }, [
      el("span", { className: "circle", textContent: String(number) }),
      el("div", { className: "step-text" }, [el("div", { className: "step-title", textContent: title }), summary]),
    ]);
    const body = el("div", { className: "step-body" }, children);
    return el("div", { className: "step locked", dataset: { number: String(number) } }, [head, body]);
  }

  function setStep(step, stateName, summary = "") {
    step.classList.remove("done", "active", "locked");
    step.classList.add(stateName);
    const circle = step.querySelector(".circle");
    circle.textContent = stateName === "done" ? "✓" : step.dataset.number;
    step.querySelector(".step-summary").textContent = stateName === "locked" ? `After step ${Number(step.dataset.number) - 1}` : summary;
    step.querySelector(".step-body").hidden = stateName === "locked";
  }

  // ----- the tab's state -----

  function chooseMode(key) {
    if (key === mode) {
      choicesOpen = !choicesOpen;
    } else {
      choicesOpen = false;
      mode = key;
      if (store.picking === "time") actions.togglePickTime();
    }
    refresh();
  }

  /** The selected photos with a date, earliest first (the time source left out). */
  function datedSelection() {
    const exclude = store.timeSourceId !== null && store.selection.has(store.timeSourceId) ? store.timeSourceId : null;
    return store.selectedIds()
      .filter((id) => id !== exclude && store.hasDate(id))
      .sort((a, b) => {
        const pa = store.get(a);
        const pb = store.get(b);
        if (pa.dateTaken !== pb.dateTaken) return pa.dateTaken < pb.dateTaken ? -1 : 1;
        return pa.name.toLowerCase() < pb.name.toLowerCase() ? -1 : 1;
      });
  }

  function stepReference(offset) {
    const dated = datedSelection();
    const current = state?.reference ?? dated[0];
    const index = dated.indexOf(current) + offset;
    if (index >= 0 && index < dated.length) {
      reference = dated[index];
      refresh();
    }
  }

  /** A date and time typed: for Shift the reference's corrected time, for Set the value. */
  function dateTyped() {
    if (!dateInput.value) return;
    const iso = `${dateInput.value}T${timeInput.value || "00:00:00"}`.slice(0, 19).padEnd(19, ":00".slice(0, 19 - `${dateInput.value}T${timeInput.value || "00:00:00"}`.length));
    if (mode === "set") {
      setValue = iso;
    } else {
      typedReference = iso;
      // Typing the time by hand means it no longer comes from the source photo.
      clearTimeSource({ keepTyped: true });
      return;
    }
    refresh();
  }

  async function zoneChosen(key) {
    const chosen = key || null;
    if (mode === "set" && setValue && state) {
      const reply = await actions.dates("convert_set_value", { value: setValue, fromKey: state.zoneKey, toKey: chosen ?? "" });
      if (reply.ok && reply.result) setValue = reply.result;
    }
    zoneKey = chosen;
    refresh();
  }

  async function keepClockClicked(checked) {
    if (!checked) {
      keepClock = false;
      refresh();
      return;
    }
    const reply = await actions.dates("keep_clock_text", { ...payload(), zoneKey: state?.zoneKey ?? zoneKey });
    const text = reply.ok ? reply.result : "When enabled, the photos keep their clock times and only get the new time zone.";
    keepClock = await actions.confirmKeepClock(text);
    keepClockCheck.checked = keepClock;
    refresh();
  }

  function clearTimeSource({ keepTyped = false } = {}) {
    store.setTimeSource(null);
    sourceInfo = null;
    if (!keepTyped) typedReference = null;
    refresh();
  }

  /** Start the change over (after Apply, Deselect All, or a tab switch). */
  function reset() {
    mode = null;
    choicesOpen = false;
    reference = null;
    typedReference = null;
    zoneKey = null;
    keepClock = false;
    keepClockCheck.checked = false;
    sourceInfo = null;
    store.setTimeSource(null);
    refresh();
  }

  function payload() {
    const photos = {};
    for (const [id, photo] of store.photos) {
      if (photo.status !== "ready") continue;
      photos[id] = { name: photo.name, dates: photo.dates ?? {}, make: photo.make, model: photo.model };
    }
    return {
      photos,
      selected: store.selectedIds(),
      mode,
      reference,
      typedReference,
      setValue,
      source: store.timeSourceId,
      sourceInfo,
      zoneKey,
      keepClock,
      computerOffsetMinutes: -new Date().getTimezoneOffset(),
      now: isoNow(),
    };
  }

  /** Ask the bridge for the state (a tick later, so bursts become one call). */
  function refresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(async () => {
      if (!pythonReady) return;
      const mine = ++serial;
      const reply = await actions.dates("state", payload());
      if (mine !== serial) return;
      if (!reply.ok) {
        pythonNote.hidden = false;
        pythonNote.textContent = `The date logic failed: ${reply.error}`;
        return;
      }
      state = reply.result;
      if (mode === "set" && setValue === null) setValue = state.setValue;
      render();
      actions.onStateChange?.(state);
    }, 30);
  }

  // ----- drawing -----

  function render() {
    if (!state) return;
    const hasPhotos = store.photos.size > 0;
    const selected = state.selectedCount;
    const picking = store.picking === "time";
    const done1 = selected > 0;
    const done2 = done1 && mode !== null && !choicesOpen;
    const done3 = done2 && state.canApply;

    setStep(step1, done1 ? "done" : "active", done1 ? `${selected} photo${selected === 1 ? "" : "s"} selected` : "");
    step1Hint.textContent = hasPhotos
      ? "Click photos in the Photo List, or a camera's checkbox to select all of its photos."
      : "The Photo List is empty. Add photos first, then select the ones to change.";
    step1Hint.hidden = done1;
    addPhotosButton.hidden = hasPhotos;

    setStep(step2, !done1 ? "locked" : done2 ? "done" : "active");
    for (const [key, card] of Object.entries(cards)) {
      card.classList.toggle("on", mode === key);
      card.setAttribute("aria-pressed", mode === key ? "true" : "false");
      card.hidden = done2 && mode !== key;
      card.classList.toggle("folded", done2 && mode === key);
    }
    changeButton.hidden = !done2;
    step2.querySelector(".step-body").hidden = !done1;

    step3.querySelector(".step-title").textContent = mode === "set" ? "Enter the date and time" : mode === "zone" ? "Choose the new time zone" : "Correct the date and time";
    setStep(step3, !done2 ? "locked" : done3 ? "done" : "active");
    refCard.hidden = mode !== "shift";
    copyBlock.hidden = mode !== "shift";
    clockRow.hidden = mode === "zone";
    keepClockRow.hidden = mode !== "zone";
    correctLabel.textContent = mode === "set" ? "New date and time" : mode === "zone" ? "New time zone" : "Correct date and time for this photo";
    if (mode === "shift") {
      const ref = state.reference ? store.get(state.reference) : null;
      refTitle.textContent = state.referenceTitle;
      refDetail.textContent = state.referenceDetail;
      refDetail.hidden = !state.referenceDetail;
      refEarliest.hidden = !(state.referenceIsEarliest && selected > 1);
      refPosition.textContent = state.referencePosition;
      refBack.disabled = !state.canStepBack;
      refForward.disabled = !state.canStepForward;
      clear(refThumb);
      if (ref?.thumb) refThumb.append(el("img", { src: ref.thumb, alt: "" }));
      else refThumb.append(photoIcon());
      if (state.correctedReference && document.activeElement !== dateInput && document.activeElement !== timeInput) {
        setClock(state.correctedReference);
      }
      const canPick = state.reference !== null && store.timePickableCount() > 0;
      pickTimeButton.textContent = picking ? "Cancel" : PICK_TIME_BUTTON_TEXT;
      pickTimeButton.disabled = !picking && !canPick;
      pickTimeButton.title = picking ? "Stop picking a photo" : canPick ? PICK_TIME_BUTTON_TIP : PICK_TIME_DISABLED_TIP;
      pickTimeButton.classList.toggle("on", picking);
      pickTimeButton.setAttribute("aria-pressed", picking ? "true" : "false");
      timeFromFileButton.disabled = state.reference === null || picking;
      sourceCard.hidden = !state.sourceCard;
      if (state.sourceCard) {
        sourceTitle.textContent = state.sourceCard.title;
        sourceDetail.textContent = state.sourceCard.detail;
        clear(sourceThumb);
        const source = store.timeSourceId ? store.get(store.timeSourceId) : null;
        if (source?.thumb) sourceThumb.append(el("img", { src: source.thumb, alt: "" }));
        else sourceThumb.append(photoIcon());
      }
    } else if (mode === "set" && setValue && document.activeElement !== dateInput && document.activeElement !== timeInput) {
      setClock(setValue);
    }
    // The zone drop-down: the items for this date, red when the photos have
    // more than one zone.
    clear(zoneSelect);
    for (const [key, label] of state.zoneItems) zoneSelect.append(el("option", { value: key, textContent: label }));
    zoneSelect.value = state.zoneKey;
    zoneSelect.classList.toggle("mixed", state.zoneMixed);
    zoneSelect.title = mode === "zone" ? (state.zoneMixed ? MIXED_ZONES_CHANGE_TIP : "The new time zone for the selected photos") : state.zoneTooltip;
    zoneSelect.disabled = selected === 0 || picking;
    for (const input of [dateInput, timeInput]) input.disabled = picking || (mode === "shift" && state.reference === null);
    keepClockCheck.checked = keepClock;
    keepClockCheck.disabled = picking;

    setStep(step4, done3 ? "active" : "locked");
    hint.textContent = state.hint;
    hint.className = `hint ${state.hintTone}`;
    hint.hidden = !state.hint;
    clear(rows);
    for (const row of state.rows) {
      const newText = row.kind === "change" ? `→  ${row.new}` : row.new;
      const line = el("div", { className: `change-row ${row.kind}`, title: `${row.name}\nOriginal: ${row.current}\nNew: ${row.new || "Not changed"}` }, [
        el("span", { className: "change-name", textContent: row.name }),
        el("span", { className: "change-current", textContent: row.current }),
        el("span", { className: "change-new", textContent: newText }),
      ]);
      rows.append(line);
    }
    rows.hidden = state.rows.length === 0;
    applyButton.textContent = state.applyLabel;
    applyButton.disabled = !state.canApply || picking;
  }

  function setClock(iso) {
    dateInput.value = iso.slice(0, 10);
    timeInput.value = iso.slice(11, 19);
  }

  store.subscribe((change) => {
    if (change.type === "removed") {
      // The reference or the source left the list: start over.
      if ((reference && !store.get(reference)) || (store.timeSourceId === null && sourceInfo === null && state?.sourceCard && !sourceInfo)) {
        reference = null;
      }
    }
    if (change.type === "selection" && store.selection.size === 0 && mode !== null) {
      // Deselect All goes back to step 1.
      mode = null;
      choicesOpen = false;
    }
    if (["info", "selection", "view", "added", "removed", "thumb"].includes(change.type)) refresh();
  });

  return {
    refresh,
    reset,
    state: () => state,
    /** A photo whose time is used: one in the list (id) or from the computer (info). */
    setSource(id, info = null) {
      sourceInfo = info;
      typedReference = null;
      store.setTimeSource(id);
      refresh();
    },
    referenceName: () => (state?.reference ? store.get(state.reference)?.name : null) ?? "the reference photo",
    setPythonReady(ok, error) {
      pythonReady = ok;
      pythonNote.textContent = ok ? "" : `The date logic could not load: ${error}`;
      pythonNote.hidden = ok;
      refresh();
    },
  };
}
