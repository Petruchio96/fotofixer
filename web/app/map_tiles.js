// The map's tile sources, the same as the desktop's core/map_tiles.py (a
// test checks the addresses and zoom limits match). Plain data, no DOM.

export const MIN_ZOOM = 2;
export const MAX_ZOOM = 19;

// OpenStreetMap's own tile server. Its usage policy asks for an identifying
// referer (the container sends one), honoring cache headers, no bulk
// downloads, and this credit.
export const STREET_MAP = {
  key: "street",
  name: "Street",
  urlTemplate: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  maxZoom: 19,
  attributionHtml: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  coverageNote: "",
  needsKey: false,
};

// USGS National Map orthoimagery: US government data with no use
// constraints, United States only, detailed to zoom 16. Note the {y}/{x} order.
export const SATELLITE_MAP = {
  key: "satellite",
  name: "US Satellite",
  urlTemplate: "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}",
  maxZoom: 16,
  attributionHtml: 'Imagery: <a href="https://www.usgs.gov/programs/national-geospatial-program/national-map">USGS The National Map</a>',
  coverageNote: "Satellite imagery covers the United States only.",
  needsKey: false,
};

// Esri World Imagery, worldwide and detailed to street level, with the
// visitor's own API key (free ArcGIS Location Platform account). The key
// goes only to Esri, in the tile address (the service takes no header).
export const ESRI_SATELLITE_MAP = {
  key: "esri",
  name: "Satellite",
  urlTemplate: "https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}?token={key}",
  maxZoom: 19,
  attributionHtml: 'Powered by <a href="https://www.esri.com">Esri</a> | Source: Esri, Vantor, GeoEye, Earthstar Geographics, CNES/Airbus DS, USDA, USGS, AeroGRID, IGN, and the GIS User Community',
  coverageNote: "",
  needsKey: true,
};

export const TILE_SOURCES = { street: STREET_MAP, satellite: SATELLITE_MAP, esri: ESRI_SATELLITE_MAP };

// Corners of the lower 48 United States (northwest, southeast), shown when
// there are no photos with GPS to show.
export const CONTIGUOUS_US_CORNERS = [[49.38, -124.85], [24.52, -66.95]];

/** The tile address for one tile (the key URL-encoded). */
export function tileUrl(source, zoom, x, y, apiKey = "") {
  return source.urlTemplate
    .replace("{z}", zoom).replace("{x}", x).replace("{y}", y)
    .replace("{key}", encodeURIComponent(apiKey));
}
