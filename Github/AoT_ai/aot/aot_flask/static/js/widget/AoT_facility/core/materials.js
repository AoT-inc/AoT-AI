// core/materials.js — AoT Facility material palette (moved from aot-facility-3d.js)
// Exposes window.AoTMaterials. Requires THREE.
(function (global) {
  'use strict';

  const _COVER_OPTS = {
    vinyl_single:  { color: 0x9ecfef, opacity: 0.25 },
    vinyl_double:  { color: 0x9ecfef, opacity: 0.32 },
    po_film:       { color: 0xbcdff0, opacity: 0.28 },
    polycarbonate: { color: 0xdaeeff, opacity: 0.46 },
    glass:         { color: 0xc8eecc, opacity: 0.18 },
  };

  const MAT = {
    cover: function (type) {
      const o = _COVER_OPTS[type] || _COVER_OPTS.vinyl_double;
      return new THREE.MeshPhysicalMaterial({ color: o.color, transparent: true, opacity: o.opacity, side: THREE.DoubleSide, roughness: 0.05, metalness: 0 });
    },
    coverInner: function (type) {
      const o = _COVER_OPTS[type] || { color: 0xd0eaff, opacity: 0.18 };
      return new THREE.MeshPhysicalMaterial({ color: o.color, transparent: true, opacity: Math.min(o.opacity * 0.65, 0.22), side: THREE.DoubleSide, roughness: 0.05, metalness: 0 });
    },
    frame:           () => new THREE.MeshStandardMaterial({ color: 0x888888, roughness: 0.6, metalness: 0.4 }),
    floor:           () => new THREE.MeshStandardMaterial({ color: 0xb8b8b8, roughness: 0.85 }),
    sashOpen:        () => new THREE.MeshStandardMaterial({ color: 0xffb300, transparent: true, opacity: 0.75, side: THREE.DoubleSide }),
    sashClosed:      () => new THREE.MeshStandardMaterial({ color: 0x607d8b, transparent: true, opacity: 0.55, side: THREE.DoubleSide }),
    curtainThermal:  () => new THREE.MeshStandardMaterial({ color: 0xf5e6c8, transparent: true, opacity: 0.80, side: THREE.DoubleSide }),
    curtainShade:    () => new THREE.MeshStandardMaterial({ color: 0x4a4a4a, transparent: true, opacity: 0.70, side: THREE.DoubleSide }),
    fan:             () => new THREE.MeshStandardMaterial({ color: 0x546e7a }),
    fanOn:           () => new THREE.MeshStandardMaterial({ color: 0x29b6f6, emissive: 0x0288d1, emissiveIntensity: 0.6 }),
    heater:          () => new THREE.MeshStandardMaterial({ color: 0xef9a9a }),
    heaterOn:        () => new THREE.MeshStandardMaterial({ color: 0xf44336, emissive: 0xe53935, emissiveIntensity: 0.8 }),
    cooler:          () => new THREE.MeshStandardMaterial({ color: 0x80cbc4 }),
    coolerOn:        () => new THREE.MeshStandardMaterial({ color: 0x00bcd4, emissive: 0x0097a7, emissiveIntensity: 0.6 }),
    pump:            () => new THREE.MeshStandardMaterial({ color: 0x81c784 }),
    pumpOn:          () => new THREE.MeshStandardMaterial({ color: 0x4caf50, emissive: 0x388e3c, emissiveIntensity: 0.6 }),
    windArrow:       () => new THREE.MeshStandardMaterial({ color: 0x0288d1 }),
    compass:         () => new THREE.MeshStandardMaterial({ color: 0xe53935 }),
  };

  global.AoTMaterials = MAT;
})(window);
