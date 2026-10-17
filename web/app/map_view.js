// Pick from a Map: a dialog with a Leaflet map as another source for New
// Location (like the desktop's gui/widgets/map_window.py). No new write
// path: a click or a dropped pin only fills the latitude/longitude fields
// (through actions.pick), and Apply writes them as usual. The photos in
// the Photo List with GPS show as dots; a dot's preview can copy its
// location. Leaflet (web/vendor/leaflet/) loads the first time the map
// opens.

import { el, clear, gpsPin, photoIcon } from "./dom.js";
import { STREET_MAP, CONTIGUOUS_US_CORNERS, MIN_ZOOM, MAX_ZOOM } from "./map_tiles.js";
import { satelliteSourceFor, MapHistory, photosAtSpot, hoverText, readoutText, doneButtonLabel } from "./map_state.js";

// The margin around the photos when the map fits them, and the closest it
// zooms for that (a single photo gets zoom 15); the pin opens at 15 too.
const FIT_PADDING = 0.12;
const FIT_MAX_ZOOM = 15;
const PIN_ZOOM = 15;
const BLUE = "#1f6feb";
const ORANGE = "#d97706";

let leafletPromise = null;
function loadLeaflet() {
  leafletPromise ??= import("../vendor/leaflet/leaflet.esm.js");
  return leafletPromise;
}

/**
 * store: the PhotoStore (dots: photos with GPS; orange when selected).
 * getFields(): {latitude, longitude, sourceId} texts for the Back history.
 * getLocation(): the parsed New Location {latitude, longitude} or null.
 * getEsriKey(): the visitor's ArcGIS key, "" for none.
 * actions: pick(latitude, longitude), usePhoto(id), clear(), back(entry).
 */
