// aot-facility-3d.js — AoT Facility 3D scene orchestrator
// Public API (unchanged): window.AoTFacility3D = { buildScene, buildFacilityMesh }
// New:  window.AoTFacilityState — pub/sub spec state (양방향 바인딩)
//       GLTF asset render path (render_mode='asset')
//
// Module load order (templates must inject before this file):
//   three.min.js → OrbitControls.js → three-mesh-bvh.js → GLTFLoader.js
//   → core/materials.js → core/parametric.js → assets/gltf_loader.js
// Falls back to inline implementations if sub-modules are absent.
(function (global) {
  'use strict';

  // ── Module resolution (use extracted modules if present, else inline) ────────
  // Materials
  const MAT = (function () {
    if (global.AoTMaterials) return global.AoTMaterials;
    // Inline fallback (identical to core/materials.js)
    const _CO = {
      vinyl_single:  { color: 0x9ecfef, opacity: 0.25 },
      vinyl_double:  { color: 0x9ecfef, opacity: 0.32 },
      po_film:       { color: 0xbcdff0, opacity: 0.28 },
      polycarbonate: { color: 0xdaeeff, opacity: 0.46 },
      glass:         { color: 0xc8eecc, opacity: 0.18 },
    };
    return {
      cover:          t => { const o=_CO[t]||_CO.vinyl_double; return new THREE.MeshPhysicalMaterial({color:o.color,transparent:true,opacity:o.opacity,side:THREE.DoubleSide,roughness:0.05,metalness:0}); },
      coverInner:     t => { const o=_CO[t]||{color:0xd0eaff,opacity:0.18}; return new THREE.MeshPhysicalMaterial({color:o.color,transparent:true,opacity:Math.min(o.opacity*0.65,0.22),side:THREE.DoubleSide,roughness:0.05,metalness:0}); },
      frame:          () => new THREE.MeshStandardMaterial({color:0x888888,roughness:0.6,metalness:0.4}),
      floor:          () => new THREE.MeshStandardMaterial({color:0xb8b8b8,roughness:0.85}),
      sashOpen:       () => new THREE.MeshStandardMaterial({color:0xffb300,transparent:true,opacity:0.75,side:THREE.DoubleSide}),
      sashClosed:     () => new THREE.MeshStandardMaterial({color:0x607d8b,transparent:true,opacity:0.55,side:THREE.DoubleSide}),
      curtainThermal: () => new THREE.MeshStandardMaterial({color:0xf5e6c8,transparent:true,opacity:0.80,side:THREE.DoubleSide}),
      curtainShade:   () => new THREE.MeshStandardMaterial({color:0x4a4a4a,transparent:true,opacity:0.70,side:THREE.DoubleSide}),
      fan:            () => new THREE.MeshStandardMaterial({color:0x546e7a}),
      fanOn:          () => new THREE.MeshStandardMaterial({color:0x29b6f6,emissive:0x0288d1,emissiveIntensity:0.6}),
      heater:         () => new THREE.MeshStandardMaterial({color:0xef9a9a}),
      heaterOn:       () => new THREE.MeshStandardMaterial({color:0xf44336,emissive:0xe53935,emissiveIntensity:0.8}),
      cooler:         () => new THREE.MeshStandardMaterial({color:0x80cbc4}),
      coolerOn:       () => new THREE.MeshStandardMaterial({color:0x00bcd4,emissive:0x0097a7,emissiveIntensity:0.6}),
      pump:           () => new THREE.MeshStandardMaterial({color:0x81c784}),
      pumpOn:         () => new THREE.MeshStandardMaterial({color:0x4caf50,emissive:0x388e3c,emissiveIntensity:0.6}),
      windArrow:      () => new THREE.MeshStandardMaterial({color:0x0288d1}),
      compass:        () => new THREE.MeshStandardMaterial({color:0xe53935}),
    };
  })();

  // Parametric builders
  const P = (function () {
    if (global.AoTParametric) return global.AoTParametric;
    // Inline fallback — delegates to local functions defined below
    return null;  // resolved after local defs
  })();

  // ── FacilityState — singleton pub/sub spec state ─────────────────────────────
  const FacilityState = (function () {
    let _spec = null;       // current facility spec dict
    let _runtime = null;
    let _subs = [];
    let _debounceTimer = null;

    function subscribe(fn) { _subs.push(fn); return () => { _subs = _subs.filter(s => s !== fn); }; }

    function _emit() {
      _subs.forEach(fn => { try { fn({ spec: _spec, runtime: _runtime }); } catch (e) {} });
    }

    function patch(delta, immediate) {
      if (!_spec) _spec = {};
      _deepMerge(_spec, delta);
      if (immediate) { _emit(); return; }
      clearTimeout(_debounceTimer);
      _debounceTimer = setTimeout(_emit, 150);
    }

    function setSpec(spec) { _spec = spec; _emit(); }
    function setRuntime(rt) { _runtime = rt; _emit(); }
    function getSpec() { return _spec; }
    function getRuntime() { return _runtime; }

    function _deepMerge(target, src) {
      if (!src || typeof src !== 'object') return;
      Object.keys(src).forEach(k => {
        if (src[k] && typeof src[k] === 'object' && !Array.isArray(src[k])) {
          if (!target[k] || typeof target[k] !== 'object') target[k] = {};
          _deepMerge(target[k], src[k]);
        } else {
          target[k] = src[k];
        }
      });
    }

    return { subscribe, patch, setSpec, setRuntime, getSpec, getRuntime };
  })();

  global.AoTFacilityState = FacilityState;

  // ── Parametric geometry helpers (inline — also available via core/parametric.js) ─

  function _buildMultiSpanShape(span, eaveH, ridgeH, roofType, bayCount, spacing) {
    if (P) return P.buildMultiSpanShape(span, eaveH, ridgeH, roofType, bayCount, spacing);
    const s = new THREE.Shape();
    s.moveTo(0, 0); s.lineTo(0, eaveH);
    for (let b = 0; b < bayCount; b++) {
      const lx = b * (span + spacing), rx = lx + span;
      if (roofType === 'gable') { s.lineTo(lx + span / 2, ridgeH); s.lineTo(rx, eaveH); }
      else if (roofType === 'flat' || roofType === 'box') { s.lineTo(lx, ridgeH); s.lineTo(rx, ridgeH); s.lineTo(rx, eaveH); }
      else { s.bezierCurveTo(lx, ridgeH, rx, ridgeH, rx, eaveH); }
      if (spacing > 0 && b < bayCount - 1) s.lineTo(rx + spacing, eaveH);
    }
    const tw = bayCount * span + (bayCount - 1) * spacing;
    s.lineTo(tw, 0); s.lineTo(0, 0);
    return s;
  }

  function buildSideVentSash(eaveH, length, openRatio, isRight) {
    if (P) return P.buildSideVentSash(eaveH, length, openRatio, isRight, MAT);
    const ventH = Math.min(eaveH * 0.40, 1.2);
    const geo = new THREE.PlaneGeometry(length * 0.85, ventH);
    geo.translate(0, -ventH / 2, 0);
    const isOpen = openRatio > 0.05;
    const mesh = new THREE.Mesh(geo, isOpen ? MAT.sashOpen() : MAT.sashClosed());
    mesh.name = 'side_vent_' + (isRight ? 'right' : 'left');
    mesh.rotation.y = isRight ? -Math.PI / 2 : Math.PI / 2;
    if (isOpen) mesh.rotation.x = -openRatio * (Math.PI / 3);
    return mesh;
  }

  function buildRoofVentIndicator(span, ridgeH, length, openRatio) {
    if (P) return P.buildRoofVentIndicator(span, ridgeH, length, openRatio, MAT);
    const ventW = span * 0.22, ventL = length * 0.75;
    const geo = new THREE.PlaneGeometry(ventW, ventL);
    const isOpen = openRatio > 0.05;
    const mesh = new THREE.Mesh(geo, isOpen ? MAT.sashOpen() : MAT.sashClosed());
    mesh.name = 'roof_vent';
    mesh.rotation.x = -(Math.PI / 2) + (isOpen ? openRatio * (Math.PI / 5) : 0);
    return mesh;
  }

  function buildCurtain(totalWidth, eaveH, length, type, deployRatio) {
    if (P) return P.buildCurtain(totalWidth, eaveH, length, type, deployRatio, MAT);
    const w = totalWidth * Math.max(deployRatio, 0.02);
    const geo = new THREE.PlaneGeometry(w, length);
    geo.rotateX(-Math.PI / 2);
    const mat = type === 'thermal' ? MAT.curtainThermal() : MAT.curtainShade();
    const mesh = new THREE.Mesh(geo, mat);
    mesh.name = 'curtain_' + type;
    mesh.position.set(w / 2, eaveH + 0.08, length / 2);
    return mesh;
  }

  function buildDeviceIcon(type, isOn, position) {
    if (P) return P.buildDeviceIcon(type, isOn, position, MAT);
    const g = new THREE.Group(); g.name = 'device_' + type; g.position.copy(position);
    let geo, mat;
    if (type === 'fan' || type === 'circulation_fan' || type === 'exhaust_fan') {
      geo = new THREE.TorusGeometry(0.18, 0.04, 8, 16); mat = isOn ? MAT.fanOn() : MAT.fan();
    } else if (type === 'heater') {
      geo = new THREE.BoxGeometry(0.4, 0.12, 0.12); mat = isOn ? MAT.heaterOn() : MAT.heater();
    } else if (type === 'cooler' || type === 'heat_pump') {
      geo = new THREE.BoxGeometry(0.4, 0.12, 0.12); mat = isOn ? MAT.coolerOn() : MAT.cooler();
    } else if (type === 'irrigation_valve') {
      geo = new THREE.CylinderGeometry(0.06, 0.06, 0.25, 8); mat = isOn ? MAT.pumpOn() : MAT.pump();
    } else {
      geo = new THREE.SphereGeometry(0.1, 8, 8); mat = new THREE.MeshStandardMaterial({color: isOn ? 0x4caf50 : 0x9e9e9e});
    }
    g.add(new THREE.Mesh(geo, mat));
    if (isOn) { const r = new THREE.Mesh(new THREE.TorusGeometry(0.25,0.015,8,16), new THREE.MeshStandardMaterial({color:0xffffff,transparent:true,opacity:0.5})); g.add(r); }
    return g;
  }

  function buildWindArrow(windDeg, length) {
    if (P) return P.buildWindArrow(windDeg, length, MAT);
    const group = new THREE.Group(); group.name = 'wind_arrow';
    group.add(new THREE.Mesh(new THREE.CylinderGeometry(0.04,0.04,1.2,8), MAT.windArrow()));
    const head = new THREE.Mesh(new THREE.ConeGeometry(0.12,0.35,8), MAT.windArrow());
    head.position.y = 0.77; group.add(head);
    group.position.set(0, 3.0, length / 2);
    group.rotation.y = THREE.MathUtils.degToRad(windDeg + 180);
    return group;
  }

  function buildCompass(orientationDeg, length) {
    if (P) return P.buildCompass(orientationDeg, length, MAT);
    const group = new THREE.Group(); group.name = 'compass';
    group.add(new THREE.Mesh(new THREE.ConeGeometry(0.08,0.45,8), MAT.compass()));
    group.position.set(0, 0.5, length + 1.2);
    group.rotation.y = THREE.MathUtils.degToRad(-orientationDeg);
    return group;
  }

  function buildPipe(pts, radius, color, opacity) {
    const curve = new THREE.CatmullRomCurve3(pts.map(([x,y,z]) => new THREE.Vector3(x,y,z)));
    const geo = new THREE.TubeGeometry(curve, Math.max(pts.length*4,8), radius, 6, false);
    const mat = new THREE.MeshStandardMaterial({color,roughness:0.55,metalness:0.35,transparent:opacity<1,opacity:opacity!=null?opacity:1});
    const m = new THREE.Mesh(geo, mat); m.name = 'pipe'; return m;
  }

  function buildIrrigationPipes(totalWidth, length, span, bayCount, effectiveSpacing, isOn) {
    if (P) return P.buildIrrigationPipes(totalWidth, length, span, bayCount, effectiveSpacing, isOn, MAT);
    const group = new THREE.Group(); group.name = 'irrigation_pipes';
    const color = isOn ? 0x29b6f6 : 0x607d8b, pH = 0.18, cx = totalWidth / 2;
    group.add(buildPipe([[cx,pH,0.5],[cx,pH,length-0.5]], 0.038, color, 1.0));
    for (let b = 0; b < bayCount; b++) {
      const bx = b*(span+effectiveSpacing)+span/2;
      [0.15,0.35,0.50,0.65,0.85].forEach(zf => {
        group.add(buildPipe([[bx-span*0.44,pH,length*zf],[cx,pH,length*zf],[bx+span*0.44,pH,length*zf]],0.020,color,0.82));
      });
    }
    return group;
  }

  function buildHeatingPipes(totalWidth, length, isOn) {
    if (P) return P.buildHeatingPipes(totalWidth, length, isOn);
    const group = new THREE.Group(); group.name = 'heating_pipes';
    const color = isOn ? 0xef5350 : 0x795548, pH = 0.22, inset = 0.35;
    [inset, totalWidth-inset].forEach(x => {
      group.add(buildPipe([[x,pH,0.4],[x,pH,length-0.4]], 0.030, color, 1.0));
    });
    return group;
  }

  // ── GLB device icon loader (existing behaviour) ───────────────────────────────
  function _tryLoadGLB(type, position, parentGroup) {
    if (!window.THREE || !THREE.GLTFLoader) return;
    const loader = new THREE.GLTFLoader();
    loader.load('/static/models/aot_devices/' + type + '.glb',
      function (gltf) {
        const model = gltf.scene; model.scale.setScalar(0.42); model.position.copy(position);
        model.name = 'glb_' + type; if (parentGroup) parentGroup.add(model);
      }, undefined, function () {});
  }

  // ── GLTF user-asset scene builder (render_mode='asset') ──────────────────────
  function _buildAssetScene(canvas, facility, runtime, opts) {
    const W = opts.W, H = opts.H;
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(W, H, false);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf0f4f8);

    const camera = new THREE.PerspectiveCamera(45, W / H, 0.1, 1500);
    camera.position.set(8, 6, 12);
    camera.lookAt(0, 1, 0);

    const controls = new THREE.MapControls(camera, renderer.domElement);
    controls.target.set(0, 1, 0);
    controls.enableDamping = true; controls.dampingFactor = 0.12; controls.update();

    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const sun = new THREE.DirectionalLight(0xfff4d6, 0.85); sun.position.set(10, 20, 10); scene.add(sun);

    // Ground
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(100,100), new THREE.MeshStandardMaterial({color:0xffffff,roughness:0.9}));
    ground.rotation.x = -Math.PI/2; ground.position.y = -0.01; scene.add(ground);
    scene.add(Object.assign(new THREE.GridHelper(50,25,0xbbbbbb,0xdddddd), {position:{y:0.005}}));

    // Status label
    const statusEl = opts.statusEl;
    if (statusEl) statusEl.textContent = '자산 모델 로딩 중…';

    const transform = facility.model_transform;
    const assetInfo = opts.assetInfo;  // {unique_id, source_file}

    if (assetInfo && assetInfo.source_file && window.AoTGLTFLoader) {
      AoTGLTFLoader.loadAsset(
        assetInfo.unique_id, assetInfo.source_file, transform, scene,
        function (model) {
          // Auto-fit camera to bounding box
          const box = new THREE.Box3().setFromObject(model);
          const center = box.getCenter(new THREE.Vector3());
          const size = box.getSize(new THREE.Vector3());
          const maxDim = Math.max(size.x, size.y, size.z);
          camera.position.set(center.x + maxDim * 1.2, center.y + maxDim * 0.8, center.z + maxDim * 1.5);
          camera.lookAt(center);
          controls.target.copy(center);
          controls.update();
          if (statusEl) statusEl.textContent = '';
        },
        function (err) {
          console.warn('[AoT 3D] Asset load error:', err);
          if (statusEl) statusEl.textContent = '모델 로드 실패';
        }
      );
    } else if (statusEl) {
      statusEl.textContent = '자산 정보 없음';
    }

    const resizeObs = new ResizeObserver(() => {
      const cw = canvas.parentElement ? canvas.parentElement.clientWidth : canvas.clientWidth;
      const ch = canvas.parentElement ? canvas.parentElement.clientHeight : canvas.clientHeight;
      if (cw > 0 && ch > 0) { renderer.setSize(cw,ch,false); camera.aspect=cw/ch; camera.updateProjectionMatrix(); }
    });
    if (canvas.parentElement) resizeObs.observe(canvas.parentElement);

    let animId;
    function animate() { animId = requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); }
    animate();

    function dispose() {
      cancelAnimationFrame(animId); resizeObs.disconnect(); controls.dispose(); renderer.dispose();
    }
    return { renderer, scene, camera, controls, dispose };
  }

  // ── Slot label map ────────────────────────────────────────────────────────────
  function _slotLabel(key) {
    return ({
      outer_side_vent_motor:'외측 측창 모터', outer_roof_vent_motor:'외측 천창 모터',
      inner_side_vent_motor:'내측 측창 모터', inner_roof_vent_motor:'내측 천창 모터',
      thermal_curtain:'보온 커튼', shade_curtain:'차광 커튼', irrigation_valve:'관수 밸브',
      circulation_fan:'순환 팬', exhaust_fan:'배기 팬', heater:'히터', cooler:'쿨러', heat_pump:'히트 펌프',
    })[key] || key;
  }

  // ── Main builder (public, backward-compat) ───────────────────────────────────
  function buildScene(canvas, facility, runtime) {
    // Update FacilityState
    FacilityState.setSpec(facility);
    if (runtime) FacilityState.setRuntime(runtime);

    const parent = canvas.parentElement;
    const W = (parent && parent.clientWidth) || canvas.clientWidth || 400;
    const H = (parent && parent.clientHeight) || canvas.clientHeight || 340;

    // ── GLTF asset render path ────────────────────────────────────────────────
    if (facility.render_mode === 'asset' && facility.model_asset_uuid) {
      // Fetch asset info then render
      const statusEl = parent && parent.querySelector('.aot-3d-asset-status');
      const opts = { W, H, statusEl, assetInfo: null };

      // If asset source already attached to facility object (pre-fetched)
      if (facility._asset_source_file) {
        opts.assetInfo = { unique_id: facility.model_asset_uuid, source_file: facility._asset_source_file };
        return _buildAssetScene(canvas, facility, runtime, opts);
      }

      // Otherwise fetch from API
      fetch('/api/geo/model_assets/' + facility.model_asset_uuid)
        .then(r => r.ok ? r.json() : null)
        .then(function (asset) {
          if (!asset || !asset.source_file) return;
          opts.assetInfo = { unique_id: asset.unique_id, source_file: asset.source_file };
          // Renderer already set up without model — add model now
          // (simplification: full rebuild with asset info)
          ctx.dispose && ctx.dispose();
        })
        .catch(() => {});

      // Render empty scene while fetching
      const ctx = _buildParametricScene(canvas, facility, runtime, W, H);
      return ctx;
    }

    // ── Parametric render path (default) ─────────────────────────────────────
    return _buildParametricScene(canvas, facility, runtime, W, H);
  }

  function _buildParametricScene(canvas, facility, runtime, W, H) {
    const g3d = facility.geometry_3d || {};
    const envelope = facility.envelope || {};
    const actuators = facility.actuators || {};
    const actStates = (runtime && runtime.actuator_states) || {};
    const outdoor = (runtime && runtime.outdoor) || {};

    const span      = parseFloat(g3d.span_width_m)   || 7;
    const eaveH     = parseFloat(g3d.eave_height_m)  || 2;
    const ridgeH    = parseFloat(g3d.ridge_height_m) || 4;
    const length    = parseFloat(g3d.length_m)       || 30;
    const roofType  = String(g3d.roof_type || 'arch').toLowerCase();
    const orientDeg = parseFloat(g3d.orientation_deg) || 0;
    const bayCount  = facility.structure === 'connected' ? Math.max(parseInt(facility.bay_count||1,10),1) : 1;
    const isDouble  = (envelope.layer_count || 1) === 2;
    const effectiveSpacing = facility.structure === 'connected' ? 0 : (parseFloat(g3d.spacing_m)||1);
    const totalWidth = bayCount * span + (bayCount-1) * effectiveSpacing;

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(W, H, false);
    renderer.shadowMap.enabled = true;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf0f4f8);
    scene.fog = new THREE.Fog(0xf0f4f8, 60, 120);

    const cx = totalWidth/2, cz = length/2, cy = ridgeH*0.5;
    const camera = new THREE.PerspectiveCamera(45, W/H, 0.1, 1500);
    camera.position.set(totalWidth*0.7, ridgeH*2.2, length*0.9);
    camera.lookAt(cx, cy, cz);

    const _origTarget = new THREE.Vector3(cx, cy, cz);
    const controls = new THREE.MapControls(camera, renderer.domElement);
    controls.target.copy(_origTarget);
    controls.enableDamping = true; controls.dampingFactor = 0.12;
    controls.panSpeed = 0.5; controls.rotateSpeed = 0.8;
    controls.minDistance = 2; controls.maxDistance = 800;
    controls.maxPolarAngle = Math.PI * 0.82;
    controls.update();
    renderer.domElement.style.cursor = 'crosshair';

    if (window.MeshBVHLib) {
      THREE.BufferGeometry.prototype.computeBoundsTree = MeshBVHLib.computeBoundsTree;
      THREE.BufferGeometry.prototype.disposeBoundsTree = MeshBVHLib.disposeBoundsTree;
      THREE.Mesh.prototype.raycast = MeshBVHLib.acceleratedRaycast;
    }

    let _dragged = false;
    renderer.domElement.addEventListener('mousedown', () => { _dragged = false; });
    renderer.domElement.addEventListener('mousemove', (e) => { if (e.buttons) _dragged = true; });

    function teleport(newCamPos) {
      if (window.gsap) {
        gsap.killTweensOf(camera.position); gsap.killTweensOf(controls.target);
        gsap.to(camera.position, {x:newCamPos.x,y:newCamPos.y,z:newCamPos.z,duration:0.65,ease:'power2.inOut',onUpdate:()=>controls.update()});
        gsap.to(controls.target, {x:_origTarget.x,y:_origTarget.y,z:_origTarget.z,duration:0.65,ease:'power2.inOut',onUpdate:()=>controls.update()});
      } else { controls.target.copy(_origTarget); camera.position.copy(newCamPos); controls.update(); }
    }
    function scaleDist(factor) {
      const dir = camera.position.clone().sub(controls.target);
      camera.position.copy(controls.target.clone().addScaledVector(dir.normalize(), dir.length()*factor));
      controls.update();
    }
    controls.teleport = teleport; controls.scaleDist = scaleDist; controls.isPanDragging = () => _dragged;

    const solarIntensity = outdoor.solar_wm2!=null ? 0.4+Math.min(outdoor.solar_wm2/1000,1)*0.8 : 0.85;
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const sun = new THREE.DirectionalLight(0xfff4d6, solarIntensity);
    sun.position.set(30,60,40); sun.castShadow = true; scene.add(sun);

    const outerEnvSpec = envelope.outer || {};
    const innerEnvSpec = envelope.inner || {};
    const outerCoverMat = outerEnvSpec.cover_material || 'vinyl_double';
    const innerCoverMat = innerEnvSpec.cover_material || 'non_woven_fabric';
    const ghGroup = new THREE.Group(); ghGroup.name = 'greenhouse'; scene.add(ghGroup);
    const clickTargets = [];

    const extrudeSettings = { steps:1, depth:length, bevelEnabled:false };
    const outerShape = _buildMultiSpanShape(span, eaveH, ridgeH, roofType, bayCount, effectiveSpacing);
    const outerGeo = new THREE.ExtrudeGeometry(outerShape, extrudeSettings);
    const outerMesh = new THREE.Mesh(outerGeo, MAT.cover(outerCoverMat));
    outerMesh.name = 'outer_cover'; ghGroup.add(outerMesh);
    ghGroup.add(new THREE.LineSegments(new THREE.EdgesGeometry(outerGeo), new THREE.LineBasicMaterial({color:0x455a64})));

    if (isDouble) {
      const inset = 0.15;
      const innerShape = _buildMultiSpanShape(span-inset*2, eaveH-inset*0.5, ridgeH-inset, roofType, bayCount, effectiveSpacing);
      const innerGeo = new THREE.ExtrudeGeometry(innerShape, {...extrudeSettings, depth:length-inset*2});
      const innerMesh = new THREE.Mesh(innerGeo, MAT.coverInner(innerCoverMat));
      innerMesh.name = 'inner_cover'; innerMesh.position.set(inset,0,inset); ghGroup.add(innerMesh);
    }

    if (facility.structure === 'connected') {
      const gm = new THREE.MeshStandardMaterial({color:0x607d8b,roughness:0.5,metalness:0.5});
      for (let b=1; b<bayCount; b++) {
        [length*0.25, length*0.75].forEach(z => {
          const col = new THREE.Mesh(new THREE.BoxGeometry(0.05,eaveH,0.05), gm);
          col.position.set(b*span, eaveH/2, z); ghGroup.add(col);
        });
      }
    }

    const floorGeo = new THREE.BoxGeometry(totalWidth,0.06,length);
    const floorMesh = new THREE.Mesh(floorGeo, MAT.floor());
    floorMesh.position.set(totalWidth/2, 0.03, length/2);
    floorMesh.name = 'facility_floor';   // raycast target for device drag-place
    ghGroup.add(floorMesh);

    // Vents outer
    if (outerEnvSpec.side_vent && outerEnvSpec.side_vent.enabled) {
      const st = actStates['outer_side_vent_motor'], openR = st ? (st.on ? 0.65 : 0) : 0;
      const sL = buildSideVentSash(eaveH,length,openR,false); sL.position.set(0,eaveH*0.45,length/2); ghGroup.add(sL);
      const sR = buildSideVentSash(eaveH,length,openR,true);  sR.position.set(totalWidth,eaveH*0.45,length/2); ghGroup.add(sR);
      clickTargets.push({mesh:sL,slot:'outer_side_vent_motor'},{mesh:sR,slot:'outer_side_vent_motor'});
    }
    if (outerEnvSpec.roof_vent && outerEnvSpec.roof_vent.enabled) {
      const st = actStates['outer_roof_vent_motor'], openR = st ? (st.on ? 0.6 : 0) : 0;
      for (let b=0; b<bayCount; b++) {
        const bx = b*(span+effectiveSpacing)+span/2;
        const vm = buildRoofVentIndicator(span,ridgeH,length,openR); vm.position.set(bx,ridgeH+0.02,length/2); ghGroup.add(vm);
        clickTargets.push({mesh:vm, slot:'outer_roof_vent_motor'});
      }
    }

    // Vents inner
    if (isDouble) {
      const inset = 0.18;
      if (innerEnvSpec.side_vent && innerEnvSpec.side_vent.enabled) {
        const st = actStates['inner_side_vent_motor'], openR = st ? (st.on ? 0.65 : 0) : 0;
        const iL = buildSideVentSash(eaveH,length*0.82,openR,false); iL.position.set(inset,eaveH*0.45,length/2); ghGroup.add(iL);
        const iR = buildSideVentSash(eaveH,length*0.82,openR,true);  iR.position.set(totalWidth-inset,eaveH*0.45,length/2); ghGroup.add(iR);
        clickTargets.push({mesh:iL,slot:'inner_side_vent_motor'},{mesh:iR,slot:'inner_side_vent_motor'});
      }
      if (innerEnvSpec.roof_vent && innerEnvSpec.roof_vent.enabled) {
        const st = actStates['inner_roof_vent_motor'], openR = st ? (st.on ? 0.6 : 0) : 0;
        for (let b=0; b<bayCount; b++) {
          const bx = b*(span+effectiveSpacing)+span/2;
          const iv = buildRoofVentIndicator(span*0.8,ridgeH-inset,length,openR); iv.position.set(bx,ridgeH-inset+0.02,length/2); ghGroup.add(iv);
          clickTargets.push({mesh:iv,slot:'inner_roof_vent_motor'});
        }
      }
    }

    // Curtains
    const curtain = envelope.curtain || {};
    if (curtain.thermal) {
      const st = actStates['thermal_curtain'], deploy = st ? (st.on ? 1.0 : 0.0) : 0.0;
      const cm = buildCurtain(totalWidth,eaveH,length,'thermal',deploy); ghGroup.add(cm);
      clickTargets.push({mesh:cm,slot:'thermal_curtain'});
    }
    if (curtain.shade) {
      const st = actStates['shade_curtain'], deploy = st ? (st.on ? 0.9 : 0.0) : 0.0;
      const cm = buildCurtain(totalWidth,eaveH,length,'shade',deploy); cm.position.y += 0.12; ghGroup.add(cm);
      clickTargets.push({mesh:cm,slot:'shade_curtain'});
    }

    // Equipment
    const centerX = Math.floor(bayCount/2)*(span+effectiveSpacing)+span/2;
    [
      {key:'circulation_fan', pos:new THREE.Vector3(centerX,eaveH*0.65,length*0.25)},
      {key:'exhaust_fan',     pos:new THREE.Vector3(centerX,eaveH*0.65,length*0.75)},
      {key:'heater',          pos:new THREE.Vector3(centerX-span*0.3,0.35,length*0.2)},
      {key:'cooler',          pos:new THREE.Vector3(centerX-span*0.3,0.35,length*0.8)},
      {key:'heat_pump',       pos:new THREE.Vector3(centerX+span*0.3,0.35,length*0.5)},
      {key:'irrigation_valve',pos:new THREE.Vector3(centerX+span*0.2,0.35,length*0.4)},
    ].forEach(({key,pos}) => {
      const state = actStates[key]; if (!actuators[key] && !state) return;
      const icon = buildDeviceIcon(key, state ? state.on : false, pos); ghGroup.add(icon);
      clickTargets.push({mesh:icon.children[0],slot:key,group:icon});
      _tryLoadGLB(key, pos, ghGroup);
    });

    // Pipes
    if (actuators['irrigation_valve'] || actStates['irrigation_valve']) {
      const iOn = !!(actStates['irrigation_valve'] && actStates['irrigation_valve'].on);
      ghGroup.add(buildIrrigationPipes(totalWidth,length,span,bayCount,effectiveSpacing,iOn));
    }
    if (actuators['heater'] || actStates['heater']) {
      const hOn = !!(actStates['heater'] && actStates['heater'].on);
      ghGroup.add(buildHeatingPipes(totalWidth,length,hOn));
    }

    // Fittings (user-placed boxes: windows, doors, curtains, devices) ─────────
    const fittings = Array.isArray(facility.fittings) ? facility.fittings : [];
    const _FIT_COLORS = {
      window:'#9ecfef', door:'#a1887f', side_window:'#bbdefb', curtain:'#f5e6c8',
      fan:'#90caf9', heater:'#ef9a9a', sensor:'#ce93d8', fixture:'#c5e1a5'
    };
    const _selFittingId = (window.FittingsUI && FittingsUI.getSelectedId)
      ? FittingsUI.getSelectedId() : null;
    // Build a full orthonormal basis from a surface normal so that:
    //   local +X (width)  → horizontal, perpendicular to the normal
    //   local +Y (height) → in-plane "up the slope" direction
    //   local +Z (depth)  → the surface normal itself
    // This avoids the "diamond/rhombus" artefact you get with setFromUnitVectors,
    // which leaves the rotation around the normal axis undefined.
    function _quatFromNormal(surfaceNormal, spinDeg) {
      if (!surfaceNormal || surfaceNormal.length !== 3) return null;
      const N = new THREE.Vector3(surfaceNormal[0], surfaceNormal[1], surfaceNormal[2]);
      if (N.lengthSq() < 0.0001) return null;
      N.normalize();

      const worldUp = new THREE.Vector3(0, 1, 0);
      let right;
      if (Math.abs(N.dot(worldUp)) > 0.99) {
        // Normal is (nearly) vertical: pick world +X as the width direction
        right = new THREE.Vector3(1, 0, 0);
      } else {
        // Width = worldUp × N → horizontal, perpendicular to N
        right = new THREE.Vector3().crossVectors(worldUp, N).normalize();
      }
      // Height = N × width → in the surface plane, pointing "up the slope"
      const up = new THREE.Vector3().crossVectors(N, right).normalize();

      const m = new THREE.Matrix4().makeBasis(right, up, N);
      const q = new THREE.Quaternion().setFromRotationMatrix(m);

      if (spinDeg) {
        // Spin around the normal (in-plane rotation)
        const spin = new THREE.Quaternion().setFromAxisAngle(N, spinDeg * Math.PI / 180);
        q.premultiply(spin);
      }
      return q;
    }

    function _orientFromNormal(meshObj, surfaceNormal, spinDeg) {
      const q = _quatFromNormal(surfaceNormal, spinDeg);
      if (!q) return false;
      meshObj.quaternion.copy(q);
      return true;
    }

    // Build & insert a single fitting (mesh + edges + clickTarget) into the
    // existing scene. Used both during initial render (forEach below) and for
    // in-place additions later via addFittingMesh — avoiding a full scene
    // rebuild (which would dispose/recreate the WebGL context, sometimes
    // leaving the canvas blank and exhausting the browser's context budget).
    function _addFittingToScene(f) {
      if (!f || !f.size || !f.position) return null;
      const w = Math.max(parseFloat(f.size.w)||0.1, 0.02);
      const h = Math.max(parseFloat(f.size.h)||0.1, 0.02);
      const d = Math.max(parseFloat(f.size.d)||0.1, 0.02);
      const px = parseFloat(f.position.x)||0;
      const py = parseFloat(f.position.y)||(h/2);
      const pz = parseFloat(f.position.z)||0;
      const rotDeg = parseFloat(f.rotation_deg)||0;
      const curSel = (window.FittingsUI && FittingsUI.getSelectedId) ? FittingsUI.getSelectedId() : null;
      const isSel  = (f.id && f.id === curSel);
      const color  = _FIT_COLORS[f.kind] || '#c5e1a5';
      const sn = (Array.isArray(f.surface_normal) && f.surface_normal.length === 3) ? f.surface_normal : null;

      const geo = new THREE.BoxGeometry(w, h, d);
      const mat = new THREE.MeshStandardMaterial({
        color: color, transparent: true,
        opacity: isSel ? 0.85 : 0.55,
        roughness: 0.6,
        emissive: isSel ? 0x1976d2 : 0x000000,
        emissiveIntensity: isSel ? 0.35 : 0,
        // depthWrite: false lets fittings on the far side of the arch (behind the
        // semi-transparent cover) remain visible regardless of Z-sort order.
        depthWrite: false,
        side: THREE.DoubleSide,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.renderOrder = 1;  // render after arch cover (renderOrder 0)
      mesh.position.set(px, py, pz);
      if (!_orientFromNormal(mesh, sn, rotDeg)) mesh.rotation.y = rotDeg * Math.PI / 180;
      mesh.name = 'fitting:' + (f.id || '');
      mesh.userData.surface_normal = sn;
      ghGroup.add(mesh);

      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(geo),
        new THREE.LineBasicMaterial({ color: isSel ? 0x1565c0 : 0x37474f, linewidth: isSel ? 2 : 1 })
      );
      edges.position.copy(mesh.position);
      edges.quaternion.copy(mesh.quaternion);
      edges.name = 'edges:fitting:' + (f.id || '');
      ghGroup.add(edges);

      if (f.id) clickTargets.push({ mesh: mesh, slot: 'fitting:' + f.id, fittingId: f.id });
      return mesh;
    }

    fittings.forEach(_addFittingToScene);

    // Wind & compass
    if (outdoor.wind_ms!=null || outdoor.wind_deg!=null) scene.add(buildWindArrow(outdoor.wind_deg||0, length));
    scene.add(buildCompass(orientDeg, length));

    // Ground & grid
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(200,200), new THREE.MeshStandardMaterial({color:0xffffff,roughness:0.90}));
    ground.rotation.x = -Math.PI/2; ground.position.y = -0.08; scene.add(ground);
    const grid = new THREE.GridHelper(100,50,0xbbbbbb,0xdddddd); grid.position.y = -0.04; scene.add(grid);

    // View cube
    const _halfFovV = camera.fov/2*Math.PI/180, _asp = camera.aspect||(W/H);
    const _halfFovH = Math.atan(Math.tan(_halfFovV)*_asp);
    const _ctr = new THREE.Vector3(cx,ridgeH/2,cz);
    const _hw=totalWidth/2, _hh=ridgeH/2, _hl=length/2, _PAD=1.18;
    function _fitD(eH,eV) { return Math.max(eH/Math.tan(_halfFovH),eV/Math.tan(_halfFovV))*_PAD; }
    const _br=Math.sqrt(_hw*_hw+_hh*_hh+_hl*_hl);
    const _dF=_fitD(_hw,_hh),_dS=_fitD(_hl,_hh),_dT=_fitD(_hw,_hl),_dC=_br/Math.sin(_halfFovV)*_PAD;
    const _vcp = {
      'back-left':_ctr.clone().addScaledVector(new THREE.Vector3(-1,1,1).normalize(),_dC),
      'top':_ctr.clone().addScaledVector(new THREE.Vector3(0,1,0),_dT),
      'back-right':_ctr.clone().addScaledVector(new THREE.Vector3(1,1,1).normalize(),_dC),
      'left':_ctr.clone().addScaledVector(new THREE.Vector3(-1,0,0),_dS),
      'iso':_ctr.clone().addScaledVector(new THREE.Vector3(0.55,0.85,-0.65).normalize(),_dC),
      'right':_ctr.clone().addScaledVector(new THREE.Vector3(1,0,0),_dS),
      'front-left':_ctr.clone().addScaledVector(new THREE.Vector3(-1,1,-1).normalize(),_dC),
      'front':_ctr.clone().addScaledVector(new THREE.Vector3(0,0,-1),_dF),
      'front-right':_ctr.clone().addScaledVector(new THREE.Vector3(1,1,-1).normalize(),_dC),
    };
    const _vcL={'back-left':'후좌','top':'위','back-right':'후우','left':'좌','iso':'●','right':'우','front-left':'전좌','front':'앞','front-right':'전우'};
    const _vcT={'back-left':'후면 좌 등각','top':'위 (평면)','back-right':'후면 우 등각','left':'좌 측면','iso':'기본 등각','right':'우 측면','front-left':'정면 좌 등각','front':'정면','front-right':'정면 우 등각'};

    const vcEl = document.createElement('div');
    vcEl.style.cssText='position:absolute;top:18px;right:8px;z-index:15;display:grid;grid-template-columns:repeat(3,28px);grid-auto-rows:28px;gap:2px';
    ['back-left','top','back-right','left','iso','right','front-left','front','front-right'].forEach(key => {
      const btn = document.createElement('button');
      btn.textContent = _vcL[key]; btn.title = _vcT[key];
      const isCtr = key==='iso';
      const _bg0=isCtr?'rgba(25,118,210,0.14)':'rgba(255,255,255,0.88)', _c0=isCtr?'#1565c0':'#444', _b0=isCtr?'#1976d2':'rgba(0,0,0,0.14)';
      btn.style.cssText=`width:28px;height:28px;padding:0;cursor:pointer;line-height:1;font-size:${isCtr?'0.88':'0.62'}rem;border-radius:4px;border:1px solid ${_b0};background:${_bg0};backdrop-filter:blur(4px);color:${_c0}`;
      btn.addEventListener('mouseenter',()=>{btn.style.background='rgba(25,118,210,0.22)';btn.style.borderColor='#1976d2';btn.style.color='#0d47a1';});
      btn.addEventListener('mouseleave',()=>{btn.style.background=_bg0;btn.style.borderColor=_b0;btn.style.color=_c0;});
      btn.addEventListener('click',e=>{
        e.stopPropagation(); const base=_vcp[key]; if(!base) return;
        const dir=base.clone().sub(_ctr), dist=dir.length();
        const ff=Math.tan(22.5*Math.PI/180)/Math.tan(camera.fov/2*Math.PI/180);
        controls.teleport(_ctr.clone().addScaledVector(dir.normalize(),dist*ff));
      });
      vcEl.appendChild(btn);
    });

    let _isoProj = false;
    const projBtn = document.createElement('button');
    projBtn.style.cssText='grid-column:1/4;margin-top:3px;height:20px;padding:0;font-size:0.60rem;border-radius:4px;border:1px solid rgba(0,0,0,0.14);background:rgba(255,255,255,0.88);backdrop-filter:blur(4px);color:#444;cursor:pointer;width:86px';
    function _syncProjBtn() {
      projBtn.textContent=_isoProj?'▦ 등축 → 투시':'▧ 투시 → 등축';
      projBtn.style.background=_isoProj?'rgba(25,118,210,0.14)':'rgba(255,255,255,0.88)';
      projBtn.style.color=_isoProj?'#1565c0':'#444';
    }
    _syncProjBtn();
    projBtn.addEventListener('click',e=>{
      e.stopPropagation(); _isoProj=!_isoProj;
      const oF=camera.fov, nF=_isoProj?5:45;
      controls.scaleDist(Math.tan(oF/2*Math.PI/180)/Math.tan(nF/2*Math.PI/180));
      camera.fov=nF; camera.updateProjectionMatrix();
      scene.fog=_isoProj?null:new THREE.Fog(0xf0f4f8,60,120); _syncProjBtn();
    });
    vcEl.appendChild(projBtn);
    if (canvas.parentElement) canvas.parentElement.appendChild(vcEl);

    // Resize observer
    const resizeObs = new ResizeObserver(() => {
      const cw=canvas.parentElement?canvas.parentElement.clientWidth:canvas.clientWidth;
      const ch=canvas.parentElement?canvas.parentElement.clientHeight:canvas.clientHeight;
      if (cw>0&&ch>0) { renderer.setSize(cw,ch,false); camera.aspect=cw/ch; camera.updateProjectionMatrix(); }
    });
    if (canvas.parentElement) resizeObs.observe(canvas.parentElement);

    if (window.MeshBVHLib) {
      clickTargets.forEach(t => { if(t.mesh&&t.mesh.geometry) { try{t.mesh.geometry.computeBoundsTree();}catch(e){} } });
    }

    const raycaster = new THREE.Raycaster(), mouse = new THREE.Vector2();
    let tooltip = null;

    // ── Tool mode ─────────────────────────────────────────────────────────
    //   _toolMode: null | wall-pick ('window'|'door'|'side_window')
    //                   | device-drag ('heater'|'fan'|'sensor'|'fixture')
    // On click while a tool is active → raycast appropriate surface →
    // dispatch 'aot-facility-add-fitting' with computed pos/normal/face.
    let _toolMode = null;
    const TOOL_DEFAULTS = {
      window:      { w: 1.2, h: 1.0, d: 0.05 },
      door:        { w: 1.0, h: 2.0, d: 0.05 },
      side_window: { w: 3.0, h: 0.8, d: 0.05 },
      heater:      { w: 0.6, h: 0.6, d: 0.4  },
      fan:         { w: 0.8, h: 0.8, d: 0.3  },
      sensor:      { w: 0.15,h: 0.15,d: 0.1  },
      fixture:     { w: 1.0, h: 1.0, d: 1.0  }
    };
    const WALL_PICK_TOOLS   = ['window', 'door', 'side_window'];
    const DEVICE_DRAG_TOOLS = ['heater', 'fan', 'sensor', 'fixture'];
    function _isWallPick()   { return WALL_PICK_TOOLS.indexOf(_toolMode) >= 0; }
    function _isDeviceDrag() { return DEVICE_DRAG_TOOLS.indexOf(_toolMode) >= 0; }

    // Hover highlight overlay
    const _hlGeo = new THREE.PlaneGeometry(1, 1);
    const _hlMat = new THREE.MeshBasicMaterial({
      color: 0x1976d2, transparent: true, opacity: 0.45, side: THREE.DoubleSide, depthTest: false
    });
    const _hlMesh = new THREE.Mesh(_hlGeo, _hlMat);
    _hlMesh.renderOrder = 999;
    _hlMesh.visible = false;
    scene.add(_hlMesh);

    function _faceFromNormal(n) {
      // Normals are the OUTWARD direction of each face. We label faces by where
      // they sit on the model, not where they "face":
      //   z = length face has outward normal +Z → 'north' (position.z = length)
      //   z = 0      face has outward normal -Z → 'south' (position.z = 0)
      //   x = totalW face has outward normal +X → 'east'  (position.x = totalW)
      //   x = 0      face has outward normal -X → 'west'  (position.x = 0)
      // Bug history: south/north were swapped, so clicks landed on the opposite
      // wall.
      if (n.y > 0.5) return 'roof';
      if (Math.abs(n.z) > Math.abs(n.x)) return n.z > 0 ? 'north' : 'south';
      return n.x > 0 ? 'east' : 'west';
    }
    const _FACE_LABELS = { roof:'지붕', south:'남', north:'북', east:'동', west:'서' };

    function _resolveOuterMesh() {
      let m = null;
      ghGroup.traverse(function (o) { if (o.isMesh && o.name === 'outer_cover') m = o; });
      return m;
    }
    let _outerMesh = _resolveOuterMesh();

    // Floating tool status chip (shows active tool + face label on hover)
    const _toolChip = document.createElement('div');
    _toolChip.style.cssText =
      'position:absolute;top:8px;left:50%;transform:translateX(-50%);z-index:25;' +
      'background:#1976d2;color:#fff;padding:0.3rem 0.75rem;border-radius:14px;' +
      'font-size:0.78rem;font-weight:600;pointer-events:none;display:none;' +
      'box-shadow:0 2px 6px rgba(0,0,0,0.2);';
    if (canvas.parentElement) canvas.parentElement.appendChild(_toolChip);

    function _updateChip(faceLabel) {
      if (!_toolMode) { _toolChip.style.display = 'none'; return; }
      const meta = { window: '🪟 창호', door: '🚪 출입문', side_window: '🪟 측창' }[_toolMode] || _toolMode;
      _toolChip.textContent = faceLabel ? (meta + ' → ' + faceLabel + ' 면') : (meta + ' (면을 클릭)');
      _toolChip.style.display = '';
    }

    function setTool(toolKind) {
      _toolMode = toolKind || null;
      if (_toolMode) {
        canvas.style.cursor = 'crosshair';
        _updateChip(null);
      } else {
        canvas.style.cursor = '';
        _hlMesh.visible = false;
        _toolChip.style.display = 'none';
      }
    }

    function _hitOuter(event) {
      if (!_outerMesh) _outerMesh = _resolveOuterMesh();
      if (!_outerMesh) return null;
      const rect = canvas.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const hits = raycaster.intersectObject(_outerMesh, false);
      return hits.length ? hits[0] : null;
    }

    // For device drag-place tools: raycast outer cover + floor, pick first hit.
    let _floorRef = null;
    function _resolveFloor() {
      let f = null;
      ghGroup.traverse(function (o) { if (o.isMesh && o.name === 'facility_floor') f = o; });
      return f;
    }
    function _hitAnySurface(event) {
      if (!_outerMesh) _outerMesh = _resolveOuterMesh();
      if (!_floorRef)  _floorRef  = _resolveFloor();
      const targets = [_outerMesh, _floorRef].filter(Boolean);
      if (targets.length === 0) return null;
      const rect = canvas.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const hits = raycaster.intersectObjects(targets, false);
      return hits.length ? hits[0] : null;
    }

    function onCanvasMouseMove(event) {
      if (!_toolMode) return;
      const hit = _isDeviceDrag() ? _hitAnySurface(event) : _hitOuter(event);
      if (!hit) { _hlMesh.visible = false; _updateChip(null); return; }
      const hitObj = hit.object || _outerMesh;
      const n = hit.face.normal.clone().transformDirection(hitObj.matrixWorld).normalize();
      const isFloor = hitObj.name === 'facility_floor';
      const face = isFloor ? 'floor' : _faceFromNormal(n);
      const def = TOOL_DEFAULTS[_toolMode] || TOOL_DEFAULTS.window;

      // Preview at the SAME location that placement would use:
      //   device on any surface → exact click point
      //   wall window/door → wall geometric center (snap)
      //   roof → hit X/Y (arch slope), Z snapped to center (length/2)
      let cp;
      if (_isDeviceDrag() || face === 'floor') {
        cp = hit.point.clone();
      } else if (face === 'roof') {
        cp = new THREE.Vector3(hit.point.x, hit.point.y, length / 2);
      } else {
        let cy;
        if (_toolMode === 'door') cy = def.h / 2;
        else                      cy = Math.max(eaveH / 2, def.h / 2);
        switch (face) {
          case 'south': cp = new THREE.Vector3(totalWidth / 2, cy, 0);          break;
          case 'north': cp = new THREE.Vector3(totalWidth / 2, cy, length);     break;
          case 'east':  cp = new THREE.Vector3(totalWidth,     cy, length / 2); break;
          case 'west':  cp = new THREE.Vector3(0,              cy, length / 2); break;
          default:      cp = hit.point.clone();
        }
      }

      _hlMesh.scale.set(def.w * 1.1, def.h * 1.1, 1);
      _hlMesh.position.copy(cp).addScaledVector(n, 0.02);
      const hq = _quatFromNormal([n.x, n.y, n.z], 0);
      if (hq) _hlMesh.quaternion.copy(hq);
      else    _hlMesh.lookAt(cp.clone().add(n));
      _hlMesh.visible = true;
      _updateChip(_FACE_LABELS[face] || (isFloor ? '바닥' : face));
    }
    canvas.addEventListener('mousemove', onCanvasMouseMove);

    function onCanvasClick(event) {
      if (event.button!==0 || _dragged) return;

      // Tool-active path: raycast appropriate surface(s) → spawn a fitting.
      //   wall-pick (window/door/side_window) → outer cover. Wall fittings snap
      //     to wall geometric center; roof fittings snap X/Y to click, Z to center.
      //   device-drag (heater/fan/sensor/fixture) → outer cover + floor. Always
      //     uses the click point. Floor hits keep the box upright (no normal).
      // For face-pick fittings rotation_deg=0 — basis-from-normal gives the
      // natural orientation; spin would tilt the box.
      if (_toolMode) {
        const isDevice = _isDeviceDrag();
        const hit = isDevice ? _hitAnySurface(event) : _hitOuter(event);
        if (!hit) return;
        const hitObj = hit.object || _outerMesh;
        const n = hit.face.normal.clone().transformDirection(hitObj.matrixWorld).normalize();
        const isFloor = hitObj.name === 'facility_floor';
        const face = isFloor ? 'floor' : _faceFromNormal(n);

        // Wall-only fittings: block roof
        if (!isDevice && face === 'roof' && (_toolMode === 'door' || _toolMode === 'side_window')) return;

        const def = TOOL_DEFAULTS[_toolMode] || TOOL_DEFAULTS.window;
        let centerPos;
        let surfaceNormal = [n.x, n.y, n.z];

        if (isDevice) {
          // Drag-place at exact hit point. Floor hits: lift box by h/2 and use
          // null surface_normal so the device stays upright.
          centerPos = { x: hit.point.x, y: hit.point.y, z: hit.point.z };
          if (isFloor) {
            centerPos.y = def.h / 2;
            surfaceNormal = null;
          }
        } else if (face === 'roof') {
          // Snap Z to greenhouse center so skylights are placed mid-length by default.
          centerPos = { x: hit.point.x, y: hit.point.y, z: length / 2 };
        } else {
          let cy;
          if (_toolMode === 'door') cy = def.h / 2;
          else                      cy = Math.max(eaveH / 2, def.h / 2);
          switch (face) {
            case 'south': centerPos = { x: totalWidth / 2, y: cy, z: 0 };               break;
            case 'north': centerPos = { x: totalWidth / 2, y: cy, z: length };          break;
            case 'east':  centerPos = { x: totalWidth,     y: cy, z: length / 2 };      break;
            case 'west':  centerPos = { x: 0,              y: cy, z: length / 2 };      break;
            default:      centerPos = { x: hit.point.x, y: hit.point.y, z: hit.point.z };
          }
        }

        document.dispatchEvent(new CustomEvent('aot-facility-add-fitting', {
          detail: {
            kind: _toolMode,
            position: centerPos,
            rotation_deg: 0,
            surface_normal: surfaceNormal,
            size: def,
            face: _FACE_LABELS[face] || (isFloor ? '바닥' : face),
            face_raw: face,            // for FittingsUI to know geometry context
            is_device: isDevice,       // skip symmetry replication for devices
            facility_dims: {
              totalWidth: totalWidth,
              length: length,
              span: span,
              effectiveSpacing: effectiveSpacing,
              bayCount: bayCount,
              structure: facility.structure || 'single'
            }
          }
        }));
        return;
      }

      const rect = canvas.getBoundingClientRect();
      mouse.x=((event.clientX-rect.left)/rect.width)*2-1;
      mouse.y=-((event.clientY-rect.top)/rect.height)*2+1;
      raycaster.setFromCamera(mouse, camera);
      const hits = raycaster.intersectObjects(clickTargets.map(t=>t.mesh).filter(Boolean), true);
      if (!hits.length) return;
      const hit = hits[0].object;
      const target = clickTargets.find(t=>t.mesh===hit||(t.group&&t.group.children.includes(hit)));
      if (!target) return;
      // Fittings: dispatch selection event to FittingsUI form, skip tooltip
      if (target.fittingId) {
        document.dispatchEvent(new CustomEvent('aot-fitting-clicked', { detail: { id: target.fittingId } }));
        return;
      }
      const state = actStates[target.slot]||{};
      if (tooltip) tooltip.remove();
      tooltip = document.createElement('div');
      tooltip.style.cssText='position:fixed;z-index:9999;background:#1e2a35;color:#fff;padding:0.5rem 0.75rem;border-radius:8px;font-size:0.82rem;pointer-events:none;max-width:220px;box-shadow:0 4px 12px rgba(0,0,0,0.4)';
      tooltip.innerHTML='<b>'+_slotLabel(target.slot)+'</b><br>'+(state.name?'장치: '+state.name+'<br>':'')+'상태: '+(state.on?'<span style="color:#4fc3f7">ON</span>':'<span style="color:#9e9e9e">OFF</span>')+(state.percent!=null?' / '+state.percent+'%':'')+'<br><small style="color:#888">'+target.slot+'</small>';
      tooltip.style.left=(event.clientX+12)+'px'; tooltip.style.top=(event.clientY-8)+'px';
      document.body.appendChild(tooltip);
      setTimeout(()=>{ if(tooltip){tooltip.remove();tooltip=null;} },3500);
    }
    canvas.addEventListener('click', onCanvasClick);

    let animId;
    function animate() { animId=requestAnimationFrame(animate); controls.update(); renderer.render(scene,camera); }
    animate();

    function dispose() {
      cancelAnimationFrame(animId); resizeObs.disconnect(); controls.dispose();
      canvas.removeEventListener('click', onCanvasClick);
      canvas.removeEventListener('mousemove', onCanvasMouseMove);
      if (tooltip) tooltip.remove();
      if (_toolChip && _toolChip.parentElement) _toolChip.parentElement.removeChild(_toolChip);
      if (vcEl.parentElement) vcEl.parentElement.removeChild(vcEl);
      if (window.MeshBVHLib) {
        clickTargets.forEach(t=>{ if(t.mesh&&t.mesh.geometry&&t.mesh.geometry.boundsTree){try{t.mesh.geometry.disposeBoundsTree();}catch(e){}} });
      }
      renderer.dispose();
    }

    // In-place selection highlight update — avoids full scene rebuild on click.
    function updateFittingSelection(selectedId) {
      ghGroup.traverse(function (obj) {
        if (!obj || !obj.name) return;
        if (obj.name.indexOf('fitting:') !== 0) return;
        if (!obj.material) return;
        var id = obj.name.slice('fitting:'.length);
        var isSel = (id === selectedId);
        obj.material.opacity = isSel ? 0.85 : 0.55;
        if (obj.material.emissive) obj.material.emissive.setHex(isSel ? 0x1976d2 : 0x000000);
        obj.material.emissiveIntensity = isSel ? 0.35 : 0;
        obj.material.needsUpdate = true;
      });
    }

    function _findFittingPair(id) {
      var mesh = null, edges = null;
      ghGroup.traverse(function (obj) {
        if (obj.name === 'fitting:' + id) mesh = obj;
        else if (obj.name === 'edges:fitting:' + id) edges = obj;
      });
      return { mesh: mesh, edges: edges };
    }

    // In-place position/rotation update for a fitting — no rebuild.
    // If the mesh was created with a surface_normal, we preserve the normal-based
    // orientation and apply rotation_deg as spin around the normal.
    function updateFittingTransform(id, position, rotation_deg) {
      var p = _findFittingPair(id);
      if (!p.mesh) return;
      if (position) {
        p.mesh.position.set(position.x || 0, position.y || 0, position.z || 0);
        if (p.edges) p.edges.position.copy(p.mesh.position);
      }
      if (rotation_deg != null) {
        var sn = p.mesh.userData && p.mesh.userData.surface_normal;
        var deg = rotation_deg || 0;
        var q = (sn && Array.isArray(sn) && sn.length === 3) ? _quatFromNormal(sn, deg) : null;
        if (q) {
          p.mesh.quaternion.copy(q);
          if (p.edges) p.edges.quaternion.copy(q);
        } else {
          p.mesh.rotation.set(0, deg * Math.PI / 180, 0);
          if (p.edges) p.edges.rotation.set(0, deg * Math.PI / 180, 0);
        }
      }
    }

    // In-place geometry replacement (box size change) — no rebuild.
    function updateFittingGeometry(id, size) {
      var p = _findFittingPair(id);
      if (!p.mesh || !size) return;
      var w = Math.max(parseFloat(size.w) || 0.1, 0.02);
      var h = Math.max(parseFloat(size.h) || 0.1, 0.02);
      var d = Math.max(parseFloat(size.d) || 0.1, 0.02);
      if (p.mesh.geometry) p.mesh.geometry.dispose();
      p.mesh.geometry = new THREE.BoxGeometry(w, h, d);
      if (p.edges) {
        if (p.edges.geometry) p.edges.geometry.dispose();
        p.edges.geometry = new THREE.EdgesGeometry(p.mesh.geometry);
      }
    }

    // In-place add for a single fitting — no scene rebuild.
    function addFittingMesh(f) {
      _addFittingToScene(f);
    }

    // In-place remove — find mesh + edges by name, dispose, drop click target.
    function removeFittingMesh(id) {
      if (!id) return;
      var meshName = 'fitting:' + id;
      var edgeName = 'edges:fitting:' + id;
      var toRemove = [];
      ghGroup.traverse(function (o) {
        if (o.name === meshName || o.name === edgeName) toRemove.push(o);
      });
      toRemove.forEach(function (o) {
        if (o.geometry) o.geometry.dispose();
        if (o.material && o.material.dispose) o.material.dispose();
        ghGroup.remove(o);
      });
      for (var i = clickTargets.length - 1; i >= 0; i--) {
        if (clickTargets[i].fittingId === id) clickTargets.splice(i, 1);
      }
    }

    return {
      renderer, scene, camera, controls, dispose, setTool,
      updateFittingSelection, updateFittingTransform, updateFittingGeometry,
      addFittingMesh, removeFittingMesh
    };
  }

  // ── buildFacilityMesh (map-layer usage, backward-compat) ────────────────────
  function buildFacilityMesh(facility) {
    if (P) return P.buildFacilityMeshGroup(facility, MAT);

    const g3d=facility.geometry_3d||{}, envelope=facility.envelope||{};
    const span=parseFloat(g3d.span_width_m)||7, eaveH=parseFloat(g3d.eave_height_m)||2;
    const ridgeH=parseFloat(g3d.ridge_height_m)||4, length=parseFloat(g3d.length_m)||30;
    const roofType=String(g3d.roof_type||'arch').toLowerCase();
    const orientDeg=parseFloat(g3d.orientation_deg)||0;
    const rawBayCount=Math.max(parseInt(facility.bay_count||1,10),1);
    const isConnected=facility.structure==='connected';
    const unitCount=isConnected?1:rawBayCount, meshBayCount=isConnected?rawBayCount:1;
    const isDouble=(envelope.layer_count||1)===2;
    const effectiveSpacing=isConnected?0:(parseFloat(g3d.spacing_m)||1);
    const unitWidth=meshBayCount*span+(meshBayCount-1)*effectiveSpacing;
    const totalWidth=unitCount*unitWidth+(unitCount-1)*effectiveSpacing;
    const outerEnvSpec=envelope.outer||{}, innerEnvSpec=envelope.inner||{};
    const outerCoverMat=outerEnvSpec.cover_material||'vinyl_double';
    const innerCoverMat=innerEnvSpec.cover_material||'non_woven_fabric';

    const group=new THREE.Group(); group.name='facility_mesh_'+(facility.unique_id||'unknown');
    const es={steps:1,depth:length,bevelEnabled:false};
    const outerShape=_buildMultiSpanShape(span,eaveH,ridgeH,roofType,meshBayCount,effectiveSpacing);
    const outerGeo=new THREE.ExtrudeGeometry(outerShape,es);
    let innerGeo;
    if (isDouble) {
      const inset=0.15;
      const innerShape=_buildMultiSpanShape(span-inset*2,eaveH-inset*0.5,ridgeH-inset,roofType,meshBayCount,effectiveSpacing);
      innerGeo=new THREE.ExtrudeGeometry(innerShape,{steps:1,depth:length-inset*2,bevelEnabled:false});
    }
    for (let u=0; u<unitCount; u++) {
      const xOffset=u*(unitWidth+effectiveSpacing);
      const om=new THREE.Mesh(outerGeo,MAT.cover(outerCoverMat)); om.name='outer_cover_'+u; om.position.x=xOffset; group.add(om);
      const ed=new THREE.LineSegments(new THREE.EdgesGeometry(outerGeo),new THREE.LineBasicMaterial({color:0x455a64})); ed.position.x=xOffset; group.add(ed);
      if (isDouble&&innerGeo) { const inset=0.15; const im=new THREE.Mesh(innerGeo,MAT.coverInner(innerCoverMat)); im.position.set(xOffset+inset,0,inset); im.name='inner_cover_'+u; group.add(im); }
    }
    if (isConnected) {
      const gm=new THREE.MeshStandardMaterial({color:0x607d8b,roughness:0.5,metalness:0.5});
      for (let b=1;b<meshBayCount;b++) {
        [length*0.25,length*0.75].forEach(z=>{ const c=new THREE.Mesh(new THREE.BoxGeometry(0.05,eaveH,0.05),gm); c.position.set(b*span,eaveH/2,z); group.add(c); });
      }
    }
    group.userData={cx:totalWidth/2,cz:length/2,orientDeg,totalWidth,length};
    return group;
  }

  global.AoTFacility3D = { buildScene, buildFacilityMesh };
})(window);
