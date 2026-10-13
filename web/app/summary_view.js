// The Photos to Change pane: the selection summary, the tabs, and the two
// tab pages (location_view.js and date_view.js). The Photo List follows
// the tab shown (GPS groups or camera groups).

import { el, clear } from "./dom.js";
import { createLocationView } from "./location_view.js";
import { createDateView } from "./date_view.js";

export function createChangePane(container, store, { saveModeText, locationActions, dateActions, onTabChange }) {
  const title = el("div", { className: "summary-title" });
  const text = el("div", { className: "summary-text" });
  const tabButtons = {
    location: el("button", { className: "tab on", role: "tab", "aria-selected": "true", title: "Add, replace, or remove a location", onclick: () => showTab("location") }, "Location"),
    date: el("button", { className: "tab", role: "tab", "aria-selected": "false", title: "Shift or set dates, or change the time zone", onclick: () => showTab("date") }, "Date & Time"),
  };
  const tabs = el("div", { className: "tabs", role: "tablist" }, Object.values(tabButtons));
  const locationTab = el("div", { className: "tab-page" });
  const dateTab = el("div", { className: "tab-page date-page", hidden: true });
  const note = el("div", { className: "pane-note" }, [el("p", { textContent: saveModeText.long })]);
  const pane = el("section", { className: "panel pane-change" }, [
    el("div", { className: "pane-hdr change" }, [el("div", { className: "pane-title", textContent: "PHOTOS TO CHANGE" })]),
    el("div", { className: "summary" }, [title, text]),
    tabs,
    locationTab,
    dateTab,
    note,
  ]);
  clear(container);
  container.append(pane);

  let dateState = null;
  const location = createLocationView(locationTab, store, locationActions);
  const date = createDateView(dateTab, store, {
    ...dateActions,
    onStateChange(state) {
      dateState = state;
      renderSummary();
      dateActions.onStateChange?.(state);
    },
  });

  function showTab(mode) {
    if (store.mode === mode) return;
    for (const [key, button] of Object.entries(tabButtons)) {
      button.classList.toggle("on", key === mode);
      button.setAttribute("aria-selected", key === mode ? "true" : "false");
    }
    locationTab.hidden = mode !== "location";
    dateTab.hidden = mode !== "date";
    onTabChange?.(mode);
    renderSummary();
  }

  function renderSummary() {
    if (store.mode === "date" && dateState) {
      title.textContent = dateState.title;
      text.textContent = dateState.summary;
      return;
    }
    const summary = store.summary();
    title.textContent = summary.title;
    text.textContent = summary.text;
  }
  store.subscribe(renderSummary);
  renderSummary();

  return { location, date, showTab };
}
