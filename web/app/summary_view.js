// The Photos to Change pane: the selection summary, the tabs, and the
// Location tab (location_view.js). The Date & Time tab comes in a later
// phase (docs/ROADMAP.md, Part 3).

import { el, clear } from "./dom.js";
import { createLocationView } from "./location_view.js";

export function createChangePane(container, store, { saveModeText, locationActions }) {
  const title = el("div", { className: "summary-title" });
  const text = el("div", { className: "summary-text" });
  const tabs = el("div", { className: "tabs", role: "tablist" }, [
    el("button", { className: "tab on", role: "tab", "aria-selected": "true", title: "Add, replace, or remove a location" }, "Location"),
    el("button", { className: "tab", role: "tab", disabled: true, title: "Shift or set dates, or change the time zone (coming in a later phase of the web version)" }, "Date & Time"),
  ]);
  const locationTab = el("div", { className: "tab-page" });
  const note = el("div", { className: "pane-note" }, [el("p", { textContent: saveModeText.long })]);
  const pane = el("section", { className: "panel pane-change" }, [
    el("div", { className: "pane-hdr change" }, [el("div", { className: "pane-title", textContent: "PHOTOS TO CHANGE" })]),
    el("div", { className: "summary" }, [title, text]),
    tabs,
    locationTab,
    note,
  ]);
  clear(container);
  container.append(pane);

  const location = createLocationView(locationTab, store, locationActions);

  function render() {
    const summary = store.summary();
    title.textContent = summary.title;
    text.textContent = summary.text;
  }
  store.subscribe(render);
  render();

  return { location };
}
