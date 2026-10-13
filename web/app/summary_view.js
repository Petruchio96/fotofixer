// The Photos to Change pane. In this version it holds the selection summary
// and the tabs; the Location and Date & Time editors come in the next
// phases (docs/ROADMAP.md, Part 3).

import { el, clear } from "./dom.js";

export function createSummaryView(container, store, { saveModeText }) {
  const title = el("div", { className: "summary-title" });
  const text = el("div", { className: "summary-text" });
  const tabs = el("div", { className: "tabs", role: "tablist" }, [
    el("button", { className: "tab on", role: "tab", disabled: true, title: "Add, replace, or remove a location (coming in the next phase of the web version)" }, "Location"),
    el("button", { className: "tab", role: "tab", disabled: true, title: "Shift or set dates, or change the time zone (coming in a later phase of the web version)" }, "Date & Time"),
  ]);
  const note = el("div", { className: "pane-note" }, [
    el("p", { textContent: "Editing locations and dates comes in the next phases of the web version. This version opens photos and shows which have GPS." }),
    el("p", { textContent: saveModeText.long }),
  ]);
  const pane = el("section", { className: "panel pane-change" }, [
    el("div", { className: "pane-hdr change" }, [el("div", { className: "pane-title", textContent: "PHOTOS TO CHANGE" })]),
    el("div", { className: "summary" }, [title, text]),
    tabs,
    note,
  ]);
  clear(container);
  container.append(pane);

  function render() {
    const summary = store.summary();
    title.textContent = summary.title;
    text.textContent = summary.text;
  }
  store.subscribe(render);
  render();
}
