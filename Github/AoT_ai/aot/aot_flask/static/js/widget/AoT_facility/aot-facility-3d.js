// aot-facility-3d.js — Three.js scene builder for AoT Facility Widget
// Procedurally generates a parametric greenhouse mesh from GeoFacility spec.
// Depends: THREE (r160+), THREE.MapControls (OrbitControls.js),
//          three-mesh-bvh (MeshBVHLib), GSAP (optional), THREE.GLTFLoader (optional)
(function (global) {
  'use strict';

  // ── Material palette ─────────────────────────────────────────────────────────
  // Cover visual properties per cover_material type
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
    frame:        () => new THREE.MeshStandardMaterial({ color: 0x888888, roughness: 0.6, metalness: 0.4 }),
    floor:        () => new THREE.MeshStandardMaterial({ color: 0xb8b8b8, roughness: 0.85 }),
    sashOpen:     () => new THREE.MeshStandardMaterial({ color: 0xffb300, transparent: true, opacity: 0.75, side: THREE.DoubleSide }),
    sashClosed:   () => new THREE.MeshStandardMaterial({ color: 0x607d8b, transparent: true, opacity: 0.55, side: THREE.DoubleSide }),
    curtainThermal: () => new THREE.MeshStandardMaterial({ color: 0xf5e6c8, transparent: true, opacity: 0.80, side: THREE.DoubleSide }),
    curtainShade:   () => new THREE.MeshStandardMaterial({ color: 0x4a4a4a, transparent: true, opacity: 0.70, side: THREE.DoubleSide }),
    fan:            () => new THREE.MeshStandardMaterial({ color: 0x546e7a }),
    fanOn:          () => new THREE.MeshStandardMaterial({ color: 0x29b6f6, emissive: 0x0288d1, emissiveIntensity: 0.6 }),
    heater:         () => new THREE.MeshStandardMaterial({ color: 0xef9a9a }),
    heaterOn:       () => new THREE.MeshStandardMaterial({ color: 0xf44336, emissive: 0xe53935, emissiveIntensity: 0.8 }),
    cooler:         () => new THREE.MeshStandardMaterial({ color: 0x80cbc4 }),
    coolerOn:       () => new THREE.MeshStandardMaterial({ color: 0x00bcd4, emissive: 0x0097a7, emissiveIntensity: 0.6 }),
    pump:           () => new THREE.MeshStandardMaterial({ color: 0x81c784 }),
    pumpOn:         () => new THREE.MeshStandardMaterial({ color: 0x4caf50, emissive: 0x388e3c, emissiveIntensity: 0.6 }),
    windArrow:      () => new THREE.MeshStandardMaterial({ color: 0x0288d1 }),
    compass:        () => new THREE.MeshStandardMaterial({ color: 0xe53935 }),
  };

  // ── Multi-span cross-section shape (handles 1..N connected bays) ─────────────
  // Shape origin: bottom-left corner (0, 0). Spans x=0..totalWidth.
  function _buildMultiSpanShape(span, eaveH, ridgeH, roofType, bayCount, spacing) {
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
        // arch — cubic bezier: peaks at ridgeH, connects eave-to-eave per bay
        s.bezierCurveTo(lx, ridgeH, rx, ridgeH, rx, eaveH);
      }

      // Gap between bays (only for spaced/separated structures)
      if (spacing > 0 && b < bayCount - 1) {
        s.lineTo(rx + spacing, eaveH);
      }
    }

    const totalWidth = bayCount * span + (bayCount - 1) * spacing;
    s.lineTo(totalWidth, 0);
    s.lineTo(0, 0);
    return s;
  }

  // ── Side vent sash (측창): runs along length, hinged at top, opens outward ───
  function buildSideVentSash(eaveH, length, openRatio, isRight) {
    const ventH = Math.min(eaveH * 0.40, 1.2);
    const geo   = new THREE.PlaneGeometry(length * 0.85, ventH);
    // Pivot at top edge (hinge) → translate so local y=0 is at the top
    geo.translate(0, -ventH / 2, 0);
    const isOpen = openRatio > 0.05;
    const mesh = new THREE.Mesh(geo, isOpen ? MAT.sashOpen() : MAT.sashClosed());
    mesh.name = 'side_vent_' + (isRight ? 'right' : 'left');
    // Align panel with the side wall (YZ plane): normal faces outward (±X)
    mesh.rotation.y = isRight ? -Math.PI / 2 : Math.PI / 2;
    // Open: bottom edge swings outward (local -Y → local +Z)
    if (isOpen) mesh.rotation.x = -openRatio * (Math.PI / 3);
    return mesh;
    // Caller: mesh.position.set(wallX, eaveH * 0.45, length / 2)
  }

  // ── Roof vent (천창): horizontal strip at ridge, tilts up when open ──────────
  function buildRoofVentIndicator(span, ridgeH, length, openRatio) {
    const ventW = span * 0.22;
    const ventL = length * 0.75;
    const geo   = new THREE.PlaneGeometry(ventW, ventL);
    const isOpen = openRatio > 0.05;
    const mesh = new THREE.Mesh(geo, isOpen ? MAT.sashOpen() : MAT.sashClosed());
    mesh.name = 'roof_vent';
    // Horizontal (lies flat on arch top), opens by tilting one edge upward
    mesh.rotation.x = -(Math.PI / 2) + (isOpen ? openRatio * (Math.PI / 5) : 0);
    return mesh;
    // Caller: mesh.position.set(bayCenter, ridgeH + 0.02, length / 2)
  }

  // ── Curtain (커튼): horizontal plane across full width at eave height ─────────
  function buildCurtain(totalWidth, eaveH, length, type, deployRatio) {
    // Deploy from x=0 toward x=totalWidth
    const w   = totalWidth * Math.max(deployRatio, 0.02);
    const geo = new THREE.PlaneGeometry(w, length);
    geo.rotateX(-Math.PI / 2);                  // horizontal plane
    const mat  = type === 'thermal' ? MAT.curtainThermal() : MAT.curtainShade();
    const mesh = new THREE.Mesh(geo, mat);
    mesh.name  = 'curtain_' + type;
    mesh.position.set(w / 2, eaveH + 0.08, length / 2);
    return mesh;
  }

  // ── Device icons (fan, heater, cooler, pump) ─────────────────────────────────
  function buildDeviceIcon(type, isOn, position) {
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
      // Pulse ring
      const ringGeo = new THREE.TorusGeometry(0.25, 0.015, 8, 16);
      const ringMat = new THREE.MeshStandardMaterial({ color: 0xffffff, transparent: true, opacity: 0.5 });
      g.add(new THREE.Mesh(ringGeo, ringMat));
    }
    return g;
  }

  // ── Wind arrow ──────────────────────────────────────────────────────────────
  function buildWindArrow(windDeg, length) {
    const group = new THREE.Group();
    group.name = 'wind_arrow';

    const shaftGeo = new THREE.CylinderGeometry(0.04, 0.04, 1.2, 8);
    group.add(new THREE.Mesh(shaftGeo, MAT.windArrow()));

    const headGeo = new THREE.ConeGeometry(0.12, 0.35, 8);
    const head = new THREE.Mesh(headGeo, MAT.windArrow());
    head.position.y = 0.77;
    group.add(head);

    group.position.set(0, 3.0, length / 2);
    // Convert wind direction (meteorological: from) to rotation
    group.rotation.y = THREE.MathUtils.degToRad(windDeg + 180);
    return group;
  }

  // ── Compass needle ────────────────────────────────────────────────────────────
  function buildCompass(orientationDeg, length) {
    const group = new THREE.Group();
    group.name = 'compass';
    const geo = new THREE.ConeGeometry(0.08, 0.45, 8);
    const needle = new THREE.Mesh(geo, MAT.compass());
    group.add(needle);
    // Point toward geographic north
    group.position.set(0, 0.5, length + 1.2);
    group.rotation.y = THREE.MathUtils.degToRad(-orientationDeg);
    return group;
  }

  // ── Pipe helpers (배관·덕트): TubeGeometry + CatmullRomCurve3 ───────────────
  function buildPipe(pts, radius, color, opacity) {
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

  function buildIrrigationPipes(totalWidth, length, span, bayCount, effectiveSpacing, isOn) {
    const group = new THREE.Group();
    group.name  = 'irrigation_pipes';
    const color = isOn ? 0x29b6f6 : 0x607d8b;
    const pH    = 0.18;
    const cx    = totalWidth / 2;

    // Main header pipe runs along center
    const header = buildPipe([[cx, pH, 0.5], [cx, pH, length - 0.5]], 0.038, color, 1.0);
    header.name  = 'pipe_header';
    group.add(header);

    // Drip laterals per bay
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
      const rail = buildPipe([[x, pH, 0.4], [x, pH, length - 0.4]], 0.030, color, 1.0);
      rail.name  = 'pipe_heat_rail';
      group.add(rail);
    });
    return group;
  }

  // ── GLTFLoader: try to load device .glb, fall back to primitive icon ──────────
  function _tryLoadGLB(type, position, parentGroup) {
    if (!window.THREE || !THREE.GLTFLoader) return;
    const loader = new THREE.GLTFLoader();
    loader.load(
      '/static/models/aot_devices/' + type + '.glb',
      function (gltf) {
        const model = gltf.scene;
        model.scale.setScalar(0.42);
        model.position.copy(position);
        model.name = 'glb_' + type;
        if (parentGroup) parentGroup.add(model);
      },
      undefined,
      function () { /* 404 / load error — keep primitive fallback */ }
    );
  }

  // ── Main builder ─────────────────────────────────────────────────────────────
  function buildScene(canvas, facility, runtime) {
    const g3d = facility.geometry_3d || {};
    const envelope = facility.envelope || {};
    const actuators = facility.actuators || {};
    const actStates = (runtime && runtime.actuator_states) || {};
    const outdoor = (runtime && runtime.outdoor) || {};

    const span      = parseFloat(g3d.span_width_m)  || 7;
    const eaveH     = parseFloat(g3d.eave_height_m) || 2;
    const ridgeH    = parseFloat(g3d.ridge_height_m)|| 4;
    const length    = parseFloat(g3d.length_m)      || 30;
    const spacing   = parseFloat(g3d.spacing_m)     || 1;
    const roofType  = String(g3d.roof_type || 'arch').toLowerCase();
    const orientDeg = parseFloat(g3d.orientation_deg) || 0;
    const bayCount  = facility.structure === 'connected'
      ? Math.max(parseInt(facility.bay_count || 1, 10), 1) : 1;
    const isDouble  = (envelope.layer_count || 1) === 2;

    // ── Renderer ──────────────────────────────────────────────────────────────
    // Use parent container dimensions; canvas CSS is 100%/100% so clientWidth
    // may read 0 before first layout tick — fall back to parent or defaults.
    const parent = canvas.parentElement;
    const W = (parent && parent.clientWidth)  || canvas.clientWidth  || 400;
    const H = (parent && parent.clientHeight) || canvas.clientHeight || 340;

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(W, H, false);
    renderer.shadowMap.enabled = true;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf0f4f8);
    scene.fog = new THREE.Fog(0xf0f4f8, 60, 120);

    // ── Camera ───────────────────────────────────────────────────────────────
    // Connected bays share walls → no spacing between them
    const effectiveSpacing = facility.structure === 'connected' ? 0 : (parseFloat(g3d.spacing_m) || 1);
    const totalWidth = bayCount * span + (bayCount - 1) * effectiveSpacing;
    const camera = new THREE.PerspectiveCamera(45, W / H, 0.1, 1500);
    const cx = totalWidth / 2, cz = length / 2, cy = ridgeH * 0.5;
    // Interior view: camera inside the greenhouse, looking toward front-center
    camera.position.set(totalWidth * 0.7, ridgeH * 2.2, length * 0.9);
    camera.lookAt(cx, cy, cz);

    // ── Controls (Three.js MapControls: LMB=pan, RMB=orbit, scroll=zoom) ────────
    const _origTarget = new THREE.Vector3(cx, cy, cz);
    const controls = new THREE.MapControls(camera, renderer.domElement);
    controls.target.copy(_origTarget);
    controls.enableDamping  = true;
    controls.dampingFactor  = 0.12;
    controls.panSpeed       = 0.5;
    controls.rotateSpeed    = 0.8;
    controls.minDistance    = 2;
    controls.maxDistance    = 800;
    controls.maxPolarAngle  = Math.PI * 0.82;
    controls.update();
    renderer.domElement.style.cursor = 'crosshair';

    // BVH-accelerated raycasting (three-mesh-bvh)
    if (window.MeshBVHLib) {
      THREE.BufferGeometry.prototype.computeBoundsTree  = MeshBVHLib.computeBoundsTree;
      THREE.BufferGeometry.prototype.disposeBoundsTree  = MeshBVHLib.disposeBoundsTree;
      THREE.Mesh.prototype.raycast                      = MeshBVHLib.acceleratedRaycast;
    }

    // Viewport-button helper: smooth GSAP fly-to (falls back to instant)
    function teleport(newCamPos) {
      if (window.gsap) {
        gsap.killTweensOf(camera.position);
        gsap.killTweensOf(controls.target);
        gsap.to(camera.position, {
          x: newCamPos.x, y: newCamPos.y, z: newCamPos.z,
          duration: 0.65, ease: 'power2.inOut',
          onUpdate: function () { controls.update(); },
        });
        gsap.to(controls.target, {
          x: _origTarget.x, y: _origTarget.y, z: _origTarget.z,
          duration: 0.65, ease: 'power2.inOut',
          onUpdate: function () { controls.update(); },
        });
      } else {
        controls.target.copy(_origTarget);
        camera.position.copy(newCamPos);
        controls.update();
      }
    }
    // Projection-toggle helper: scale camera distance relative to target
    function scaleDist(factor) {
      const dir = camera.position.clone().sub(controls.target);
      camera.position.copy(controls.target.clone().addScaledVector(dir.normalize(), dir.length() * factor));
      controls.update();
    }
    // Click-vs-drag discrimination: track whether mouse moved during mousedown
    let _dragged = false;
    renderer.domElement.addEventListener('mousedown', () => { _dragged = false; });
    renderer.domElement.addEventListener('mousemove', (e) => { if (e.buttons) _dragged = true; });
    function isPanDragging() { return _dragged; }

    // Expose on controls object so existing callers (viewport buttons, projection toggle) work
    controls.teleport     = teleport;
    controls.scaleDist    = scaleDist;
    controls.isPanDragging = isPanDragging;

    // ── Lights ────────────────────────────────────────────────────────────────
    const ambient = new THREE.AmbientLight(0xffffff, 0.55);
    scene.add(ambient);

    const solarIntensity = outdoor.solar_wm2 != null
      ? 0.4 + Math.min(outdoor.solar_wm2 / 1000, 1) * 0.8
      : 0.85;
    const sun = new THREE.DirectionalLight(0xfff4d6, solarIntensity);
    sun.position.set(30, 60, 40);
    sun.castShadow = true;
    scene.add(sun);

    // ── Greenhouse group ──────────────────────────────────────────────────────
    // orientation_deg is shown via compass needle only; the 3D preview is always
    // displayed in a fixed orientation for consistent editing UX.
    const outerEnvSpec  = envelope.outer || {};
    const innerEnvSpec  = envelope.inner || {};
    const outerCoverMat = outerEnvSpec.cover_material || 'vinyl_double';
    const innerCoverMat = innerEnvSpec.cover_material || 'non_woven_fabric';

    const ghGroup = new THREE.Group();
    ghGroup.name = 'greenhouse';
    scene.add(ghGroup);

    // Track devices for click-picking
    const clickTargets = [];

    // ── Greenhouse cover: single multi-span extrusion ─────────────────────────
    const extrudeSettings = { steps: 1, depth: length, bevelEnabled: false };

    const outerShape = _buildMultiSpanShape(span, eaveH, ridgeH, roofType, bayCount, effectiveSpacing);
    const outerGeo   = new THREE.ExtrudeGeometry(outerShape, extrudeSettings);
    const outerMesh  = new THREE.Mesh(outerGeo, MAT.cover(outerCoverMat));
    outerMesh.name = 'outer_cover';
    ghGroup.add(outerMesh);
    ghGroup.add(new THREE.LineSegments(new THREE.EdgesGeometry(outerGeo),
      new THREE.LineBasicMaterial({ color: 0x455a64 })));

    // Inner cover for double-layer
    if (isDouble) {
      const inset = 0.15;
      const innerShape = _buildMultiSpanShape(
        span - inset * 2, eaveH - inset * 0.5, ridgeH - inset, roofType, bayCount, effectiveSpacing
      );
      const innerGeo  = new THREE.ExtrudeGeometry(innerShape, { ...extrudeSettings, depth: length - inset * 2 });
      const innerMesh = new THREE.Mesh(innerGeo, MAT.coverInner(innerCoverMat));
      innerMesh.name = 'inner_cover';
      innerMesh.position.set(inset, 0, inset);
      ghGroup.add(innerMesh);
    }

    // Gutter posts at each bay junction (connected only) — thin steel column
    if (facility.structure === 'connected') {
      const gutterMat = new THREE.MeshStandardMaterial({ color: 0x607d8b, roughness: 0.5, metalness: 0.5 });
      for (let b = 1; b < bayCount; b++) {
        const col = new THREE.Mesh(new THREE.BoxGeometry(0.05, eaveH, 0.05), gutterMat);
        col.position.set(b * span, eaveH / 2, length * 0.25);
        ghGroup.add(col);
        const col2 = new THREE.Mesh(new THREE.BoxGeometry(0.05, eaveH, 0.05), gutterMat);
        col2.position.set(b * span, eaveH / 2, length * 0.75);
        ghGroup.add(col2);
      }
    }

    // Single floor slab — raised above y=0 to avoid z-fighting with ground/grid
    const floorGeo  = new THREE.BoxGeometry(totalWidth, 0.06, length);
    const floorMesh = new THREE.Mesh(floorGeo, MAT.floor());
    floorMesh.position.set(totalWidth / 2, 0.03, length / 2);
    ghGroup.add(floorMesh);

    // ── Vents: outer layer ────────────────────────────────────────────────────
    if (outerEnvSpec.side_vent && outerEnvSpec.side_vent.enabled) {
      const stateS = actStates['outer_side_vent_motor'];
      const openR  = stateS ? (stateS.on ? 0.65 : 0) : 0.0;
      const sashL  = buildSideVentSash(eaveH, length, openR, false);
      sashL.position.set(0, eaveH * 0.45, length / 2);
      ghGroup.add(sashL);
      const sashR = buildSideVentSash(eaveH, length, openR, true);
      sashR.position.set(totalWidth, eaveH * 0.45, length / 2);
      ghGroup.add(sashR);
      clickTargets.push({ mesh: sashL, slot: 'outer_side_vent_motor' });
      clickTargets.push({ mesh: sashR, slot: 'outer_side_vent_motor' });
    }
    if (outerEnvSpec.roof_vent && outerEnvSpec.roof_vent.enabled) {
      const stateR = actStates['outer_roof_vent_motor'];
      const openR  = stateR ? (stateR.on ? 0.6 : 0) : 0.0;
      for (let b = 0; b < bayCount; b++) {
        const bx = b * (span + effectiveSpacing) + span / 2;
        const ventMesh = buildRoofVentIndicator(span, ridgeH, length, openR);
        ventMesh.position.set(bx, ridgeH + 0.02, length / 2);
        ghGroup.add(ventMesh);
        clickTargets.push({ mesh: ventMesh, slot: 'outer_roof_vent_motor' });
      }
    }

    // ── Vents: inner layer (double-layer only, inset 0.18 m inside outer wall) ─
    if (isDouble) {
      const inset = 0.18;
      if (innerEnvSpec.side_vent && innerEnvSpec.side_vent.enabled) {
        const stateS = actStates['inner_side_vent_motor'];
        const openR  = stateS ? (stateS.on ? 0.65 : 0) : 0.0;
        const iSashL = buildSideVentSash(eaveH, length * 0.82, openR, false);
        iSashL.position.set(inset, eaveH * 0.45, length / 2);
        ghGroup.add(iSashL);
        const iSashR = buildSideVentSash(eaveH, length * 0.82, openR, true);
        iSashR.position.set(totalWidth - inset, eaveH * 0.45, length / 2);
        ghGroup.add(iSashR);
        clickTargets.push({ mesh: iSashL, slot: 'inner_side_vent_motor' });
        clickTargets.push({ mesh: iSashR, slot: 'inner_side_vent_motor' });
      }
      if (innerEnvSpec.roof_vent && innerEnvSpec.roof_vent.enabled) {
        const stateR = actStates['inner_roof_vent_motor'];
        const openR  = stateR ? (stateR.on ? 0.6 : 0) : 0.0;
        for (let b = 0; b < bayCount; b++) {
          const bx = b * (span + effectiveSpacing) + span / 2;
          const iVent = buildRoofVentIndicator(span * 0.8, ridgeH - inset, length, openR);
          iVent.position.set(bx, ridgeH - inset + 0.02, length / 2);
          ghGroup.add(iVent);
          clickTargets.push({ mesh: iVent, slot: 'inner_roof_vent_motor' });
        }
      }
    }

    // ── Curtains: horizontal planes at eave height ────────────────────────────
    const curtain = envelope.curtain || {};
    if (curtain.thermal) {
      const st     = actStates['thermal_curtain'];
      const deploy = st ? (st.on ? 1.0 : 0.0) : 0.0;
      const cm     = buildCurtain(totalWidth, eaveH, length, 'thermal', deploy);
      ghGroup.add(cm);
      clickTargets.push({ mesh: cm, slot: 'thermal_curtain' });
    }
    if (curtain.shade) {
      const st     = actStates['shade_curtain'];
      const deploy = st ? (st.on ? 0.9 : 0.0) : 0.0;
      const cm     = buildCurtain(totalWidth, eaveH, length, 'shade', deploy);
      cm.position.y += 0.12;   // shade slightly above thermal to avoid z-fighting
      ghGroup.add(cm);
      clickTargets.push({ mesh: cm, slot: 'shade_curtain' });
    }

    // ── Equipment icons (placed in center bay) ────────────────────────────────
    const centerX  = Math.floor(bayCount / 2) * (span + effectiveSpacing) + span / 2;
    const equipSlots = [
      { key: 'circulation_fan',   pos: new THREE.Vector3(centerX,               eaveH * 0.65, length * 0.25) },
      { key: 'exhaust_fan',       pos: new THREE.Vector3(centerX,               eaveH * 0.65, length * 0.75) },
      { key: 'heater',            pos: new THREE.Vector3(centerX - span * 0.3,  0.35,         length * 0.2)  },
      { key: 'cooler',            pos: new THREE.Vector3(centerX - span * 0.3,  0.35,         length * 0.8)  },
      { key: 'heat_pump',         pos: new THREE.Vector3(centerX + span * 0.3,  0.35,         length * 0.5)  },
      { key: 'irrigation_valve',  pos: new THREE.Vector3(centerX + span * 0.2,  0.35,         length * 0.4)  },
    ];
    equipSlots.forEach(({ key, pos }) => {
      const state = actStates[key];
      if (!actuators[key] && !state) return;
      const icon = buildDeviceIcon(key, state ? state.on : false, pos);
      ghGroup.add(icon);
      clickTargets.push({ mesh: icon.children[0], slot: key, group: icon });
      // Try to replace primitive with GLTF model if available
      _tryLoadGLB(key, pos, ghGroup);
    });

    // ── Pipe networks ─────────────────────────────────────────────────────────
    if (actuators['irrigation_valve'] || actStates['irrigation_valve']) {
      const iOn = !!(actStates['irrigation_valve'] && actStates['irrigation_valve'].on);
      ghGroup.add(buildIrrigationPipes(totalWidth, length, span, bayCount, effectiveSpacing, iOn));
    }
    if (actuators['heater'] || actStates['heater']) {
      const hOn = !!(actStates['heater'] && actStates['heater'].on);
      ghGroup.add(buildHeatingPipes(totalWidth, length, hOn));
    }

    // ── Wind arrow + compass ──────────────────────────────────────────────────
    const windDeg = outdoor.wind_deg != null ? outdoor.wind_deg : 0;
    const windMs  = outdoor.wind_ms;
    if (windMs != null || outdoor.wind_deg != null) {
      const arrow = buildWindArrow(windDeg, length);
      scene.add(arrow);
    }
    scene.add(buildCompass(orientDeg, length));

    // ── Ground plane ──────────────────────────────────────────────────────────
    // y=-0.08: clearly below floor slab (bottom at y=0) → no z-fighting
    const groundGeo = new THREE.PlaneGeometry(200, 200);
    const groundMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.90 });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.08;
    scene.add(ground);

    // ── Grid helper ───────────────────────────────────────────────────────────
    // y=-0.04: between ground and floor bottom (y=0), visible outside facility
    const grid = new THREE.GridHelper(100, 50, 0xbbbbbb, 0xdddddd);
    grid.position.y = -0.04;
    scene.add(grid);

    // ── View cube overlay (3×3 fit-to-model presets + projection toggle) ───────
    // Compute per-direction camera distances so the model fills the frame
    const _halfFovV = camera.fov / 2 * Math.PI / 180;
    const _asp      = camera.aspect || (W / H);
    const _halfFovH = Math.atan(Math.tan(_halfFovV) * _asp);
    const _ctr      = new THREE.Vector3(cx, ridgeH / 2, cz);
    const _hw = totalWidth / 2, _hh = ridgeH / 2, _hl = length / 2;
    const _PAD = 1.18;

    function _fitD(eH, eV) {
      return Math.max(eH / Math.tan(_halfFovH), eV / Math.tan(_halfFovV)) * _PAD;
    }
    const _boundR = Math.sqrt(_hw*_hw + _hh*_hh + _hl*_hl);
    const _dFront  = _fitD(_hw, _hh);
    const _dSide   = _fitD(_hl, _hh);
    const _dTop    = _fitD(_hw, _hl);
    const _dCorner = _boundR / Math.sin(_halfFovV) * _PAD;

    const _vcPresets = {
      'back-left':   _ctr.clone().addScaledVector(new THREE.Vector3(-1, 1,  1).normalize(), _dCorner),
      'top':         _ctr.clone().addScaledVector(new THREE.Vector3( 0, 1,  0),             _dTop),
      'back-right':  _ctr.clone().addScaledVector(new THREE.Vector3( 1, 1,  1).normalize(), _dCorner),
      'left':        _ctr.clone().addScaledVector(new THREE.Vector3(-1, 0,  0),             _dSide),
      'iso':         _ctr.clone().addScaledVector(new THREE.Vector3( 0.55, 0.85, -0.65).normalize(), _dCorner),
      'right':       _ctr.clone().addScaledVector(new THREE.Vector3( 1, 0,  0),             _dSide),
      'front-left':  _ctr.clone().addScaledVector(new THREE.Vector3(-1, 1, -1).normalize(), _dCorner),
      'front':       _ctr.clone().addScaledVector(new THREE.Vector3( 0, 0, -1),             _dFront),
      'front-right': _ctr.clone().addScaledVector(new THREE.Vector3( 1, 1, -1).normalize(), _dCorner),
    };
    const _vcLabels = {
      'back-left':'후좌','top':'위','back-right':'후우',
      'left':'좌','iso':'●','right':'우',
      'front-left':'전좌','front':'앞','front-right':'전우',
    };
    const _vcTitles = {
      'back-left':'후면 좌 등각','top':'위 (평면)','back-right':'후면 우 등각',
      'left':'좌 측면','iso':'기본 등각','right':'우 측면',
      'front-left':'정면 좌 등각','front':'정면','front-right':'정면 우 등각',
    };

    const vcEl = document.createElement('div');
    vcEl.style.cssText = [
      'position:absolute','top:32px','right:8px','z-index:15',
      'display:grid','grid-template-columns:repeat(3,28px)',
      'grid-auto-rows:28px','gap:2px',
    ].join(';');

    ['back-left','top','back-right','left','iso','right','front-left','front','front-right']
      .forEach((key) => {
        const btn = document.createElement('button');
        btn.textContent = _vcLabels[key];
        btn.title = _vcTitles[key];
        const isCtr = key === 'iso';
        const _bg0 = isCtr ? 'rgba(25,118,210,0.14)' : 'rgba(255,255,255,0.88)';
        const _col0 = isCtr ? '#1565c0' : '#444';
        const _brd0 = isCtr ? '#1976d2' : 'rgba(0,0,0,0.14)';
        btn.style.cssText = [
          'width:28px','height:28px','padding:0','cursor:pointer','line-height:1',
          'font-size:' + (isCtr ? '0.88rem' : '0.62rem'),
          'border-radius:4px','border:1px solid ' + _brd0,
          'background:' + _bg0, 'backdrop-filter:blur(4px)', 'color:' + _col0,
        ].join(';');
        btn.addEventListener('mouseenter', () => {
          btn.style.background = 'rgba(25,118,210,0.22)';
          btn.style.borderColor = '#1976d2'; btn.style.color = '#0d47a1';
        });
        btn.addEventListener('mouseleave', () => {
          btn.style.background = _bg0; btn.style.borderColor = _brd0; btn.style.color = _col0;
        });
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const base = _vcPresets[key];
          if (!base) return;
          // Recompute distance for current FOV so model always fills the frame.
          // _vcPresets were built at FOV=45°; scale distance by tan(22.5°)/tan(currentHalf).
          const dir  = base.clone().sub(_ctr);
          const dist = dir.length();
          const fovFactor = Math.tan(22.5 * Math.PI / 180)
                          / Math.tan(camera.fov / 2 * Math.PI / 180);
          controls.teleport(_ctr.clone().addScaledVector(dir.normalize(), dist * fovFactor));
        });
        vcEl.appendChild(btn);
      });

    // ── Projection toggle (투시 ↔ 등축) ──────────────────────────────────────
    // FOV 45°=투시, 5°=등축(fake-ortho). Distance scales to preserve apparent size.
    let _isoProj = false;
    const projBtn = document.createElement('button');
    projBtn.style.cssText = [
      'grid-column:1/4','margin-top:3px','height:20px','padding:0',
      'font-size:0.60rem','border-radius:4px','border:1px solid rgba(0,0,0,0.14)',
      'background:rgba(255,255,255,0.88)','backdrop-filter:blur(4px)',
      'color:#444','cursor:pointer','width:86px',
    ].join(';');
    function _syncProjBtn() {
      projBtn.textContent = _isoProj ? '▦ 등축 → 투시' : '▧ 투시 → 등축';
      projBtn.title = _isoProj ? '투시(Perspective)로 전환' : '등축(Orthographic)으로 전환';
      projBtn.style.background = _isoProj ? 'rgba(25,118,210,0.14)' : 'rgba(255,255,255,0.88)';
      projBtn.style.color      = _isoProj ? '#1565c0' : '#444';
    }
    _syncProjBtn();
    projBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      _isoProj = !_isoProj;
      const oldFov = camera.fov;
      const newFov = _isoProj ? 5 : 45;
      controls.scaleDist(Math.tan(oldFov / 2 * Math.PI / 180) / Math.tan(newFov / 2 * Math.PI / 180));
      camera.fov = newFov;
      camera.updateProjectionMatrix();
      // 등축: 카메라가 멀어져 안개에 묻히므로 제거. 투시: 복원.
      scene.fog = _isoProj ? null : new THREE.Fog(0xf0f4f8, 60, 120);
      _syncProjBtn();
    });
    vcEl.appendChild(projBtn);

    if (canvas.parentElement) canvas.parentElement.appendChild(vcEl);

    // ── Resize observer ───────────────────────────────────────────────────────
    const resizeObs = new ResizeObserver(() => {
      const cw = canvas.parentElement ? canvas.parentElement.clientWidth : canvas.clientWidth;
      const ch = canvas.parentElement ? canvas.parentElement.clientHeight : canvas.clientHeight;
      if (cw > 0 && ch > 0) {
        renderer.setSize(cw, ch, false);
        camera.aspect = cw / ch;
        camera.updateProjectionMatrix();
      }
    });
    if (canvas.parentElement) resizeObs.observe(canvas.parentElement);

    // Pre-build BVH for all click targets
    if (window.MeshBVHLib) {
      clickTargets.forEach(function (t) {
        if (t.mesh && t.mesh.geometry) {
          try { t.mesh.geometry.computeBoundsTree(); } catch (e) {}
        }
      });
    }

    // ── Raycaster for click ───────────────────────────────────────────────────
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    let tooltip = null;

    function onCanvasClick(event) {
      if (event.button !== 0 || isPanDragging()) return;
      const rect = canvas.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width)  * 2 - 1;
      mouse.y = -((event.clientY - rect.top)  / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const meshes = clickTargets.map(t => t.mesh).filter(Boolean);
      const hits = raycaster.intersectObjects(meshes, true);
      if (hits.length === 0) return;
      const hit = hits[0].object;
      const target = clickTargets.find(t => t.mesh === hit || (t.group && t.group.children.includes(hit)));
      if (!target) return;
      const state = actStates[target.slot] || {};
      showDeviceTooltip(event.clientX, event.clientY, target.slot, state);
    }
    canvas.addEventListener('click', onCanvasClick);

    function showDeviceTooltip(cx, cy, slot, state) {
      if (tooltip) tooltip.remove();
      tooltip = document.createElement('div');
      tooltip.style.cssText = [
        'position:fixed', 'z-index:9999', 'background:#1e2a35', 'color:#fff',
        'padding:0.5rem 0.75rem', 'border-radius:8px', 'font-size:0.82rem',
        'pointer-events:none', 'max-width:220px', 'box-shadow:0 4px 12px rgba(0,0,0,0.4)'
      ].join(';');
      tooltip.innerHTML =
        '<b>' + _slotLabel(slot) + '</b><br>' +
        (state.name ? '장치: ' + state.name + '<br>' : '') +
        '상태: ' + (state.on ? '<span style="color:#4fc3f7">ON</span>' : '<span style="color:#9e9e9e">OFF</span>') +
        (state.percent != null ? ' / ' + state.percent + '%' : '') +
        '<br><small style="color:#888">' + slot + '</small>';
      tooltip.style.left = (cx + 12) + 'px';
      tooltip.style.top  = (cy - 8) + 'px';
      document.body.appendChild(tooltip);
      setTimeout(() => { if (tooltip) tooltip.remove(); tooltip = null; }, 3500);
    }

    // ── Animate ───────────────────────────────────────────────────────────────
    let animId;
    function animate() {
      animId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    }
    animate();

    // ── Cleanup ───────────────────────────────────────────────────────────────
    function dispose() {
      cancelAnimationFrame(animId);
      resizeObs.disconnect();
      controls.dispose();
      canvas.removeEventListener('click', onCanvasClick);
      if (tooltip) tooltip.remove();
      if (vcEl.parentElement) vcEl.parentElement.removeChild(vcEl);
      if (window.MeshBVHLib) {
        clickTargets.forEach(function (t) {
          if (t.mesh && t.mesh.geometry && t.mesh.geometry.boundsTree) {
            try { t.mesh.geometry.disposeBoundsTree(); } catch (e) {}
          }
        });
      }
      renderer.dispose();
    }

    return { renderer, scene, camera, controls, dispose };
  }

  // ── Slot label map ────────────────────────────────────────────────────────────
  function _slotLabel(key) {
    return {
      outer_side_vent_motor: '외측 측창 모터',
      outer_roof_vent_motor: '외측 천창 모터',
      inner_side_vent_motor: '내측 측창 모터',
      inner_roof_vent_motor: '내측 천창 모터',
      thermal_curtain:       '보온 커튼',
      shade_curtain:         '차광 커튼',
      irrigation_valve:      '관수 밸브',
      circulation_fan:       '순환 팬',
      exhaust_fan:           '배기 팬',
      heater:                '히터',
      cooler:                '쿨러',
      heat_pump:             '히트 펌프',
    }[key] || key;
  }

  // ── Map-layer mesh builder (envelope only, no equipment/vents/pipes) ──────────
  // Returns a THREE.Group centred at origin (model space).
  // userData.cx / .cz = half-extents so callers can translate from polygon centroid.
  // userData.orientDeg = raw orientation from spec (applied by caller in world transform).
  function buildFacilityMesh(facility) {
    const g3d      = facility.geometry_3d || {};
    const envelope = facility.envelope    || {};

    const span      = parseFloat(g3d.span_width_m)   || 7;
    const eaveH     = parseFloat(g3d.eave_height_m)  || 2;
    const ridgeH    = parseFloat(g3d.ridge_height_m) || 4;
    const length    = parseFloat(g3d.length_m)       || 30;
    const roofType  = String(g3d.roof_type || 'arch').toLowerCase();
    const orientDeg = parseFloat(g3d.orientation_deg) || 0;
    const bayCount  = facility.structure === 'connected'
      ? Math.max(parseInt(facility.bay_count || 1, 10), 1) : 1;
    const isDouble  = (envelope.layer_count || 1) === 2;
    const effectiveSpacing = facility.structure === 'connected' ? 0 : (parseFloat(g3d.spacing_m) || 1);
    const totalWidth = bayCount * span + (bayCount - 1) * effectiveSpacing;

    const cx = totalWidth / 2, cz = length / 2;

    const outerEnvSpec  = envelope.outer || {};
    const innerEnvSpec  = envelope.inner || {};
    const outerCoverMat = outerEnvSpec.cover_material || 'vinyl_double';
    const innerCoverMat = innerEnvSpec.cover_material || 'non_woven_fabric';

    const group = new THREE.Group();
    group.name = 'facility_mesh_' + (facility.unique_id || 'unknown');

    // Outer cover
    const extrudeSettings = { steps: 1, depth: length, bevelEnabled: false };
    const outerShape = _buildMultiSpanShape(span, eaveH, ridgeH, roofType, bayCount, effectiveSpacing);
    const outerGeo   = new THREE.ExtrudeGeometry(outerShape, extrudeSettings);
    const outerMesh  = new THREE.Mesh(outerGeo, MAT.cover(outerCoverMat));
    outerMesh.name = 'outer_cover';
    group.add(outerMesh);

    // Wireframe edges for roof silhouette
    group.add(new THREE.LineSegments(
      new THREE.EdgesGeometry(outerGeo),
      new THREE.LineBasicMaterial({ color: 0x455a64, linewidth: 1 })
    ));

    // Inner cover (double-layer)
    if (isDouble) {
      const inset = 0.15;
      const innerShape = _buildMultiSpanShape(
        span - inset * 2, eaveH - inset * 0.5, ridgeH - inset, roofType, bayCount, effectiveSpacing
      );
      const innerGeo  = new THREE.ExtrudeGeometry(innerShape,
        { steps: 1, depth: length - inset * 2, bevelEnabled: false });
      const innerMesh = new THREE.Mesh(innerGeo, MAT.coverInner(innerCoverMat));
      innerMesh.position.set(inset, 0, inset);
      innerMesh.name = 'inner_cover';
      group.add(innerMesh);
    }

    // Gutter posts (connected bays)
    if (facility.structure === 'connected') {
      const gutterMat = new THREE.MeshStandardMaterial({ color: 0x607d8b, roughness: 0.5, metalness: 0.5 });
      for (let b = 1; b < bayCount; b++) {
        const col = new THREE.Mesh(new THREE.BoxGeometry(0.05, eaveH, 0.05), gutterMat);
        col.position.set(b * span, eaveH / 2, length * 0.25);
        group.add(col);
        const col2 = col.clone();
        col2.position.set(b * span, eaveH / 2, length * 0.75);
        group.add(col2);
      }
    }

    group.userData.cx        = cx;
    group.userData.cz        = cz;
    group.userData.orientDeg = orientDeg;
    group.userData.totalWidth = totalWidth;
    group.userData.length     = length;

    return group;
  }

  global.AoTFacility3D = { buildScene, buildFacilityMesh };
})(window);
