/**
 * MapLibre Core ES Module Shim
 * Imports from IIFE pattern and re-exports for bundling
 */

// Re-export what the IIFE module sets on window
const AoTMapLibre = window.AoTMapLibre;

export { AoTMapLibre };
export default AoTMapLibre;
