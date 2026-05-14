// core/parametric.js — Parametric greenhouse geometry builders (moved from aot-facility-3d.js)
// Exposes window.AoTParametric. Requires THREE.
(function (global) {
  'use strict';

  function buildMultiSpanShape(span, eaveH, ridgeH, roofType, bayCount, spacing) {
    const s = new THREE.Shape();
    s.moveTo(0, 0);
    s.lineTo(0, eaveH);

    for (let b = 0; b < bayCount; b++) {
      const lx = b * (span + spacing);
      const rx = lx + span;

      if (roofType === 'gable') {
        s.lineTo(lx + span / 2, ridgeH);
        s.lineTo(rx, eaveH);
      } else if (roofType === 'flat' || roofType === 'box') {
        s.lineTo(lx, ridgeH);
        s.lineTo(rx, ridgeH);
        s.lineTo(rx, eaveH);
      } else {
        s.bezierCurveTo(lx, ridgeH, rx, ridgeH, rx, eaveH);
      }

      if (spacing > 0 && b < bayCount - 1) {
        s.lineTo(rx + spacing, eaveH);
      }
    }

    const totalWidth = bayCount * span + (bayCount - 1) * spacing;
    s.lineTo(totalWidth, 0);
    s.lineTo(0, 0);
    return s;
  }

  function buildSideVentSash(eaveH, length, openRatio, isRight, MAT) {
    const ventH = Math.min(eaveH * 0.40, 1.2);
    const geo   = new THREE.PlaneGeometry(length * 0.85, ventH);
    geo.translate(0, -ventH / 2, 0);
    const isOpen = openRatio > 0.05;
    const mesh = new THREE.Mesh(geo, isOpen ? MAT.sashOpen() : MAT.sashClosed());
    mesh.name = 'side_vent_' + (isRight ? 'right' : 'left');
    mesh.rotation.y = isRight ? -Math.PI / 2 : Math.PI / 2;
    if (isOpen) mesh.rotation.x = -openRatio * (Math.PI / 3);
    return mesh;
  }

  function buildRoofVentIndicator(span, ridgeH, length, openRatio, MAT) {
    const ventW = span * 0.22;
    const ventL = length * 0.75;
    const geo   = new THREE.PlaneGeometry(ventW, ventL);
    const isOpen = openRatio > 0.05;
    const mesh = new THREE.Mesh(geo, isOpen ? MAT.sashOpen() : MAT.sashClosed());
    mesh.name = 'roof_vent';
    mesh.rotation.x = -(Math.PI / 2) + (isOpen ? openRatio * (Math.PI / 5) : 0);
    return mesh;
  }

  function buildCurtain(totalWidth, eaveH, length, type, deployRatio, MAT) {
    const w   = totalWidth * Math.max(deployRatio, 0.02);
    const geo = new THREE.PlaneGeometry(w, length);
    geo.rotateX(-Math.PI / 2);
    const mat  = type === 'thermal' ? MAT.curtainThermal() : MAT.curtainShade();
    const mesh = new THREE.Mesh(geo, mat);
    mesh.name  = 'curtain_' + type;
    mesh.position.set(w / 2, eaveH + 0.08, length / 2);
    return mesh;
  }

  function buildDeviceIcon(type, isOn, position, MAT) {
    const g = new THREE.Group();
    g.name = 'device_' + type;
    g.position.copy(position);

    let geo, mat;
    if (type === 'fan' || type === 'circulation_fan' || type === 'exhaust_fan') {
      geo = new THREE.TorusGeometry(0.18, 0.04, 8, 16);
      mat = isOn ? MAT.fanOn() : MAT.fan();
    } else if (type === 'heater') {
      geo = new THREE.BoxGeometry(0.4, 0.12, 0.12);
      mat = isOn ? MAT.heaterOn() : MAT.heater();
    } else if (type === 'cooler' || type === 'heat_pump') {
      geo = new THREE.BoxGeometry(0.4, 0.12, 0.12);
      mat = isOn ? MAT.coolerOn() : MAT.cooler();
    } else if (type === 'irrigation_valve') {
      geo = new THREE.CylinderGeometry(0.06, 0.06, 0.25, 8);
      mat = isOn ? MAT.pumpOn() : MAT.pump();
    } else {
      geo = new THREE.SphereGeometry(0.1, 8, 8);
      mat = new THREE.MeshStandardMaterial({ color: isOn ? 0x4caf50 : 0x9e9e9e });
    }

    const mesh = new THREE.Mesh(geo, mat);
    g.add(mesh);

    if (isOn) {
      const ringGeo = new THREE.TorusGeometry(0.25, 0.015, 8, 16);
      const ringMat = new THREE.MeshStandardMaterial({ color: 0xffffff, transparent: true, opacity: 0.5 });
      g.add(new THREE.Mesh(ringGeo, ringMat));
    }
    return g;
  }

  function buildWindArrow(windDeg, length, MAT) {
    const group = new THREE.Group();
    group.name = 'wind_arrow';
    const shaftGeo = new THREE.CylinderGeometry(0.04, 0.04, 1.2, 8);
    group.add(new THREE.Mesh(shaftGeo, MAT.windArrow()));
    const headGeo = new THREE.ConeGeometry(0.12, 0.35, 8);
    const head = new THREE.Mesh(headGeo, MAT.windArrow());
    head.position.y = 0.77;
    group.add(head);
    group.position.set(0, 3.0, length / 2);
    group.rotation.y = THREE.MathUtils.degToRad(windDeg + 180);
    return group;
  }

  function buildCompass(orientationDeg, length, MAT) {
    const group = new THREE.Group();
    group.name = 'compass';
    const geo = new THREE.ConeGeometry(0.08, 0.45, 8);
    const needle = new THREE.Mesh(geo, MAT.compass());
    group.add(needle);
    group.position.set(0, 0.5, length + 1.2);
    group.rotation.y = THREE.MathUtils.degToRad(-orientationDeg);
    return group;
  }

  function buildPipe(pts, radius, color, opacity, MAT) {
    const curve = new THREE.CatmullRomCurve3(pts.map(([x, y, z]) => new THREE.Vector3(x, y, z)));
    const geo   = new THREE.TubeGeometry(curve, Math.max(pts.length * 4, 8), radius, 6, false);
    const mat   = new THREE.MeshStandardMaterial({
      color, roughness: 0.55, metalness: 0.35,
      transparent: opacity < 1, opacity: opacity != null ? opacity : 1,
    });
    const m = new THREE.Mesh(geo, mat);
    m.name = 'pipe';
    return m;
  }

  function buildIrrigationPipes(totalWidth, length, span, bayCount, effectiveSpacing, isOn, MAT) {
    const group = new THREE.Group();
    group.name  = 'irrigation_pipes';
    const color = isOn ? 0x29b6f6 : 0x607d8b;
    const pH    = 0.18;
    const cx    = totalWidth / 2;

    const header = buildPipe([[cx, pH, 0.5], [cx, pH, length - 0.5]], 0.038, color, 1.0);
    header.name  = 'pipe_header';
    group.add(header);

    for (let b = 0; b < bayCount; b++) {
      const bx  = b * (span + effectiveSpacing) + span / 2;
      const lx0 = bx - span * 0.44;
      const lx1 = bx + span * 0.44;
      [0.15, 0.35, 0.50, 0.65, 0.85].forEach(function (zf) {
        const lat = buildPipe([[lx0, pH, length * zf], [cx, pH, length * zf], [lx1, pH, length * zf]], 0.020, color, 0.82);
        lat.name  = 'pipe_lateral';
        group.add(lat);
      });
    }
    return group;
  }

  function buildHeatingPipes(totalWidth, length, isOn) {
    const group = new THREE.Group();
    group.name  = 'heating_pipes';
    const color = isOn ? 0xef5350 : 0x795548;
    const pH    = 0.22;
    const inset = 0.35;

    [inset, totalWidth - inset].forEach(function (x) {
      const curve = new THREE.CatmullRomCurve3([
        new THREE.Vector3(x, pH, 0.4), new THREE.Vector3(x, pH, length - 0.4),
      ]);
      const geo = new THREE.TubeGeometry(curve, 8, 0.030, 6, false);
      const mat = new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.35 });
      const rail = new THREE.Mesh(geo, mat);
      rail.name = 'pipe_heat_rail';
      group.add(rail);
    });
    return group;
  }

  function buildFacilityMeshGroup(facility, MAT) {
    const g3d      = facility.geometry_3d || {};
    const envelope = facility.envelope    || {};

    const span      = parseFloat(g3d.span_width_m)   || 7;
    const eaveH     = parseFloat(g3d.eave_height_m)  || 2;
    const ridgeH    = parseFloat(g3d.ridge_height_m) || 4;
    const length    = parseFloat(g3d.length_m)       || 30;
    const roofType  = String(g3d.roof_type || 'arch').toLowerCase();
    const orientDeg = parseFloat(g3d.orientation_deg) || 0;
    const rawBayCount = Math.max(parseInt(facility.bay_count || 1, 10), 1);
    const isConnected = facility.structure === 'connected';
    const unitCount = isConnected ? 1 : rawBayCount;
    const meshBayCount = isConnected ? rawBayCount : 1;
    const isDouble  = (envelope.layer_count || 1) === 2;
    const effectiveSpacing = isConnected ? 0 : (parseFloat(g3d.spacing_m) || 1);
    const unitWidth = meshBayCount * span + (meshBayCount - 1) * effectiveSpacing;
    const totalWidth = unitCount * unitWidth + (unitCount - 1) * effectiveSpacing;

    const outerEnvSpec  = envelope.outer || {};
    const innerEnvSpec  = envelope.inner || {};
    const outerCoverMat = outerEnvSpec.cover_material || 'vinyl_double';
    const innerCoverMat = innerEnvSpec.cover_material || 'non_woven_fabric';

    const group = new THREE.Group();
    group.name = 'facility_mesh_' + (facility.unique_id || 'unknown');

    const extrudeSettings = { steps: 1, depth: length, bevelEnabled: false };
    const outerShape = buildMultiSpanShape(span, eaveH, ridgeH, roofType, meshBayCount, effectiveSpacing);
    const outerGeo   = new THREE.ExtrudeGeometry(outerShape, extrudeSettings);

    let innerGeo;
    if (isDouble) {
      const inset = 0.15;
      const innerShape = buildMultiSpanShape(
        span - inset * 2, eaveH - inset * 0.5, ridgeH - inset, roofType, meshBayCount, effectiveSpacing
      );
      innerGeo = new THREE.ExtrudeGeometry(innerShape,
        { steps: 1, depth: length - inset * 2, bevelEnabled: false });
    }

    for (let u = 0; u < unitCount; u++) {
      const xOffset = u * (unitWidth + effectiveSpacing);
      const outerMesh = new THREE.Mesh(outerGeo, MAT.cover(outerCoverMat));
      outerMesh.name = 'outer_cover_' + u;
      outerMesh.position.x = xOffset;
      group.add(outerMesh);
      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(outerGeo),
        new THREE.LineBasicMaterial({ color: 0x455a64, linewidth: 1 })
      );
      edges.position.x = xOffset;
      group.add(edges);
      if (isDouble && innerGeo) {
        const inset = 0.15;
        const innerMesh = new THREE.Mesh(innerGeo, MAT.coverInner(innerCoverMat));
        innerMesh.position.set(xOffset + inset, 0, inset);
        innerMesh.name = 'inner_cover_' + u;
        group.add(innerMesh);
      }
    }

    if (isConnected) {
      const gutterMat = new THREE.MeshStandardMaterial({ color: 0x607d8b, roughness: 0.5, metalness: 0.5 });
      for (let b = 1; b < meshBayCount; b++) {
        const col = new THREE.Mesh(new THREE.BoxGeometry(0.05, eaveH, 0.05), gutterMat);
        col.position.set(b * span, eaveH / 2, length * 0.25);
        group.add(col);
        const col2 = col.clone();
        col2.position.set(b * span, eaveH / 2, length * 0.75);
        group.add(col2);
      }
    }

    group.userData.cx = totalWidth / 2;
    group.userData.cz = length / 2;
    group.userData.orientDeg = orientDeg;
    group.userData.totalWidth = totalWidth;
    group.userData.length = length;
    return group;
  }

  global.AoTParametric = {
    buildMultiSpanShape,
    buildSideVentSash,
    buildRoofVentIndicator,
    buildCurtain,
    buildDeviceIcon,
    buildWindArrow,
    buildCompass,
    buildPipe,
    buildIrrigationPipes,
    buildHeatingPipes,
    buildFacilityMeshGroup,
  };
})(window);
