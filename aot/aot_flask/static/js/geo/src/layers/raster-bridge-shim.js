/**
 * Raster Bridge ES Module Shim
 * Imports from IIFE pattern and re-exports for bundling
 */

const RasterBridge = window.AoTRasterBridge;
const MapBridge = window.AoTMapBridge;

export { RasterBridge, MapBridge };
export default { RasterBridge, MapBridge };