export function createMapDialog({ store, getFields, getLocation, getEsriKey, actions }) {
  let L = null;
  let map = null;
  let dialog = null;
  let streetLayer = null;
  let satelliteLayer = null;
  let satelliteSource = null;
  let activeLayer = null;
  let pinMarker = null;
  let dotLayer = null;
  let dots = new Map(); // id -> circle marker
  let popup = null;
  let popupIds = [];
  let popupIndex = 0;
  let esriFailed = false;
  const history = new MapHistory();

  // ----- the dialog -----
  const streetButton = el("button", { className: "btn", title: "Show the OpenStreetMap street map", onclick: () => showSource("street") }, STREET_MAP.name);
  const satelliteButton = el("button", { className: "btn", title: "Show satellite imagery", onclick: () => showSource("satellite") }, "Satellite");
  const showPhotosButton = el("button", { className: "btn", title: "Zoom to fit every photo in the Photo List that has GPS", onclick: () => fitPhotos() }, "Show All Photo Locations");
  const showPinButton = el("button", { className: "btn", title: "Center the map on the New Location pin", onclick: () => goToPin() }, "Go to Selected Location");
  const zoomInButton = el("button", { className: "btn sq", title: "Zoom in (or scroll the mouse wheel)", "aria-label": "Zoom in", onclick: () => map?.zoomIn() }, "+");
  const zoomOutButton = el("button", { className: "btn sq", title: "Zoom out (or scroll the mouse wheel)", "aria-label": "Zoom out", onclick: () => map?.zoomOut() }, "−");
  const toolbar = el("div", { className: "map-bar" }, [
    streetButton, satelliteButton, el("span", { className: "sep" }), showPhotosButton, showPinButton,
    el("span", { className: "spacer" }), zoomInButton, zoomOutButton,
  ]);
  const mapBox = el("div", { className: "map-box", "aria-label": "Map" });
  const useUsButton = el("button", { className: "btn", title: "Show USGS imagery instead (United States only)", onclick: () => useUsSatelliteInstead() }, "Use US Satellite Instead");
  const esriBanner = el("div", { className: "map-banner", hidden: true }, [
    el("span", { textContent: "Esri's satellite imagery didn't load. Check the key in Settings, or your connection." }), useUsButton,
  ]);
  const coverageNote = el("div", { className: "map-note", hidden: true });
  const mapArea = el("div", { className: "map-area" }, [mapBox, esriBanner, coverageNote]);
  const readout = el("span", { className: "readout" });
  const readoutRow = el("div", { className: "map-readout" }, [
    readout, el("span", { className: "hint", textContent: "Click the map to move the pin. Drag to pan, scroll or pinch to zoom." }),
  ]);
  const backButton = el("button", { className: "btn", disabled: true, title: "Nothing to go back to yet", onclick: () => goBack() }, "Back");
  const clearButton = el("button", { className: "btn", title: "Empty New Location and remove the pin", onclick: () => clearLocation() }, "Clear");
  const doneButton = el("button", { className: "btn", title: "Close the map and keep the fields as they were", onclick: () => close() }, "Cancel");
  const bottomBar = el("div", { className: "map-bar bottom" }, [backButton, clearButton, el("span", { className: "spacer" }), doneButton]);
  const loading = el("div", { className: "map-loading", textContent: "Loading the map…" });

  function buildDialog() {
    dialog = el("dialog", { className: "map-dialog", "aria-label": "Pick from a Map" }, [toolbar, mapArea, readoutRow, bottomBar, loading]);
    dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
    document.body.append(dialog);
  }

  // ----- Leaflet -----
  async function buildMap() {
    L = await loadLeaflet();
    map = L.map(mapBox, {
      zoomControl: false,
      minZoom: MIN_ZOOM,
      maxZoom: MAX_ZOOM,
      worldCopyJump: true,
      attributionControl: true,
    });
    map.attributionControl.setPrefix(false);
    streetLayer = tileLayer(STREET_MAP, "");
    dotLayer = L.layerGroup().addTo(map);
    map.on("click", (event) => pickOnMap(event.latlng));
    map.on("mousemove", (event) => { readout.textContent = readoutText(event.latlng.lat, event.latlng.lng); });
    map.on("popupclose", () => { popup = null; popupIds = []; });
    loading.hidden = true;
  }

  function tileLayer(source, apiKey) {
    const layer = L.tileLayer(source.urlTemplate, {
      maxZoom: MAX_ZOOM,
      maxNativeZoom: source.maxZoom,
      attribution: source.attributionHtml,
      key: encodeURIComponent(apiKey),
    });
    if (source.needsKey) {
      layer.on("tileerror", () => {
        if (esriFailed) return;
        esriFailed = true;
        esriBanner.hidden = false;
      });
    }
    return layer;
  }

  function showSource(which) {
    if (!map) return;
    const next = which === "satellite" ? satelliteLayer : streetLayer;
    if (activeLayer === next) return;
    if (activeLayer) map.removeLayer(activeLayer);
    activeLayer = next.addTo(map);
    streetButton.classList.toggle("on", which === "street");
    satelliteButton.classList.toggle("on", which === "satellite");
    coverageNote.hidden = which !== "satellite" || !satelliteSource.coverageNote;
    coverageNote.textContent = satelliteSource.coverageNote;
  }

  function setSatelliteSource(source) {
    satelliteSource = source;
    const wasActive = activeLayer === satelliteLayer && satelliteLayer !== null;
    if (wasActive) map.removeLayer(satelliteLayer);
    satelliteLayer = tileLayer(source, source.needsKey ? getEsriKey() : "");
    satelliteButton.textContent = source.name;
    satelliteButton.title = source.needsKey
      ? "Esri World Imagery, worldwide, with the key saved in Settings"
      : "USGS imagery, United States only (set an Esri key in Settings for worldwide imagery)";
    if (wasActive) {
      activeLayer = satelliteLayer.addTo(map);
      coverageNote.hidden = !source.coverageNote;
      coverageNote.textContent = source.coverageNote;
    }
  }

  function useUsSatelliteInstead() {
    esriBanner.hidden = true;
    setSatelliteSource(satelliteSourceFor(""));
    showSource("satellite");
  }

  // ----- the pin -----
  function pinIcon() {
    const pin = gpsPin(ORANGE, "New Location pin");
    pin.setAttribute("width", "34");
    pin.setAttribute("height", "44");
    return L.divIcon({ className: "map-pin", html: pin, iconSize: [34, 44], iconAnchor: [17, 44] });
  }

  function setPin(location, { reveal = false } = {}) {
    if (!map) return;
    if (!location) {
      if (pinMarker) { map.removeLayer(pinMarker); pinMarker = null; }
    } else {
      const latlng = L.latLng(location.latitude, location.longitude);
      if (!pinMarker) {
        pinMarker = L.marker(latlng, { icon: pinIcon(), draggable: true, title: "", keyboard: false }).addTo(map);
        pinMarker.on("dragend", () => {
          const at = pinMarker.getLatLng();
          remember();
          actions.pick(at.lat, at.lng);
        });
      } else {
        pinMarker.setLatLng(latlng);
      }
      if (reveal && !map.getBounds().contains(latlng)) map.panTo(latlng);
    }
    updateButtons();
  }

  function pickOnMap(latlng) {
    remember();
    actions.pick(latlng.lat, latlng.lng);
  }

  function goToPin() {
    const location = getLocation();
    if (!map || !location) return;
    map.setView([location.latitude, location.longitude], Math.max(map.getZoom(), PIN_ZOOM));
  }

  // ----- photo dots -----
  function photosWithGps() {
    return store.order.map((id) => store.get(id)).filter((photo) => photo.gps);
  }

  function refreshDots() {
    if (!map) return;
    const wanted = new Map(photosWithGps().map((photo) => [photo.id, photo]));
    for (const [id, marker] of dots) {
      if (!wanted.has(id)) { dotLayer.removeLayer(marker); dots.delete(id); }
    }
    for (const [id, photo] of wanted) {
      const selected = store.selection.has(id);
      const latlng = [photo.gps.latitude, photo.gps.longitude];
      let marker = dots.get(id);
      if (!marker) {
        marker = L.circleMarker(latlng, { radius: 7, color: "#ffffff", weight: 2.5, fillColor: selected ? ORANGE : BLUE, fillOpacity: 1, bubblingMouseEvents: false });
        marker.bindTooltip(() => hoverText(spotIds(id).map((other) => store.get(other)?.name ?? "")), { direction: "top", offset: [0, -8] });
        marker.on("click", () => showPreview(id));
        marker.addTo(dotLayer);
        dots.set(id, marker);
      } else {
        marker.setLatLng(latlng);
        marker.setStyle({ fillColor: selected ? ORANGE : BLUE });
      }
    }
    if (popup && popupIds.length && !popupIds.every((id) => dots.has(id))) map.closePopup();
    updateButtons();
  }

  /** The photos drawn at the same spot as this one (within 2 px). */
  function spotIds(id) {
    const points = [...dots].map(([other, marker]) => {
      const point = map.latLngToContainerPoint(marker.getLatLng());
      return { id: other, x: point.x, y: point.y };
    });
    return photosAtSpot(points, id);
  }

  function showPreview(id) {
    popupIds = spotIds(id);
    popupIndex = Math.max(0, popupIds.indexOf(id));
    const marker = dots.get(id);
    popup = L.popup({ closeButton: false, className: "map-preview", offset: [0, -10], autoPanPadding: [20, 20] })
      .setLatLng(marker.getLatLng())
      .setContent(previewContent())
      .openOn(map);
  }

  function previewContent() {
    const id = popupIds[popupIndex];
    const photo = store.get(id);
    const thumb = el("button", { className: "preview-thumb", title: "Zoom the map to this photo's location", onclick: () => zoomToPhoto(id) });
    if (photo.thumb) thumb.append(el("img", { src: photo.thumb, alt: "" }));
    else thumb.append(photoIcon());
    const name = el("div", { className: "preview-name", textContent: photo.name });
    // Like the desktop app: thumbnail, name, "‹ 1 of 2 ›" (several photos at one spot), then the button.
    const parts = [thumb, name];
    if (popupIds.length > 1) {
      const previous = el("button", { className: "preview-step", title: "Previous photo at this spot", onclick: (event) => stepPreview(event, -1) }, "‹");
      const next = el("button", { className: "preview-step", title: "Next photo at this spot", onclick: (event) => stepPreview(event, 1) }, "›");
      const count = el("span", { className: "preview-count", textContent: `${popupIndex + 1} of ${popupIds.length}` });
      parts.push(el("div", { className: "preview-row" }, [previous, count, next]));
    }
    // A selected photo can be the source too: it is deselected when used.
    const use = el("button", {
      className: "use",
      title: "Copy this photo's location into New Location",
      onclick: () => { remember(); actions.usePhoto(id); },
    }, "Use This Location");
    parts.push(use);
    return el("div", { className: "preview" }, parts);
  }

  function stepPreview(event, offset) {
    // setContent below detaches the clicked button, so Leaflet could no
    // longer tell the click came from the popup: it would close the popup
    // and move the New Location pin. Keep the click from reaching the map.
    event.stopPropagation();
    popupIndex = (popupIndex + offset + popupIds.length) % popupIds.length;
    popup?.setContent(previewContent());
  }

  function zoomToPhoto(id) {
    const photo = store.get(id);
    if (!photo?.gps) return;
    map.setView([photo.gps.latitude, photo.gps.longitude], Math.max(map.getZoom(), PIN_ZOOM));
  }

  function fitPhotos() {
    const photos = photosWithGps();
    if (!photos.length) return;
    fitPoints(photos.map((photo) => [photo.gps.latitude, photo.gps.longitude]));
  }

  function fitPoints(points) {
    const size = map.getSize();
    const padding = L.point(Math.round(size.x * FIT_PADDING), Math.round(size.y * FIT_PADDING));
    map.fitBounds(L.latLngBounds(points), { padding, maxZoom: FIT_MAX_ZOOM, animate: false });
  }

  /** Where the map opens: the pin, else the photos with GPS, else the lower 48. */
  function showOpeningView() {
    const location = getLocation();
    if (location) {
      map.setView([location.latitude, location.longitude], PIN_ZOOM, { animate: false });
    } else if (photosWithGps().length) {
      fitPhotos();
    } else {
      fitPoints(CONTIGUOUS_US_CORNERS);
    }
  }

  // ----- Back and Clear -----
  function remember() {
    history.remember(getFields());
    updateButtons();
  }

  function goBack() {
    const entry = history.back();
    if (entry) actions.back(entry);
    updateButtons();
  }

  function clearLocation() {
    const fields = getFields();
    if (fields.latitude || fields.longitude) remember();
    actions.clear();
  }

  function updateButtons() {
    const location = getLocation();
    const dotCount = dots.size;
    showPhotosButton.disabled = dotCount === 0;
    showPhotosButton.title = dotCount ? "Zoom to fit every photo in the Photo List that has GPS" : "No photo in the Photo List has GPS yet";
    showPinButton.disabled = !location;
    showPinButton.title = location ? "Center the map on the New Location pin" : "Set a New Location first (click the map)";
    backButton.disabled = !history.canGoBack;
    backButton.title = history.canGoBack ? "Go back to the previous New Location set on this map" : "Nothing to go back to yet";
    const fields = getFields();
    clearButton.disabled = !fields.latitude && !fields.longitude;
    doneButton.textContent = doneButtonLabel(location !== null);
    doneButton.classList.toggle("accent", location !== null);
    doneButton.title = location ? "Close the map; the pin's coordinates are the New Location" : "Close the map and keep the fields as they were";
  }

  // ----- open and close -----
  async function open() {
    if (!dialog) buildDialog();
    if (dialog.open) return;
    dialog.showModal();
    if (!map) await buildMap();
    history.clear();
    esriFailed = false;
    esriBanner.hidden = true;
    setSatelliteSource(satelliteSourceFor(getEsriKey()));
    // Always opens on the street map.
    if (activeLayer) map.removeLayer(activeLayer);
    activeLayer = null;
    showSource("street");
    map.invalidateSize();
    setPin(getLocation());
    refreshDots();
    showOpeningView();
    readout.textContent = "";
    updateButtons();
    mapBox.focus();
  }

  function close() {
    if (!dialog?.open) return;
    map?.closePopup();
    dialog.close();
    actions.closed?.();
  }

  return {
    open,
    close,
    isOpen: () => Boolean(dialog?.open),
    setPin,
    refreshDots,
    updateButtons,
  };
}

export { clear };
