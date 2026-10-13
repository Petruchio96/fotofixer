// The Photo List pane: header (Add Photos, Clear List), the Show filter,
// the selection bar, the grid of tiles in GPS groups, and the status row.
// It draws what the PhotoStore says and sends clicks back to it; the
// loading itself lives in main.js.

import { el, clear, gpsPin, photoIcon, folderIcon } from "./dom.js";
import { ACCEPT_ATTRIBUTE } from "./file_types.js";
import { tileTooltip } from "./photo_store.js";

// Show filter values, in button order, with their hover hints (as on the
// desktop, gui/widgets/browser_panel.py).
const GRID_FILTERS = [
  ["all", "All", "Show every photo in the list"],
  ["needs", "Needs GPS", "Show only the photos without GPS coordinates"],
  ["has", "Has GPS", "Show only the photos that have GPS coordinates"],
];

/**
 * actions: {openFolder, addFiles(fileList), dropEntries(dataTransfer),
 *           clearList, removeSelected, cancelLoading}
 */
export function createPhotoListView(container, store, actions, { canOpenFolder }) {
  const tiles = new Map(); // id -> tile element
  let anchorId = null; // for Shift-click ranges
  let menuOpen = false;

  // ----- header -----
  const fileInput = el("input", { type: "file", multiple: true, accept: ACCEPT_ATTRIBUTE, className: "hidden-input" });
  const folderInput = el("input", { type: "file", multiple: true, className: "hidden-input" });
  folderInput.setAttribute("webkitdirectory", "");
  fileInput.addEventListener("change", () => { actions.addFiles(fileInput.files); fileInput.value = ""; });
  folderInput.addEventListener("change", () => { actions.addFiles(folderInput.files); folderInput.value = ""; });

  const menu = el("div", { className: "add-menu-items", hidden: true, role: "menu" }, [
    canOpenFolder
      ? el("button", {
          className: "menu-item", role: "menuitem",
          title: "Choose a folder on this computer. The browser asks once for permission to save changes into it.",
          onclick: () => { closeMenu(); actions.openFolder(); },
        }, [folderIcon(), el("span", { textContent: "Open a Folder…" }), el("small", { textContent: "saves changes into your files" })])
      : null,
    el("button", {
      className: "menu-item", role: "menuitem",
      title: canOpenFolder ? "Choose photos. Photos chosen this way come back as downloads when changed." : "Choose photos from this computer or the Files app",
      onclick: () => { closeMenu(); fileInput.click(); },
    }, [photoIcon(), el("span", { textContent: "Choose Photos…" })]),
    "webkitdirectory" in folderInput
      ? el("button", {
          className: "menu-item", role: "menuitem",
          title: canOpenFolder ? "Choose a whole folder of photos. Photos chosen this way come back as downloads when changed." : "Choose a whole folder of photos",
          onclick: () => { closeMenu(); folderInput.click(); },
        }, [folderIcon(), el("span", { textContent: "Choose a Folder…" })])
      : null,
  ]);
  const addButton = el("button", {
    className: "hdr-btn", title: "Add photos or folders from this computer, or drop them on the list. Photos already in the list are skipped.",
    "aria-haspopup": "menu", onclick: () => (menuOpen ? closeMenu() : openMenu()),
  }, "+ Add Photos");
  const addMenu = el("div", { className: "add-menu" }, [addButton, menu, fileInput, folderInput]);
  const clearButton = el("button", {
    className: "hdr-outline", disabled: true, title: "Remove every photo from this list. Files are not changed or deleted.",
    onclick: () => actions.clearList(),
  }, "Clear List");
  const header = el("div", { className: "pane-hdr list" }, [
    el("div", { className: "pane-title", textContent: "PHOTO LIST" }),
    el("div", { className: "spacer" }),
    addMenu, clearButton,
  ]);

  function openMenu() { menu.hidden = false; menuOpen = true; addButton.setAttribute("aria-expanded", "true"); }
  function closeMenu() { menu.hidden = true; menuOpen = false; addButton.setAttribute("aria-expanded", "false"); }
  document.addEventListener("click", (event) => { if (menuOpen && !addMenu.contains(event.target)) closeMenu(); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && menuOpen) closeMenu(); });

  // ----- Show filter -----
  const filterButtons = {};
  const seg = el("div", { className: "seg", role: "group", "aria-label": "Show" });
  for (const [key, text, hint] of GRID_FILTERS) {
    filterButtons[key] = el("button", { title: hint, dataset: { filter: key }, onclick: () => store.setView(key) }, text);
    seg.append(filterButtons[key]);
  }
  const onlySelectedButton = el("button", {
    className: "toggle", disabled: true, "aria-pressed": "false",
    title: "Show only the selected photos (turns off when a view button is clicked)",
    onclick: () => store.setOnlySelected(!store.onlySelected),
  }, "Only Show Selected Photos");
  const filterRow = el("div", { className: "filter-row" }, [
    el("span", { className: "label", textContent: "Show" }), seg, el("span", { className: "gap" }), onlySelectedButton,
  ]);

  // ----- selection bar -----
  const selectionCount = el("span", { className: "count", textContent: "0 selected" });
  const selectAllButton = el("button", { className: "selbtn", title: "Select every photo shown (Ctrl+A)", onclick: () => store.selectAll() }, "Select All");
  const deselectAllButton = el("button", { className: "selbtn", disabled: true, title: "Deselect all photos", onclick: () => store.deselectAll() }, "Deselect All");
  const removeButton = el("button", {
    className: "selbtn", disabled: true,
    title: "Remove the selected photos from this list (Delete key). Files are not changed or deleted.",
    onclick: () => actions.removeSelected(),
  }, "✕  Remove from List");
  const selectionBar = el("div", { className: "selbar" }, [
    el("span", { className: "dot", "aria-hidden": "true", textContent: "●" }), selectionCount,
    el("span", { className: "sep", "aria-hidden": "true", textContent: "|" }), selectAllButton,
    el("span", { className: "sep", "aria-hidden": "true", textContent: "|" }), deselectAllButton,
    el("span", { className: "sep", "aria-hidden": "true", textContent: "|" }), removeButton,
  ]);

  // ----- grid -----
  const grid = el("div", { className: "grid", tabindex: "0", role: "listbox", "aria-multiselectable": "true", "aria-label": "Photos" });
  grid.addEventListener("click", (event) => {
    const tile = event.target.closest(".tile");
    if (!tile || !grid.contains(tile)) return;
    const id = tile.dataset.id;
    if (event.shiftKey && anchorId) store.selectRange(anchorId, id);
    else store.toggle(id);
    anchorId = id;
  });
  grid.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
      event.preventDefault();
      store.selectAll();
    } else if (event.key === "Delete" || event.key === "Backspace") {
      if (store.selection.size) {
        event.preventDefault();
        actions.removeSelected();
      }
    }
  });
  const gridBox = el("div", { className: "gridbox" }, [selectionBar, grid]);

  // ----- status row: loading progress or a message -----
  const statusText = el("span", { className: "status-text" });
  const cancelButton = el("button", { className: "selbtn", title: "Stop reading the remaining photos; the ones already read stay", onclick: () => actions.cancelLoading() }, "Cancel");
  const statusRow = el("div", { className: "status-row", hidden: true }, [statusText, cancelButton]);

  const body = el("div", { className: "pane-body" }, [filterRow, gridBox, statusRow]);
  const pane = el("section", { className: "panel pane-list" }, [header, body]);
  clear(container);
  container.append(pane);

  // ----- drag and drop on the whole pane -----
  let dragDepth = 0;
  pane.addEventListener("dragenter", (event) => { if (hasFiles(event)) { event.preventDefault(); dragDepth += 1; pane.classList.add("over"); } });
  pane.addEventListener("dragover", (event) => { if (hasFiles(event)) { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; } });
  pane.addEventListener("dragleave", () => { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) pane.classList.remove("over"); });
  pane.addEventListener("drop", (event) => {
    event.preventDefault();
    dragDepth = 0;
    pane.classList.remove("over");
    actions.dropEntries(event.dataTransfer);
  });
  function hasFiles(event) {
    return [...(event.dataTransfer?.types ?? [])].includes("Files");
  }

  // ----- drawing -----
  function tileFor(id) {
    let tile = tiles.get(id);
    if (!tile) {
      tile = el("button", { className: "tile", role: "option", dataset: { id }, title: "Reading…" }, [
        el("div", { className: "img" }), el("div", { className: "name" }),
      ]);
      tiles.set(id, tile);
    }
    return tile;
  }

  function updateTile(id) {
    const photo = store.get(id);
    const tile = tiles.get(id);
    if (!photo || !tile) return;
    tile.title = tileTooltip(photo);
    tile.querySelector(".name").textContent = photo.name;
    tile.classList.toggle("sel", store.selection.has(id));
    tile.classList.toggle("faded", store.isFaded(id));
    tile.classList.toggle("unread", photo.status === "error");
    tile.setAttribute("aria-selected", store.selection.has(id) ? "true" : "false");
    const img = tile.querySelector(".img");
    const state = photo.thumb ? "thumb" : photo.status === "pending" && !photo.thumbFailed ? "loading" : "none";
    if (img.dataset.state !== state || (state === "thumb" && img.dataset.src !== photo.thumb)) {
      clear(img);
      img.dataset.state = state;
      img.dataset.src = photo.thumb ?? "";
      img.classList.toggle("shimmer", state === "loading");
      img.classList.toggle("blank", state !== "thumb");
      if (state === "thumb") img.append(el("img", { src: photo.thumb, alt: "", draggable: false }));
      else if (state === "none") img.append(photoIcon());
    }
    const hasPin = img.querySelector(".pin") !== null;
    if (photo.gps && !hasPin) img.append(gpsPin());
    else if (!photo.gps && hasPin) img.querySelector(".pin").remove();
  }

  function renderGrid() {
    clear(grid);
    const groups = store.groups();
    groups.forEach((group, index) => {
      if (index > 0) grid.append(el("div", { className: "divider" }));
      grid.append(el("div", { className: `grp ${group.key}`, textContent: `● ${group.title}` }));
      const row = el("div", { className: "tiles" });
      for (const id of group.ids) {
        row.append(tileFor(id));
        updateTile(id);
      }
      grid.append(row);
    });
    const message = store.emptyMessage();
    if (message) grid.append(el("div", { className: "empty", textContent: message }));
    // Drop tiles of photos no longer in the list.
    for (const id of [...tiles.keys()]) if (!store.get(id)) tiles.delete(id);
  }

  function renderControls() {
    const counts = store.counts();
    const selected = store.selection.size;
    filterButtons.all.textContent = `All (${counts.total})`;
    filterButtons.needs.textContent = `Needs GPS (${counts.needs})`;
    filterButtons.has.textContent = `Has GPS (${counts.has})`;
    for (const [key, button] of Object.entries(filterButtons)) {
      const on = store.view === key && !store.onlySelected;
      button.classList.toggle("on", on);
      button.classList.toggle(key, on);
      button.setAttribute("aria-pressed", on ? "true" : "false");
    }
    onlySelectedButton.disabled = selected === 0 && !store.onlySelected;
    onlySelectedButton.classList.toggle("on", store.onlySelected);
    onlySelectedButton.setAttribute("aria-pressed", store.onlySelected ? "true" : "false");
    selectionCount.textContent = `${selected} selected`;
    selectionBar.classList.toggle("active", selected > 0);
    deselectAllButton.disabled = selected === 0;
    removeButton.disabled = selected === 0;
    selectAllButton.disabled = store.visibleIds().length === 0;
    clearButton.disabled = counts.total === 0;
  }

  store.subscribe((change) => {
    if (change.type === "info" || change.type === "thumb") {
      // A photo's group can change once its GPS is known.
      if (change.type === "info") renderGrid();
      else updateTile(change.id);
      renderControls();
      return;
    }
    if (change.type === "selection") {
      for (const id of store.visibleIds()) updateTile(id);
      renderControls();
      return;
    }
    renderGrid();
    renderControls();
  });
  renderGrid();
  renderControls();

  return {
    /** Show "Reading photos… 3 of 12" with Cancel, or hide the row. */
    setProgress(progress) {
      if (!progress) {
        statusRow.hidden = true;
        return;
      }
      statusText.textContent = `Reading photos… ${progress.done} of ${progress.total}`;
      cancelButton.hidden = false;
      statusRow.hidden = false;
    },
    /** A one-line message under the grid (no Cancel). */
    setMessage(text) {
      statusText.textContent = text;
      cancelButton.hidden = true;
      statusRow.hidden = !text;
    },
    focusGrid() {
      grid.focus();
    },
  };
}
