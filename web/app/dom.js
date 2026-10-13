// Small DOM helpers. Every button must have a hover hint (title): el()
// refuses to make one without it, and a test checks the static HTML too.

export function el(tag, attrs = {}, children = []) {
  if (tag === "button" && !attrs.title) {
    throw new Error(`button "${attrs.textContent ?? ""}" needs a title (hover hint)`);
  }
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "className") node.className = value;
    else if (key === "textContent") node.textContent = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (key in node && typeof value === "boolean") node[key] = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of Array.isArray(children) ? children : [children]) {
    if (child == null) continue;
    node.append(child);
  }
  return node;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function svgElement(name, attrs) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

/** The GPS badge pin, the same shape as the desktop's icons.py pin. */
export function gpsPin(color = "#1f6feb", label = "Has GPS") {
  const svg = svgElement("svg", { viewBox: "0 0 22 28", width: "22", height: "28", role: "img", "aria-label": label, class: "pin" });
  svg.append(
    svgElement("path", {
      d: "M11 1.5C5.8 1.5 1.5 5.7 1.5 10.9c0 7 9.5 15.6 9.5 15.6s9.5-8.6 9.5-15.6C20.5 5.7 16.2 1.5 11 1.5z",
      fill: color, stroke: "#ffffff", "stroke-width": "2",
    }),
    svgElement("circle", { cx: "11", cy: "11", r: "3.2", fill: "#ffffff" }),
  );
  return svg;
}

/** The photo outline shown while a thumbnail loads or when none exists. */
export function photoIcon() {
  const svg = svgElement("svg", { viewBox: "0 0 40 30", width: "40", height: "30", "aria-hidden": "true" });
  svg.append(
    svgElement("path", { d: "M2 28 L14 10 L22 20 L28 14 L38 28 Z", fill: "currentColor" }),
    svgElement("circle", { cx: "31", cy: "7", r: "4", fill: "currentColor" }),
  );
  return svg;
}

/** The folder icon on the Open a Folder button. */
export function folderIcon() {
  const svg = svgElement("svg", { viewBox: "0 0 18 16", width: "18", height: "16", "aria-hidden": "true" });
  svg.append(svgElement("path", {
    d: "M1 3.5 A1.5 1.5 0 0 1 2.5 2 H7 L8.5 3.5 H15.5 A1.5 1.5 0 0 1 17 5 V13 A1.5 1.5 0 0 1 15.5 14.5 H2.5 A1.5 1.5 0 0 1 1 13 Z",
    fill: "none", stroke: "currentColor", "stroke-width": "1.6",
  }));
  return svg;
}

/** The map icon on the Pick from a Map button. */
export function mapIcon() {
  const svg = svgElement("svg", { viewBox: "0 0 18 18", width: "18", height: "18", "aria-hidden": "true" });
  svg.append(
    svgElement("path", { d: "M1.5 4.5 L6.5 2.5 L11.5 4.5 L16.5 2.5 V13.5 L11.5 15.5 L6.5 13.5 L1.5 15.5 Z", fill: "none", stroke: "currentColor", "stroke-width": "1.5" }),
    svgElement("path", { d: "M6.5 2.5 V13.5 M11.5 4.5 V15.5", stroke: "currentColor", "stroke-width": "1.5" }),
  );
  return svg;
}
