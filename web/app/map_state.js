// The map dialog's logic that needs no map: which satellite source applies,
// the Back history of New Locations set on the map, which photo dots share
// a spot, and the readout text. Plain JavaScript, tested in Node.

import { SATELLITE_MAP, ESRI_SATELLITE_MAP } from "./map_tiles.js";

/** Satellite is Esri with the visitor's key, USGS without one. */
export function satelliteSourceFor(apiKey) {
  return apiKey ? ESRI_SATELLITE_MAP : SATELLITE_MAP;
}

/**
 * New Location before each change made on the map (clicks, dropped pins,
 * Clear, Use This Location), newest last, so Back can step through them.
 * Emptied each time the map opens.
 */
export class MapHistory {
  constructor() {
    this.entries = [];
  }

  remember(fields) {
    this.entries.push({ latitude: fields.latitude, longitude: fields.longitude, sourceId: fields.sourceId ?? null });
  }

  get canGoBack() {
    return this.entries.length > 0;
  }

  back() {
    return this.entries.pop() ?? null;
  }

  clear() {
    this.entries = [];
  }
}

// Photos whose dots are this close on screen look like one dot and share
// one preview ("1 of 2"); farther apart, each dot is its own.
export const SAME_SPOT_PIXELS = 2;

/**
 * The photos at the clicked dot: the clicked one and any others drawn
 * within SAME_SPOT_PIXELS of it. points: [{id, x, y}] in screen pixels.
 */
export function photosAtSpot(points, clickedId, tolerance = SAME_SPOT_PIXELS) {
  const clicked = points.find((point) => point.id === clickedId);
  if (!clicked) return [];
  return points
    .filter((point) => Math.hypot(point.x - clicked.x, point.y - clicked.y) <= tolerance)
    .map((point) => point.id);
}

// Names listed in a dot's hover hint before "and N more".
const HOVER_NAMES = 3;

export function hoverText(names) {
  if (names.length <= HOVER_NAMES) return names.join(", ");
  return `${names.slice(0, HOVER_NAMES).join(", ")} and ${names.length - HOVER_NAMES} more`;
}

export function readoutText(latitude, longitude) {
  return `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`;
}

/** The button that closes the map: Select Location once a pin is set, else Cancel. */
export function doneButtonLabel(hasLocation) {
  return hasLocation ? "Select Location" : "Cancel";
}
