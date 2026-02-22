/**
 * Esri World Imagery tile URLs — same approach as modules/ground_verifier.py
 * (fetch_satellite_image_esri). No API key required.
 * @see https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer
 */

const TILE_BASE =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile";

/**
 * Convert lat/lng to slippy-map tile coordinates at given zoom.
 * Matches Python _latlon_to_tile in ground_verifier.py.
 */
export function latLngToTile(
  lat: number,
  lng: number,
  zoom: number
): { x: number; y: number } {
  const n = 2 ** zoom;
  const x = Math.floor(((lng + 180) / 360) * n);
  const latRad = (lat * Math.PI) / 180;
  const y = Math.floor(
    ((1 - Math.asinh(Math.tan(latRad)) / Math.PI) / 2) * n
  );
  return { x, y };
}

/**
 * Get the Esri World Imagery tile URL for a given lat/lng and zoom.
 */
export function getEsriTileUrl(lat: number, lng: number, zoom: number): string {
  const { x, y } = latLngToTile(lat, lng, zoom);
  return `${TILE_BASE}/${zoom}/${y}/${x}`;
}

/**
 * Get tile coordinates for a grid of tiles around a center point.
 * grid=2 → 2x2 tiles (e.g. -1,0 and 0,1 in x and y).
 */
export function getEsriTileGridUrls(
  lat: number,
  lng: number,
  zoom: number,
  gridSize: number = 2
): string[][] {
  const { x, y } = latLngToTile(lat, lng, zoom);
  const half = Math.floor(gridSize / 2);
  const urls: string[][] = [];
  for (let dy = -half; dy <= half; dy++) {
    const row: string[] = [];
    for (let dx = -half; dx <= half; dx++) {
      row.push(`${TILE_BASE}/${zoom}/${y + dy}/${x + dx}`);
    }
    urls.push(row);
  }
  return urls;
}
