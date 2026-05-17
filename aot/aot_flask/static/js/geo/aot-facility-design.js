// aot-facility-design.js — Facility Design page (PRD/DESIGN-GEO-FACILITY-001)

// ── EnvelopeUI ────────────────────────────────────────────────────────────────
// Manages cover layers, vent stages, and curtain config for the Envelope section.
(function () {
  'use strict';

  var COVERS_OUTER = [
    { v: 'vinyl_single', l: 'vinyl_single' },
    { v: 'vinyl_double', l: 'vinyl_double' },
    { v: 'po_film',      l: 'po_film' },
    { v: 'polycarbonate', l: 'polycarbonate' },
    { v: 'glass',        l: 'glass' }
  ];
  var COVERS_INNER = [
    { v: 'vinyl_single',     l: 'vinyl_single' },
    { v: 'non_woven_fabric', l: 'non_woven_fabric' },
    { v: 'pe_film',          l: 'pe_film' },
    { v: 'polycarbonate',    l: 'polycarbonate' },
    { v: 'air_cushion',      l: 'air_cushion' }
  ];

  var _layers = [
    { id: 'outer', type: 'full', role: 'outer', cover: 'vinyl_double' }
  ];

  function _sel(opts, selected) {
    return opts.map(function (o) {
      return '<option value="' + o.v + '"' + (o.v === selected ? ' selected' : '') + '>' + o.l + '</option>';
    }).join('');
  }

  function _uid() {
    return 'L' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
  }

  function _notify() {
    document.dispatchEvent(new CustomEvent('envelope-changed'));
  }

  // ── Layer card renderer ────────────────────────────────────
  function _renderLayers() {
    var container = document.getElementById('envelope-layers-list');
    if (!container) return;
    container.innerHTML = '';

    _layers.forEach(function (layer) {
      var card = document.createElement('div');
      card.className = 'env-layer-card';
      card.setAttribute('data-layer-id', layer.id);
      card.style.cssText = 'border:1px solid #e8e8e8;border-radius:10px;padding:0.55rem 0.75rem;margin-bottom:0.4rem;';

      if (layer.type === 'full') {
        var covers = layer.role === 'outer' ? COVERS_OUTER : COVERS_INNER;
        var label  = layer.role === 'outer' ? '외피 (전체)' : '내피 (전체)';
        var icon   = layer.role === 'outer' ? '🏠' : '🪟';
        var airgapHtml = (layer.role === 'inner')
          ? '<span style="font-size:0.8rem;color:#888;white-space:nowrap;margin-left:4px;">에어갭&nbsp;' +
            '<input type="number" class="env-layer-airgap fac-input" data-layer-id="' + layer.id + '" ' +
            'value="' + (layer.air_gap_m != null ? layer.air_gap_m : 0.5) + '" step="0.1" min="0.1" ' +
            'style="width:58px;height:28px;display:inline-block;">&nbsp;m</span>'
          : '';
        var removeBtn = (layer.role !== 'outer')
          ? '<button class="btn btn-sm btn-outline-danger" style="margin-left:auto;padding:0 8px;height:28px;font-size:0.8rem;" ' +
            'onclick="EnvelopeUI.removeLayer(\'' + layer.id + '\')">✕</button>'
          : '';
        card.innerHTML =
          '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">' +
          '<span style="font-weight:700;font-size:0.85rem;flex:0 0 auto;">' + icon + ' ' + label + '</span>' +
          '<select class="fac-select env-layer-cover" data-layer-id="' + layer.id + '" ' +
          'style="flex:1;max-width:180px;height:30px;font-size:0.82rem;">' +
          _sel(covers, layer.cover) + '</select>' +
          airgapHtml + removeBtn + '</div>';

      } else if (layer.type === 'side_only') {
        var sideLabels = { north: '북', south: '남', east: '동', west: '서' };
        var sidesHtml = ['north', 'south', 'east', 'west'].map(function (s) {
          var checked = (layer.sides || []).indexOf(s) >= 0 ? ' checked' : '';
          return '<label style="font-size:0.82rem;cursor:pointer;display:flex;align-items:center;gap:3px;">' +
            '<input type="checkbox" class="env-layer-side" data-layer-id="' + layer.id + '" value="' + s + '"' + checked + '>' +
            sideLabels[s] + '</label>';
        }).join('');
        card.innerHTML =
          '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">' +
          '<span style="font-weight:700;font-size:0.85rem;flex:0 0 auto;">🧱 측벽 보강</span>' +
          '<select class="fac-select env-layer-cover" data-layer-id="' + layer.id + '" ' +
          'style="width:140px;height:30px;font-size:0.82rem;">' + _sel(COVERS_OUTER, layer.cover) + '</select>' +
          '<div style="display:flex;gap:6px;align-items:center;">' + sidesHtml + '</div>' +
          '<span style="font-size:0.8rem;color:#888;white-space:nowrap;">두께&nbsp;' +
          '<input type="number" class="env-layer-thickness fac-input" data-layer-id="' + layer.id + '" ' +
          'value="' + (layer.thickness_m || 1.0) + '" step="0.1" min="0.1" style="width:52px;height:28px;display:inline-block;">&nbsp;m</span>' +
          '<span style="font-size:0.8rem;color:#888;white-space:nowrap;">높이&nbsp;' +
          '<input type="number" class="env-layer-height fac-input" data-layer-id="' + layer.id + '" ' +
          'value="' + (layer.height_m || 2.0) + '" step="0.1" min="0.1" style="width:52px;height:28px;display:inline-block;">&nbsp;m</span>' +
          '<button class="btn btn-sm btn-outline-danger" style="margin-left:auto;padding:0 8px;height:28px;font-size:0.8rem;" ' +
          'onclick="EnvelopeUI.removeLayer(\'' + layer.id + '\')">✕</button></div>';
      }
      container.appendChild(card);
    });

    var hasInner = _layers.some(function (l) { return l.role === 'inner'; });
    var addInnerBtn = document.getElementById('btn-add-inner-layer');
    if (addInnerBtn) {
      addInnerBtn.disabled = hasInner;
      addInnerBtn.style.opacity = hasInner ? '0.4' : '';
    }
  }

  // ── Vent stage renderer ────────────────────────────────────
  function _renderVentStages(existingStages) {
    var stageCount = parseInt(
      ((document.querySelector('input[name="vent-stages"]:checked') || {}).value || '1'), 10);
    var container = document.getElementById('vent-stage-rows');
    if (!container) return;
    if (stageCount < 2) { container.innerHTML = ''; return; }

    var prev = [];
    container.querySelectorAll('.vent-stage-row').forEach(function (r, i) {
      prev[i] = {
        height_m:    parseFloat((r.querySelector('.vent-stage-height') || {}).value) || 1.2,
        from_floor_m: parseFloat((r.querySelector('.vent-stage-floor') || {}).value) || (i === 0 ? 0.3 : 1.6)
      };
    });
    var src = existingStages || prev;
    var defaults = [{ height_m: 1.2, from_floor_m: 0.3 }, { height_m: 1.2, from_floor_m: 1.6 }];
    var names = ['하단 (lower)', '상단 (upper)'];
    container.innerHTML = '';
    for (var i = 0; i < stageCount; i++) {
      var v = src[i] || defaults[i];
      var row = document.createElement('div');
      row.className = 'fac-row vent-stage-row';
      row.style.cssText = 'padding-left:0.5rem;border-bottom:none;';
      row.innerHTML =
        '<div class="fac-label" style="font-size:0.82rem;font-weight:500;color:#555;">' + names[i] + '</div>' +
        '<div style="display:flex;gap:6px;align-items:center;font-size:0.82rem;color:#888;">' +
        '높이&nbsp;<input type="number" class="fac-input vent-stage-height" value="' + v.height_m +
        '" step="0.1" min="0.1" style="width:58px;height:28px;display:inline-block;">&nbsp;m' +
        '&nbsp;&nbsp;시작&nbsp;<input type="number" class="fac-input vent-stage-floor" value="' + v.from_floor_m +
        '" step="0.1" min="0" style="width:58px;height:28px;display:inline-block;">&nbsp;m</div>';
      container.appendChild(row);
    }
  }

  // ── Public API ─────────────────────────────────────────────
  function addSideOnlyLayer() {
    _layers.push({ id: _uid(), type: 'side_only', role: 'reinforcement',
      cover: 'pe_film', sides: ['east', 'west'], thickness_m: 1.0, height_m: 2.0 });
    _renderLayers();
    _notify();
  }

  function addInnerLayer() {
    if (_layers.some(function (l) { return l.role === 'inner'; })) return;
    _layers.push({ id: _uid(), type: 'full', role: 'inner',
      cover: 'non_woven_fabric', air_gap_m: 0.5 });
    _renderLayers();
    _notify();
  }

  function removeLayer(id) {
    _layers = _layers.filter(function (l) { return l.id !== id; });
    _renderLayers();
    _notify();
  }

  function onVentToggle() {
    var enabled = !!((document.getElementById('outer-side-vent') || {}).checked);
    var detail = document.getElementById('outer-side-vent-detail');
    if (detail) detail.style.display = enabled ? '' : 'none';
    _notify();
  }

  function onCurtainCeilingToggle() {
    var enabled = !!((document.getElementById('curtain-thermal-ceiling') || {}).checked);
    var detail = document.getElementById('curtain-ceiling-detail');
    if (detail) detail.style.display = enabled ? '' : 'none';
    _notify();
  }

  function onCurtainWallToggle() {
    var enabled = !!((document.getElementById('curtain-thermal-wall') || {}).checked);
    var detail = document.getElementById('curtain-wall-detail');
    if (detail) detail.style.display = enabled ? '' : 'none';
    _notify();
  }

  // ── Read UI → envelope object ──────────────────────────────
  function read() {
    _layers = _layers.map(function (layer) {
      var coverEl = document.querySelector('.env-layer-cover[data-layer-id="' + layer.id + '"]');
      if (coverEl) layer.cover = coverEl.value;
      if (layer.type === 'full' && layer.role === 'inner') {
        var agEl = document.querySelector('.env-layer-airgap[data-layer-id="' + layer.id + '"]');
        if (agEl) layer.air_gap_m = parseFloat(agEl.value) || 0.5;
      }
      if (layer.type === 'side_only') {
        layer.sides = [];
        document.querySelectorAll('.env-layer-side[data-layer-id="' + layer.id + '"]:checked')
          .forEach(function (el) { layer.sides.push(el.value); });
        var tEl = document.querySelector('.env-layer-thickness[data-layer-id="' + layer.id + '"]');
        var hEl = document.querySelector('.env-layer-height[data-layer-id="' + layer.id + '"]');
        if (tEl) layer.thickness_m = parseFloat(tEl.value) || 1.0;
        if (hEl) layer.height_m    = parseFloat(hEl.value) || 2.0;
      }
      return layer;
    });

    var ventEnabled = !!((document.getElementById('outer-side-vent') || {}).checked);
    var stageCount  = parseInt(
      ((document.querySelector('input[name="vent-stages"]:checked') || {}).value || '1'), 10);
    var ventStages = [];
    var stageIds = ['lower', 'upper'];
    document.querySelectorAll('.vent-stage-row').forEach(function (row, i) {
      ventStages.push({
        id: stageIds[i] || ('stage' + i),
        height_m:    parseFloat((row.querySelector('.vent-stage-height') || {}).value) || 1.2,
        from_floor_m: parseFloat((row.querySelector('.vent-stage-floor') || {}).value) || 0.3
      });
    });
    if (ventStages.length === 0) ventStages = [{ id: 'lower', height_m: 1.2, from_floor_m: 0.3 }];

    var roofEnabled  = !!((document.getElementById('outer-roof-vent') || {}).checked);
    var ceilEnabled  = !!((document.getElementById('curtain-thermal-ceiling') || {}).checked);
    var ceilLayers   = parseInt(
      ((document.querySelector('input[name="curtain-ceiling-layers"]:checked') || {}).value || '1'), 10);
    var wallEnabled  = !!((document.getElementById('curtain-thermal-wall') || {}).checked);
    var wallSides    = [];
    document.querySelectorAll('.curtain-wall-side:checked').forEach(function (el) { wallSides.push(el.value); });
    var shadeEnabled = !!((document.getElementById('curtain-shade') || {}).checked);

    return {
      layers: JSON.parse(JSON.stringify(_layers)),
      side_vent: { outer: { enabled: ventEnabled, stages: ventStages } },
      roof_vent: { outer: { enabled: roofEnabled } },
      curtain: {
        thermal_ceiling: { enabled: ceilEnabled, layers: ceilLayers },
        thermal_wall:    { enabled: wallEnabled, sides: wallSides },
        shade:           { enabled: shadeEnabled }
      }
    };
  }

  // ── Fill UI from envelope object (old or new format) ──────
  function fill(env) {
    if (!env) return;
    if (env.layer_count != null && !env.layers) env = _migrate(env);

    _layers = (Array.isArray(env.layers) && env.layers.length > 0)
      ? JSON.parse(JSON.stringify(env.layers))
      : [{ id: 'outer', type: 'full', role: 'outer', cover: 'vinyl_double' }];
    _renderLayers();

    // side vent
    var sv = (env.side_vent && env.side_vent.outer) || {};
    var ventEl = document.getElementById('outer-side-vent');
    if (ventEl) ventEl.checked = !!sv.enabled;
    var ventDetail = document.getElementById('outer-side-vent-detail');
    if (ventDetail) ventDetail.style.display = sv.enabled ? '' : 'none';

    var stages = sv.stages || [];
    var stageCount = Math.max(stages.length, 1);
    var stageRadio = document.querySelector('input[name="vent-stages"][value="' + stageCount + '"]');
    if (stageRadio) {
      stageRadio.checked = true;
      document.querySelectorAll('input[name="vent-stages"]').forEach(function (r) {
        var lbl = r.parentElement;
        if (lbl) { if (r.checked) lbl.classList.add('active'); else lbl.classList.remove('active'); }
      });
    }
    _renderVentStages(stages);

    // roof vent
    var rv = (env.roof_vent && env.roof_vent.outer) || {};
    var roofEl = document.getElementById('outer-roof-vent');
    if (roofEl) roofEl.checked = !!rv.enabled;

    // curtain
    var curtain = env.curtain || {};
    var tc = curtain.thermal_ceiling || {};
    var tw = curtain.thermal_wall    || {};
    var sh = curtain.shade           || {};

    var ceilEl = document.getElementById('curtain-thermal-ceiling');
    if (ceilEl) ceilEl.checked = !!tc.enabled;
    var ceilDetail = document.getElementById('curtain-ceiling-detail');
    if (ceilDetail) ceilDetail.style.display = tc.enabled ? '' : 'none';
    var ceilR = document.querySelector('input[name="curtain-ceiling-layers"][value="' + (tc.layers || 1) + '"]');
    if (ceilR) ceilR.checked = true;

    var wallEl = document.getElementById('curtain-thermal-wall');
    if (wallEl) wallEl.checked = !!tw.enabled;
    var wallDetail = document.getElementById('curtain-wall-detail');
    if (wallDetail) wallDetail.style.display = tw.enabled ? '' : 'none';
    var wallSides = tw.sides || [];
    document.querySelectorAll('.curtain-wall-side').forEach(function (el) {
      el.checked = wallSides.indexOf(el.value) >= 0;
    });

    var shadeEl = document.getElementById('curtain-shade');
    if (shadeEl) shadeEl.checked = !!sh.enabled;
  }

  // ── Migrate old flat envelope → new layers format ─────────
  function _migrate(old) {
    var layers = [{ id: 'outer', type: 'full', role: 'outer',
      cover: (old.outer && old.outer.cover_material) || 'vinyl_double' }];
    if ((old.layer_count || 1) >= 2 && old.inner) {
      layers.push({ id: 'inner', type: 'full', role: 'inner',
        cover: old.inner.cover_material || 'non_woven_fabric',
        air_gap_m: old.inner.air_gap_m || 0.5 });
    }
    var oSV = (old.outer && old.outer.side_vent) || {};
    var oRV = (old.outer && old.outer.roof_vent) || {};
    var oc  = old.curtain || {};
    return {
      layers: layers,
      side_vent: { outer: { enabled: !!oSV.enabled,
        stages: [{ id: 'lower', height_m: 1.2, from_floor_m: 0.3 }] } },
      roof_vent: { outer: { enabled: !!oRV.enabled } },
      curtain: {
        thermal_ceiling: { enabled: !!oc.thermal, layers: 1 },
        thermal_wall:    { enabled: false, sides: [] },
        shade:           { enabled: !!oc.shade }
      }
    };
  }

  // ── Init (called from DOMContentLoaded) ───────────────────
  function init() {
    _renderLayers();
    _renderVentStages();

    document.querySelectorAll('input[name="vent-stages"]').forEach(function (r) {
      r.addEventListener('change', function () {
        document.querySelectorAll('input[name="vent-stages"]').forEach(function (rr) {
          var lbl = rr.parentElement;
          if (lbl) { if (rr.checked) lbl.classList.add('active'); else lbl.classList.remove('active'); }
        });
        _renderVentStages();
        // Stage count/height does not change 3D geometry — emit lightweight event
        // so compute runs but the WebGL scene is NOT disposed and rebuilt.
        document.dispatchEvent(new CustomEvent('envelope-data-changed'));
      });
    });

    // Delegate events for dynamically created layer inputs
    document.addEventListener('change', function (e) {
      if (!e.target) return;
      if (e.target.classList.contains('env-layer-cover') ||
          e.target.classList.contains('env-layer-side')  ||
          e.target.classList.contains('curtain-wall-side') ||
          e.target.name === 'curtain-ceiling-layers') {
        _notify();
      }
    });
    document.addEventListener('input', function (e) {
      if (!e.target) return;
      if (e.target.classList.contains('env-layer-airgap')    ||
          e.target.classList.contains('env-layer-thickness')  ||
          e.target.classList.contains('env-layer-height')) {
        _notify();
      }
      if (e.target.classList.contains('vent-stage-height')    ||
          e.target.classList.contains('vent-stage-floor')) {
        document.dispatchEvent(new CustomEvent('envelope-data-changed'));
      }
    });
  }

  window.EnvelopeUI = {
    addSideOnlyLayer: addSideOnlyLayer,
    addInnerLayer:    addInnerLayer,
    removeLayer:      removeLayer,
    onVentToggle:     onVentToggle,
    onCurtainCeilingToggle: onCurtainCeilingToggle,
    onCurtainWallToggle:    onCurtainWallToggle,
    read: read,
    fill: fill,
    init: init
  };
})();

// ── ActuatorUI ────────────────────────────────────────────────────────────────
// Manages actuator instances: kind, device mapping, mount position, specs.
(function () {
  'use strict';

  var _instances = [];   // array of actuator objects
  var _devices   = [];   // available output devices from /api/geo/devices

  var KIND_META = {
    side_window_motor:    { label: '측창 모터',    icon: '🪟', specs: ['stroke_m','speed_m_per_min'],       mount: ['north','south','east','west'], useStage: true },
    roof_vent_motor:      { label: '지붕창 모터',  icon: '🔲', specs: ['stroke_m','speed_m_per_min'],       mount: ['north','south','east','west','roof'] },
    thermal_curtain_motor:{ label: '보온커튼 모터',icon: '🪢', specs: ['speed_m_per_min','coverage_pct'],   mount: ['ceiling','north','south','east','west'], useStage: true },
    shade_curtain_motor:  { label: '차광커튼 모터',icon: '🪢', specs: ['speed_m_per_min','coverage_pct'],   mount: ['ceiling'] },
    exhaust_fan:          { label: '환기팬',       icon: '💨', specs: ['airflow_cmh','power_w'],            mount: ['north','south','east','west','roof'], useElevation: true },
    circulation_fan:      { label: '순환팬',       icon: '🌀', specs: ['airflow_cmh','power_w'],            mount: ['north','south','east','west','roof','ceiling'], useElevation: true },
    heater:               { label: '히터',         icon: '🔥', specs: ['capacity_kw','fuel'],               mount: [] },
    cooler:               { label: '냉각기',       icon: '❄️', specs: ['capacity_kw','power_w'],            mount: [] },
    heat_pump:            { label: '히트펌프',     icon: '⚡', specs: ['capacity_kw','power_w'],            mount: [] },
    irrigation_valve:     { label: '관개밸브',     icon: '💧', specs: ['flow_lph','pressure_kpa'],          mount: [] }
  };

  var SPEC_META = {
    stroke_m:         { label: '행정', unit: 'm',      type: 'number', step: 0.1, min: 0.1 },
    speed_m_per_min:  { label: '속도', unit: 'm/min',  type: 'number', step: 0.1, min: 0.1 },
    coverage_pct:     { label: '커버율', unit: '%',    type: 'number', step: 1,   min: 0, max: 100 },
    airflow_cmh:      { label: '풍량', unit: '㎥/h',   type: 'number', step: 100, min: 0 },
    power_w:          { label: '전력', unit: 'W',      type: 'number', step: 10,  min: 0 },
    capacity_kw:      { label: '용량', unit: 'kW',     type: 'number', step: 0.1, min: 0 },
    fuel:             { label: '연료', unit: '',       type: 'select', options: ['gas','oil','electric','biomass'] },
    flow_lph:         { label: '유량', unit: 'L/h',    type: 'number', step: 10,  min: 0 },
    pressure_kpa:     { label: '압력', unit: 'kPa',    type: 'number', step: 1,   min: 0 }
  };

  var WALL_LABELS = { north:'북', south:'남', east:'동', west:'서', roof:'지붕', ceiling:'천정' };
  var STAGE_OPTIONS = ['lower','upper','single'];

  function _uid() {
    return 'A' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
  }

  function _notify() {
    document.dispatchEvent(new CustomEvent('actuator-changed'));
  }

  // ── Device <select> options html ──────────────────────────
  function _deviceOptions(selectedUuid) {
    var html = '<option value="">— 미연결 —</option>';
    _devices.forEach(function (d) {
      var sel = d.unique_id === selectedUuid ? ' selected' : '';
      html += '<option value="' + d.unique_id + '"' + sel + '>' +
        (d.name || d.unique_id) + ' (' + (d.type || '') + ')</option>';
    });
    return html;
  }

  // ── Render a single actuator card ─────────────────────────
  function _cardHtml(act) {
    var meta = KIND_META[act.kind] || { label: act.kind, icon: '⚙️', specs: [], mount: [] };
    var id   = act.id;

    // Device row
    var html = '<div class="act-card" data-act-id="' + id + '" ' +
      'style="border:1px solid #e8e8e8;border-radius:10px;padding:0.55rem 0.75rem;margin-bottom:0.4rem;">';

    // Header: icon + label + remove
    html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:0.35rem;">' +
      '<span style="font-size:1rem;">' + meta.icon + '</span>' +
      '<span style="font-weight:700;font-size:0.85rem;flex:1;">' + meta.label + '</span>' +
      '<button class="btn btn-sm btn-outline-danger" style="padding:0 7px;height:26px;font-size:0.78rem;" ' +
      'onclick="ActuatorUI.remove(\'' + id + '\')">✕</button></div>';

    // Row 1: device selector
    html += '<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:0.3rem;">' +
      '<span style="font-size:0.78rem;color:#888;white-space:nowrap;">장치:</span>' +
      '<select class="fac-select act-device" data-act-id="' + id + '" ' +
      'style="flex:1;min-width:160px;height:28px;font-size:0.8rem;">' +
      _deviceOptions(act.device_uuid) + '</select></div>';

    // Row 2: mount (wall) + elevation
    if (meta.mount && meta.mount.length > 0) {
      var mountSel = '<select class="fac-select act-mount-wall" data-act-id="' + id + '" ' +
        'style="width:90px;height:28px;font-size:0.8rem;">';
      meta.mount.forEach(function (w) {
        mountSel += '<option value="' + w + '"' + (w === (act.mount && act.mount.wall) ? ' selected' : '') + '>' +
          (WALL_LABELS[w] || w) + '</option>';
      });
      mountSel += '</select>';

      var elevHtml = '';
      if (meta.useElevation) {
        var elev = (act.mount && act.mount.elevation_m != null) ? act.mount.elevation_m : '';
        elevHtml = '<span style="font-size:0.78rem;color:#888;white-space:nowrap;margin-left:4px;">높이&nbsp;' +
          '<input type="number" class="fac-input act-mount-elev" data-act-id="' + id + '" ' +
          'value="' + elev + '" step="0.1" min="0" style="width:55px;height:28px;display:inline-block;">&nbsp;m</span>';
      }

      var stageHtml = '';
      if (meta.useStage) {
        var stageSel = '<select class="fac-select act-stage-ref" data-act-id="' + id + '" ' +
          'style="width:80px;height:28px;font-size:0.8rem;">' +
          '<option value="">—</option>';
        STAGE_OPTIONS.forEach(function (s) {
          stageSel += '<option value="' + s + '"' + (s === act.stage_ref ? ' selected' : '') + '>' + s + '</option>';
        });
        stageSel += '</select>';
        stageHtml = '<span style="font-size:0.78rem;color:#888;margin-left:4px;">단:&nbsp;</span>' + stageSel;
      }

      html += '<div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;margin-bottom:0.3rem;">' +
        '<span style="font-size:0.78rem;color:#888;">위치:</span>' + mountSel + elevHtml + stageHtml + '</div>';
    }

    // Row 3: specs
    if (meta.specs && meta.specs.length > 0) {
      html += '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">' +
        '<span style="font-size:0.78rem;color:#888;">성능:</span>';
      meta.specs.forEach(function (sk) {
        var sm = SPEC_META[sk];
        if (!sm) return;
        var val = (act.specs && act.specs[sk] != null) ? act.specs[sk] : '';
        if (sm.type === 'select') {
          var optHtml = sm.options.map(function (o) {
            return '<option value="' + o + '"' + (o === val ? ' selected' : '') + '>' + o + '</option>';
          }).join('');
          html += '<span style="font-size:0.78rem;color:#888;white-space:nowrap;">' + sm.label + ':&nbsp;' +
            '<select class="fac-select act-spec" data-act-id="' + id + '" data-spec-key="' + sk + '" ' +
            'style="width:90px;height:26px;font-size:0.78rem;">' + optHtml + '</select></span>';
        } else {
          html += '<span style="font-size:0.78rem;color:#888;white-space:nowrap;">' + sm.label + ':&nbsp;' +
            '<input type="number" class="fac-input act-spec" data-act-id="' + id + '" data-spec-key="' + sk + '" ' +
            'value="' + val + '" step="' + sm.step + '" min="' + (sm.min || 0) + '" ' +
            (sm.max != null ? 'max="' + sm.max + '" ' : '') +
            'style="width:68px;height:26px;display:inline-block;">&nbsp;' + sm.unit + '</span>';
        }
      });
      html += '</div>';
    }

    html += '</div>';
    return html;
  }

  // ── Re-render all cards ───────────────────────────────────
  function _render() {
    var container = document.getElementById('actuator-list');
    if (!container) return;
    if (_instances.length === 0) {
      container.innerHTML = '<div style="color:#aaa;font-size:0.82rem;padding:0.4rem 0;">액추에이터가 없습니다. 아래에서 추가하세요.</div>';
      return;
    }
    container.innerHTML = _instances.map(_cardHtml).join('');
  }

  // ── Public API ─────────────────────────────────────────────
  function add(kind) {
    var meta = KIND_META[kind] || {};
    var defaultMount = (meta.mount && meta.mount[0]) || null;
    _instances.push({
      id: _uid(), kind: kind, device_uuid: null,
      stage_ref: null,
      mount: defaultMount ? { wall: defaultMount } : {},
      specs: {}
    });
    _render();
    _notify();
  }

  function remove(id) {
    _instances = _instances.filter(function (a) { return a.id !== id; });
    _render();
    _notify();
  }

  function setDevices(devices) {
    _devices = devices || [];
    _render();
  }

  // Sync DOM → _instances, then return copy
  function read() {
    _instances = _instances.map(function (act) {
      var devEl  = document.querySelector('.act-device[data-act-id="' + act.id + '"]');
      var wallEl = document.querySelector('.act-mount-wall[data-act-id="' + act.id + '"]');
      var elevEl = document.querySelector('.act-mount-elev[data-act-id="' + act.id + '"]');
      var stgEl  = document.querySelector('.act-stage-ref[data-act-id="' + act.id + '"]');
      if (devEl)  act.device_uuid = devEl.value || null;
      if (wallEl) act.mount = act.mount || {};
      if (wallEl) act.mount.wall = wallEl.value || null;
      if (elevEl && elevEl.value !== '') act.mount.elevation_m = parseFloat(elevEl.value);
      if (stgEl)  act.stage_ref = stgEl.value || null;
      act.specs = act.specs || {};
      document.querySelectorAll('.act-spec[data-act-id="' + act.id + '"]').forEach(function (el) {
        var sk = el.dataset.specKey;
        if (!sk) return;
        var sm = SPEC_META[sk];
        if (sm && sm.type === 'select') {
          act.specs[sk] = el.value || null;
        } else {
          act.specs[sk] = el.value !== '' ? parseFloat(el.value) : null;
        }
      });
      return act;
    });
    return JSON.parse(JSON.stringify(_instances));
  }

  function fill(actuators) {
    if (!actuators) return;
    // Handle old dict format {key: device_uuid}
    if (!Array.isArray(actuators)) {
      _instances = [];
      Object.entries(actuators).forEach(function (entry) {
        var key = entry[0], uuid = entry[1];
        if (!uuid) return;
        var kind = key; // keep old key as kind (best-effort)
        _instances.push({ id: _uid(), kind: kind, device_uuid: uuid, stage_ref: null, mount: {}, specs: {} });
      });
    } else {
      _instances = JSON.parse(JSON.stringify(actuators));
      // Ensure each has id
      _instances.forEach(function (a) { if (!a.id) a.id = _uid(); });
    }
    _render();
  }

  function init() {
    _render();
    // Delegate change/input events for dynamically created actuator inputs
    document.addEventListener('change', function (e) {
      if (!e.target) return;
      if (e.target.classList.contains('act-device')     ||
          e.target.classList.contains('act-mount-wall') ||
          e.target.classList.contains('act-stage-ref')  ||
          (e.target.classList.contains('act-spec') && e.target.tagName === 'SELECT')) {
        _notify();
      }
    });
    document.addEventListener('input', function (e) {
      if (!e.target) return;
      if (e.target.classList.contains('act-mount-elev') ||
          (e.target.classList.contains('act-spec') && e.target.type === 'number')) {
        _notify();
      }
    });
  }

  // Lightweight accessor for FittingsUI's actuator dropdown.
  // Returns a shallow snapshot of {id, kind, name(label or kind+#)}.
  function getAll() {
    return _instances.map(function (a, i) {
      var meta = KIND_META[a.kind] || {};
      var label = (a.name && a.name.trim()) || ((meta.label || a.kind) + ' #' + (i + 1));
      return { id: a.id, kind: a.kind, label: label, icon: meta.icon || '⚙️' };
    });
  }

  window.ActuatorUI = {
    add: add, remove: remove,
    setDevices: setDevices,
    getAll: getAll,
    read: read, fill: fill, init: init
  };
})();

// ── FittingsUI ────────────────────────────────────────────────────────────────
// Manages user-placed fittings (windows, doors, fixtures, sensors, ad-hoc devices)
// rendered as boxes in the 3D scene. Position/size are absolute (m) from facility origin.
(function () {
  'use strict';

  var KIND_META = {
    window:      { label: '창호',     icon: '🪟', color: '#9ecfef', defaults: { w: 1.2, h: 1.0, d: 0.05 } },
    door:        { label: '출입문',   icon: '🚪', color: '#a1887f', defaults: { w: 1.0, h: 2.0, d: 0.05 } },
    side_window: { label: '측창',     icon: '🪟', color: '#bbdefb', defaults: { w: 3.0, h: 0.8, d: 0.05 } },
    curtain:     { label: '커튼',     icon: '🪢', color: '#f5e6c8', defaults: { w: 3.0, h: 2.5, d: 0.02 } },
    fan:         { label: '팬',       icon: '💨', color: '#90caf9', defaults: { w: 0.8, h: 0.8, d: 0.3  } },
    heater:      { label: '히터',     icon: '🔥', color: '#ef9a9a', defaults: { w: 0.6, h: 0.6, d: 0.4  } },
    sensor:      { label: '센서',     icon: '🔬', color: '#ce93d8', defaults: { w: 0.15, h: 0.15, d: 0.1 } },
    fixture:     { label: '설비',     icon: '⚙️', color: '#c5e1a5', defaults: { w: 1.0, h: 1.0, d: 1.0  } }
  };

  var _fittings    = [];
  var _selectedId  = null;

  // Caches of global Input/Output devices for fitting binding.
  // Sensors bind to Inputs (measurement source), all other fittings bind to
  // Outputs (relay/motor/PWM physical actuator). Fetched once on init.
  var InputCache  = { list: [], loaded: false };
  var OutputCache = { list: [], loaded: false };

  function _loadInputs(force) {
    if (InputCache.loaded && !force) return Promise.resolve(InputCache.list);
    return fetch('/api/geo/inputs', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : { ok: false }; })
      .then(function (j) {
        InputCache.list   = (j && j.ok && Array.isArray(j.inputs)) ? j.inputs : [];
        InputCache.loaded = true;
        return InputCache.list;
      })
      .catch(function () { InputCache.list = []; InputCache.loaded = true; return []; });
  }

  function _loadOutputs(force) {
    if (OutputCache.loaded && !force) return Promise.resolve(OutputCache.list);
    return fetch('/api/geo/outputs', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : { ok: false }; })
      .then(function (j) {
        OutputCache.list   = (j && j.ok && Array.isArray(j.outputs)) ? j.outputs : [];
        OutputCache.loaded = true;
        return OutputCache.list;
      })
      .catch(function () { OutputCache.list = []; OutputCache.loaded = true; return []; });
  }

  function _uid() {
    return 'F' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
  }

  function _notify() {
    document.dispatchEvent(new CustomEvent('fittings-changed'));
  }

  // ── List rendering — right-side panel inside 3D viewport ───────────────────
  function _renderList() {
    var container = document.getElementById('fit-list-items');
    var counter   = document.getElementById('fit-list-count');
    if (counter) counter.textContent = '(' + _fittings.length + ')';
    if (!container) return;
    if (_fittings.length === 0) {
      container.innerHTML = '<div class="fit-list-empty">아직 추가된 fitting이 없습니다.</div>';
      return;
    }
    // Look up Output & Input device labels once so each row can show its binding badge.
    var outMap = {};
    (OutputCache.list || []).forEach(function (o) { outMap[o.unique_id] = o; });
    var inpMap = {};
    (InputCache.list || []).forEach(function (i) { inpMap[i.unique_id] = i; });

    container.innerHTML = _fittings.map(function (f) {
      var meta = KIND_META[f.kind] || KIND_META.fixture;
      var isSel = (f.id === _selectedId);
      var label = f.name || (meta.label + ' #' + (_fittings.indexOf(f) + 1));
      var badge = '';
      if (f.kind === 'sensor') {
        var inp = f.input_id && inpMap[f.input_id];
        if (inp) {
          badge = '<span title="' + (inp.name || 'Input') + '" style="margin-left:auto;font-size:0.7rem;color:#6a1b9a;background:#f3e5f5;padding:0 5px;border-radius:8px;white-space:nowrap;">📡</span>';
        }
      } else {
        var out = f.actuator_id && outMap[f.actuator_id];
        if (out) {
          badge = '<span title="' + (out.name || 'Output') + '" style="margin-left:auto;font-size:0.7rem;color:#1565c0;background:#e3f2fd;padding:0 5px;border-radius:8px;white-space:nowrap;">🔌</span>';
        }
      }
      return '<div class="fit-list-item' + (isSel ? ' selected' : '') + '" ' +
        'data-fit-id="' + f.id + '" onclick="FittingsUI.select(\'' + f.id + '\')">' +
        '<span>' + meta.icon + '</span>' +
        '<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;">' + label + '</span>' +
        badge + '</div>';
    }).join('');
  }

  // ── Inspector rendering — bottom strip showing selected fitting's props ────
  function _renderInspector() {
    var empty   = document.getElementById('fi-empty');
    var content = document.getElementById('fi-content');
    if (!empty || !content) return;
    var f = _fittings.find(function (x) { return x.id === _selectedId; });
    if (!f) {
      empty.style.display = '';
      content.style.display = 'none';
      return;
    }
    empty.style.display = 'none';
    content.style.display = '';

    var meta = KIND_META[f.kind] || KIND_META.fixture;
    var iconEl = document.getElementById('fi-icon');
    if (iconEl) iconEl.textContent = meta.icon;

    // Populate inputs (programmatic — must not retrigger 'input' loop)
    var setVal = function (id, v) {
      var el = document.getElementById(id);
      if (!el) return;
      if (el.value !== String(v)) el.value = v;
    };
    setVal('fi-name', f.name || '');
    var kindEl = document.getElementById('fi-kind');
    if (kindEl) kindEl.value = f.kind;
    setVal('fi-x', f.position.x != null ? f.position.x : 0);
    setVal('fi-y', f.position.y != null ? f.position.y : 0);
    setVal('fi-z', f.position.z != null ? f.position.z : 0);
    setVal('fi-w', f.size.w != null ? f.size.w : 1);
    setVal('fi-h', f.size.h != null ? f.size.h : 1);
    setVal('fi-d', f.size.d != null ? f.size.d : 0.1);
    setVal('fi-rot', f.rotation_deg || 0);

    // Sensors bind to an Input (measurement source), other fittings bind to an
    // Actuator (output device). Toggle the two dropdown groups accordingly.
    var actGroup = document.getElementById('fi-group-actuator');
    var inpGroup = document.getElementById('fi-group-input');
    var isSensor = (f.kind === 'sensor');
    if (actGroup) actGroup.style.display = isSensor ? 'none' : '';
    if (inpGroup) inpGroup.style.display = isSensor ? '' : 'none';

    if (!isSensor) {
      // Populate actuator dropdown from the global Output device list.
      var actSel = document.getElementById('fi-actuator');
      if (actSel) {
        var outList = OutputCache.list || [];
        var aOpts;
        if (outList.length === 0) {
          aOpts = ['<option value="">— 등록된 Output 없음 (Setup → Output 페이지에서 추가) —</option>'];
        } else {
          aOpts = ['<option value="">— 없음 —</option>'];
          outList.forEach(function (out) {
            var sel = (f.actuator_id === out.unique_id) ? ' selected' : '';
            var label = (out.name || 'Output') + (out.output_type ? ' (' + out.output_type + ')' : '');
            aOpts.push('<option value="' + out.unique_id + '"' + sel + '>🔌 ' + label + '</option>');
          });
        }
        actSel.innerHTML = aOpts.join('');
        actSel.value = f.actuator_id || '';
      }
    } else {
      // Populate input dropdown from cached Input device list.
      var inpSel = document.getElementById('fi-input');
      if (inpSel) {
        var iOpts;
        if ((InputCache.list || []).length === 0) {
          iOpts = ['<option value="">— 등록된 Input 없음 (Setup → Input 페이지에서 추가) —</option>'];
        } else {
          iOpts = ['<option value="">— 없음 —</option>'];
          InputCache.list.forEach(function (inp) {
            var sel = (f.input_id === inp.unique_id) ? ' selected' : '';
            var label = (inp.name || 'Input') + (inp.device ? ' (' + inp.device + ')' : '');
            iOpts.push('<option value="' + inp.unique_id + '"' + sel + '>📡 ' + label + '</option>');
          });
        }
        inpSel.innerHTML = iOpts.join('');
        inpSel.value = f.input_id || '';
      }
    }
  }

  function _render() {
    _renderList();
    _renderInspector();
  }

  // Read the current facility dimensions from the form (best-effort fallback).
  function _facilityDims() {
    var span    = parseFloat((document.getElementById('span-width')   || {}).value) || 7;
    var length  = parseFloat((document.getElementById('length-m')     || {}).value) || 30;
    var eaveH   = parseFloat((document.getElementById('eave-height')  || {}).value) || 2;
    var ridgeH  = parseFloat((document.getElementById('ridge-height') || {}).value) || 4;
    var bay     = parseInt(  (document.getElementById('bay-count')    || {}).value, 10) || 1;
    var spacing = parseFloat((document.getElementById('spacing-m')    || {}).value) || 0;
    var struct  = ((document.querySelector('input[name="structure"]:checked') || {}).value) || 'single';
    var totalWidth = (struct === 'connected')
      ? span * bay
      : span * bay + spacing * (bay - 1);
    return { span:span, length:length, eaveH:eaveH, ridgeH:ridgeH, bayCount:bay, totalWidth:totalWidth };
  }

  // Sensible default position per kind, so a freshly-added fitting is visible
  // in the centre of the facility (not buried at the corner).
  function _defaultPlacement(kind) {
    var d = _facilityDims();
    var cx = d.totalWidth / 2, cz = d.length / 2;
    switch (kind) {
      case 'curtain':  // ceiling-mounted, lies horizontal under the eaves
        return { position: { x: cx, y: d.eaveH + 0.05, z: cz }, surface_normal: [0, 1, 0] };
      case 'fan':
        return { position: { x: cx, y: d.eaveH * 0.7, z: cz }, surface_normal: null };
      case 'heater':
        return { position: { x: Math.max(cx - 1, 0.5), y: 0.4, z: cz - 1 }, surface_normal: null };
      case 'sensor':
        return { position: { x: cx, y: d.eaveH * 0.6, z: cz }, surface_normal: null };
      case 'fixture':
        return { position: { x: cx, y: d.eaveH * 0.7, z: cz }, surface_normal: null };
      default:
        return { position: { x: cx, y: d.eaveH / 2, z: cz }, surface_normal: null };
    }
  }

  function add(kind) {
    var meta  = KIND_META[kind] || KIND_META.fixture;
    var place = _defaultPlacement(kind);
    var id    = _uid();
    var f = {
      id: id, kind: kind, name: '',
      position: place.position,
      size:     { w: meta.defaults.w, h: meta.defaults.h, d: meta.defaults.d },
      rotation_deg: 0,
      surface_normal: place.surface_normal,
      // Sensors bind to an Input (measurement source); other kinds bind to an
      // Actuator. Both fields exist on every fitting but only one is meaningful
      // per kind — kept side-by-side for spec stability across kind changes.
      actuator_id: null,
      input_id: null
    };
    _fittings.push(f);
    _selectedId = id;
    _render();
    // Delta event so the 3D scene can add ONE mesh without a full rebuild.
    document.dispatchEvent(new CustomEvent('fitting-added',
      { detail: { fitting: JSON.parse(JSON.stringify(f)) } }));
    _notify();
    return id;
  }

  // Programmatic fitting creation — used by face-click placement from 3D scene.
  // pos: {x,y,z} in facility-local meters · rot: degrees around Y
  // size?: {w,h,d} (default = KIND_META.defaults) · faceLabel?: prepended to name
  // surface_normal?: [nx,ny,nz] — face normal in world space, used to orient
  //                   the box flush with curved/sloped surfaces (e.g. arch roof).
  // link_group?: string — fittings sharing a group sync size/rotation/kind/name.
  function addAt(kind, pos, rot, size, faceLabel, surface_normal, link_group, replica_info) {
    var meta = KIND_META[kind] || KIND_META.fixture;
    var sz = size || meta.defaults;
    var id = _uid();
    var posY = pos.y || 0;
    // If placing on the ground (no normal, very low y), lift to half-height so
    // the box sits on the floor instead of half-buried.
    if (!surface_normal && posY < 0.1) {
      posY = (sz.h || meta.defaults.h) / 2;
    }
    var f = {
      id: id,
      kind: kind,
      name: faceLabel ? (faceLabel + ' ' + meta.label) : '',
      position: { x: pos.x || 0, y: posY, z: pos.z || 0 },
      size:     { w: sz.w || meta.defaults.w, h: sz.h || meta.defaults.h, d: sz.d || meta.defaults.d },
      rotation_deg: rot || 0,
      surface_normal: (surface_normal && surface_normal.length === 3) ? surface_normal : null,
      link_group: link_group || null,
      actuator_id: null,   // user assigns via inspector — same actuator can drive many fittings
      input_id: null,      // sensor fittings: bound Input device (measurement source)
      replica_info: replica_info || null   // metadata for position-propagation within link_group
    };
    _fittings.push(f);
    _selectedId = id;  // auto-select newly placed fitting
    _render();
    document.dispatchEvent(new CustomEvent('fitting-added',
      { detail: { fitting: JSON.parse(JSON.stringify(f)) } }));
    _notify();
    return id;
  }

  // Generate symmetric/multi-bay replicas for a face-click placement.
  // Each item carries a replica_info describing its transformation relative to
  // a shared "master local frame", so position edits can later be propagated
  // across the group with the correct mirror/bay offset.
  function _generateReplicas(face_raw, position, surface_normal, dims) {
    var out = [];
    var sn = surface_normal || [0, 0, 1];
    if (!dims) {
      return [{ position: position, surface_normal: sn,
                replica_info: { face: face_raw || 'unknown' } }];
    }
    var sp = (dims.span || 7) + (dims.effectiveSpacing || 0);
    var bayCount = Math.max(parseInt(dims.bayCount, 10) || 1, 1);
    var totalWidth = dims.totalWidth || ((dims.span || 7) * bayCount);
    var length = dims.length || 30;
    var span = dims.span || 7;

    if (face_raw === 'roof') {
      var bay_idx = Math.floor(position.x / sp);
      if (bay_idx < 0) bay_idx = 0;
      if (bay_idx >= bayCount) bay_idx = bayCount - 1;
      var local_x = position.x - bay_idx * sp;
      var mirror_local_x = span - local_x;
      // Only skip mirror when click is EXACTLY at ridge (floating-point equality).
      // A 5 cm threshold caused mirrors to be suppressed when users click on the
      // flat-looking arch top near the ridge, which is the typical skylight zone.
      var isRidge = Math.abs(mirror_local_x - local_x) < 0.001;
      for (var b = 0; b < bayCount; b++) {
        out.push({
          position: { x: b * sp + local_x, y: position.y, z: position.z },
          surface_normal: [sn[0], sn[1], sn[2]],
          replica_info: { face: 'roof', bay: b, x_mirror: false }
        });
        if (!isRidge) {
          out.push({
            position: { x: b * sp + mirror_local_x, y: position.y, z: position.z },
            surface_normal: [-sn[0], sn[1], sn[2]],
            replica_info: { face: 'roof', bay: b, x_mirror: true }
          });
        }
      }
    } else if (face_raw === 'east' || face_raw === 'west') {
      out.push({ position: position, surface_normal: sn,
                 replica_info: { face: face_raw, x_mirror_wall: false } });
      if (Math.abs(position.x - totalWidth / 2) > 0.05) {
        out.push({
          position: { x: totalWidth - position.x, y: position.y, z: position.z },
          surface_normal: [-sn[0], sn[1], sn[2]],
          replica_info: { face: face_raw, x_mirror_wall: true }
        });
      }
    } else if (face_raw === 'south' || face_raw === 'north') {
      out.push({ position: position, surface_normal: sn,
                 replica_info: { face: face_raw, z_mirror_wall: false } });
      if (Math.abs(position.z - length / 2) > 0.05) {
        out.push({
          position: { x: position.x, y: position.y, z: length - position.z },
          surface_normal: [sn[0], sn[1], -sn[2]],
          replica_info: { face: face_raw, z_mirror_wall: true }
        });
      }
    } else {
      out.push({ position: position, surface_normal: sn,
                 replica_info: { face: face_raw || 'unknown' } });
    }
    return out;
  }

  // Propagate shared properties (size, rotation, kind, name) to all members
  // of a linked group when one member is edited. Position is NOT propagated —
  // each replica keeps its own (mirrored / per-bay) position.
  function _syncGroup(sourceId) {
    var src = _fittings.find(function (f) { return f.id === sourceId; });
    if (!src || !src.link_group) return;
    var groupId = src.link_group;
    var changed = false;
    _fittings.forEach(function (f) {
      if (f.id === sourceId || f.link_group !== groupId) return;
      f.kind = src.kind;
      f.name = src.name;
      f.size = { w: src.size.w, h: src.size.h, d: src.size.d };
      f.rotation_deg = src.rotation_deg;
      changed = true;
    });
    return changed;
  }

  function remove(id) {
    _fittings = _fittings.filter(function (f) { return f.id !== id; });
    if (_selectedId === id) _selectedId = null;
    _render();
    document.dispatchEvent(new CustomEvent('fitting-removed', { detail: { id: id } }));
    _notify();
  }

  function select(id) {
    _selectedId = (_selectedId === id) ? null : id;
    _render();
    // Scroll the right-side list (not the page) so the selected item is visible.
    if (_selectedId) {
      var item = document.querySelector('.fit-list-item[data-fit-id="' + _selectedId + '"]');
      var listPanel = document.getElementById('facility-3d-fittings-list');
      if (item && listPanel) {
        var itemRect = item.getBoundingClientRect();
        var panelRect = listPanel.getBoundingClientRect();
        if (itemRect.top < panelRect.top || itemRect.bottom > panelRect.bottom) {
          listPanel.scrollTop += (itemRect.top - panelRect.top) - 20;
        }
      }
    }
    document.dispatchEvent(new CustomEvent('fitting-selection-changed', { detail: { id: _selectedId } }));
  }

  function getSelectedId() { return _selectedId; }

  function read() {
    _fittings = _fittings.map(function (f) {
      var nm = document.querySelector('.fit-name[data-fit-id="' + f.id + '"]');
      if (nm) f.name = nm.value || '';
      ['x','y','z'].forEach(function (ax) {
        var el = document.querySelector('.fit-pos[data-fit-id="' + f.id + '"][data-axis="' + ax + '"]');
        if (el && el.value !== '') f.position[ax] = parseFloat(el.value);
      });
      ['w','h','d'].forEach(function (ax) {
        var el = document.querySelector('.fit-size[data-fit-id="' + f.id + '"][data-axis="' + ax + '"]');
        if (el && el.value !== '') f.size[ax] = parseFloat(el.value);
      });
      var rot = document.querySelector('.fit-rot[data-fit-id="' + f.id + '"]');
      if (rot && rot.value !== '') f.rotation_deg = parseFloat(rot.value) || 0;
      return f;
    });
    return JSON.parse(JSON.stringify(_fittings));
  }

  function fill(fittings) {
    _fittings = Array.isArray(fittings)
      ? JSON.parse(JSON.stringify(fittings))
      : [];
    _fittings.forEach(function (f) {
      if (!f.id) f.id = _uid();
      f.position = f.position || { x: 0, y: 0, z: 0 };
      f.size     = f.size     || { w: 1, h: 1, d: 0.1 };
      if (f.rotation_deg == null) f.rotation_deg = 0;
    });
    _selectedId = null;
    _render();
  }

  // ── Inspector input wiring — bidirectional binding with selected fitting ───
  function _bindInspectorInputs() {
    function _getSel() { return _fittings.find(function (x) { return x.id === _selectedId; }); }

    function _onTransform() {
      var f = _getSel(); if (!f) return;
      f.position.x = parseFloat((document.getElementById('fi-x') || {}).value) || 0;
      f.position.y = parseFloat((document.getElementById('fi-y') || {}).value) || 0;
      f.position.z = parseFloat((document.getElementById('fi-z') || {}).value) || 0;
      f.rotation_deg = parseFloat((document.getElementById('fi-rot') || {}).value) || 0;

      var dirty = [{ id: f.id, position: f.position, rotation_deg: f.rotation_deg }];

      // Propagate to other group members using replica_info (per-bay + mirror).
      // Rotation always copies; position is reflected/translated based on each
      // replica's transformation relative to a shared local frame.
      if (f.link_group) {
        var others = _fittings.filter(function (g) {
          return g.link_group === f.link_group && g.id !== f.id;
        });
        if (others.length > 0) {
          var dims = _facilityDims();
          var sp = dims.span + 0;  // connected mode default; spacing handled below if set
          var span = dims.span;
          var totalW = dims.totalWidth;
          var length = dims.length;
          var fInfo = f.replica_info || {};

          // Recover the master-local position implied by THIS fitting's new pos.
          // (Whichever fitting the user edits acts as the new reference.)
          var masterLocalX = f.position.x;
          if (fInfo.face === 'roof') {
            var fBay = fInfo.bay != null ? fInfo.bay : Math.floor(f.position.x / sp);
            var fLocalX = f.position.x - fBay * sp;
            masterLocalX = fInfo.x_mirror ? (span - fLocalX) : fLocalX;
          } else if (fInfo.x_mirror_wall) {
            masterLocalX = totalW - f.position.x;
          }
          var masterZ = fInfo.z_mirror_wall ? (length - f.position.z) : f.position.z;

          others.forEach(function (g) {
            var gInfo = g.replica_info || {};
            // Always propagate rotation
            g.rotation_deg = f.rotation_deg;
            // Position propagation requires compatible face
            if (gInfo.face === 'roof' && fInfo.face === 'roof') {
              var gLocalX = gInfo.x_mirror ? (span - masterLocalX) : masterLocalX;
              g.position = {
                x: (gInfo.bay || 0) * sp + gLocalX,
                y: f.position.y,
                z: f.position.z
              };
            } else if ((gInfo.face === 'east' || gInfo.face === 'west') &&
                       (fInfo.face === 'east' || fInfo.face === 'west')) {
              g.position = {
                x: gInfo.x_mirror_wall ? (totalW - masterLocalX) : masterLocalX,
                y: f.position.y,
                z: f.position.z
              };
            } else if ((gInfo.face === 'south' || gInfo.face === 'north') &&
                       (fInfo.face === 'south' || fInfo.face === 'north')) {
              g.position = {
                x: f.position.x,
                y: f.position.y,
                z: gInfo.z_mirror_wall ? (length - masterZ) : masterZ
              };
            } else {
              // Unknown / legacy: keep position, only rotation propagates
            }
            dirty.push({ id: g.id, position: g.position, rotation_deg: g.rotation_deg });
          });
        }
      }

      // Emit one in-place transform event per dirty fitting (no scene rebuild)
      dirty.forEach(function (d) {
        document.dispatchEvent(new CustomEvent('aot-fitting-transform', { detail: d }));
      });
      document.dispatchEvent(new CustomEvent('fittings-data-changed'));
    }
    function _onSize() {
      var f = _getSel(); if (!f) return;
      f.size.w = Math.max(parseFloat((document.getElementById('fi-w') || {}).value) || 0.1, 0.02);
      f.size.h = Math.max(parseFloat((document.getElementById('fi-h') || {}).value) || 0.1, 0.02);
      f.size.d = Math.max(parseFloat((document.getElementById('fi-d') || {}).value) || 0.1, 0.02);
      // Sync size to linked group members + emit transform event for each.
      var syncIds = [f.id];
      if (f.link_group) {
        _syncGroup(f.id);
        _fittings.forEach(function (g) {
          if (g.link_group === f.link_group && g.id !== f.id) syncIds.push(g.id);
        });
      }
      syncIds.forEach(function (id) {
        document.dispatchEvent(new CustomEvent('aot-fitting-geometry', {
          detail: { id: id, size: f.size }
        }));
      });
      document.dispatchEvent(new CustomEvent('fittings-data-changed'));
    }
    function _onMeta() {
      var f = _getSel(); if (!f) return;
      f.name = (document.getElementById('fi-name') || {}).value || '';
      var newKind = (document.getElementById('fi-kind') || {}).value;
      var kindChanged = (newKind && newKind !== f.kind);
      f.kind = newKind || f.kind;
      if (f.link_group) _syncGroup(f.id);
      _renderList();           // list labels may have changed
      // Kind toggles sensor/non-sensor → actuator vs input dropdown swap.
      if (kindChanged) _renderInspector();
      if (kindChanged) {
        // Color/material depends on kind — recreate THIS mesh in-place (no full rebuild)
        document.dispatchEvent(new CustomEvent('fitting-removed', { detail: { id: f.id } }));
        document.dispatchEvent(new CustomEvent('fitting-added',
          { detail: { fitting: JSON.parse(JSON.stringify(f)) } }));
        // If linked group, also recreate every member's mesh
        if (f.link_group) {
          _fittings.forEach(function (g) {
            if (g.link_group === f.link_group && g.id !== f.id) {
              document.dispatchEvent(new CustomEvent('fitting-removed', { detail: { id: g.id } }));
              document.dispatchEvent(new CustomEvent('fitting-added',
                { detail: { fitting: JSON.parse(JSON.stringify(g)) } }));
            }
          });
        }
        document.dispatchEvent(new CustomEvent('fittings-data-changed'));
      } else {
        document.dispatchEvent(new CustomEvent('fittings-data-changed'));
      }
    }

    ['fi-x','fi-y','fi-z','fi-rot'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener('input', _onTransform);
    });
    ['fi-w','fi-h','fi-d'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener('input', _onSize);
    });
    var nm = document.getElementById('fi-name');
    if (nm) nm.addEventListener('input', _onMeta);
    var kd = document.getElementById('fi-kind');
    if (kd) kd.addEventListener('change', _onMeta);
    var del = document.getElementById('fi-delete');
    if (del) del.addEventListener('click', function () {
      if (_selectedId) remove(_selectedId);
    });

    // Actuator dropdown — per-fitting, NOT propagated to link_group
    // (replicas can be driven by different actuators).
    var actSel = document.getElementById('fi-actuator');
    if (actSel) actSel.addEventListener('change', function () {
      var f = _getSel(); if (!f) return;
      f.actuator_id = actSel.value || null;
      _renderList();
      document.dispatchEvent(new CustomEvent('fittings-data-changed'));
    });

    // Input dropdown — only meaningful for sensor fittings, same per-fitting rule.
    var inpSel = document.getElementById('fi-input');
    if (inpSel) inpSel.addEventListener('change', function () {
      var f = _getSel(); if (!f) return;
      f.input_id = inpSel.value || null;
      _renderList();
      document.dispatchEvent(new CustomEvent('fittings-data-changed'));
    });
  }

  function init() {
    _render();
    _bindInspectorInputs();

    // Fetch the Input & Output device lists once so the inspector dropdowns
    // are populated on first open. Re-render when each arrives in case a
    // fitting is already selected.
    _loadInputs().then(function () {
      if (_selectedId) _renderInspector();
      _renderList();
    });
    _loadOutputs().then(function () {
      if (_selectedId) _renderInspector();
      _renderList();
    });

    // External 3D click → select the matching item in the list
    document.addEventListener('aot-fitting-clicked', function (e) {
      var id = e.detail && e.detail.id;
      if (id) select(id);
    });

    // The fitting actuator dropdown now binds directly to the global Output
    // device list (not the facility-local ActuatorUI instances), so we no
    // longer need to refresh or prune anything when ActuatorUI changes.

    // External face-click placement from 3D scene → spawn fitting(s).
    // Wall/roof clicks: generate symmetric + per-bay replicas, all sharing one
    // link_group. Device drag-place: single fitting, no replication.
    document.addEventListener('aot-facility-add-fitting', function (e) {
      var d = e.detail; if (!d || !d.kind || !d.position) return;

      var replicas;
      if (d.is_device || !d.face_raw) {
        // Devices: single fitting at click point, no replication.
        replicas = [{ position: d.position, surface_normal: d.surface_normal }];
      } else {
        replicas = _generateReplicas(d.face_raw, d.position, d.surface_normal, d.facility_dims);
      }

      var groupId = (replicas.length > 1) ? _uid() : null;
      replicas.forEach(function (r) {
        addAt(d.kind, r.position, d.rotation_deg, d.size, d.face,
              r.surface_normal, groupId, r.replica_info);
      });
    });
  }

  // ── Catalog import: pull equipment features from geo/design ───────────────
  function _featureCentroid(geom) {
    if (!geom || !geom.coordinates) return null;
    var coords = [];
    function _walk(c) {
      if (!c) return;
      if (typeof c[0] === 'number') { coords.push(c); return; }
      c.forEach(_walk);
    }
    _walk(geom.coordinates);
    if (coords.length === 0) return null;
    var sx = 0, sy = 0;
    coords.forEach(function (p) { sx += p[0]; sy += p[1]; });
    return [sx / coords.length, sy / coords.length];
  }

  function _featureSizeM(geom, latC) {
    // Approximate bounding-box size in meters
    if (!geom || !geom.coordinates) return null;
    var coords = [];
    function _walk(c) {
      if (!c) return;
      if (typeof c[0] === 'number') { coords.push(c); return; }
      c.forEach(_walk);
    }
    _walk(geom.coordinates);
    if (coords.length < 2) return null;
    var minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    coords.forEach(function (p) {
      if (p[0] < minX) minX = p[0]; if (p[0] > maxX) maxX = p[0];
      if (p[1] < minY) minY = p[1]; if (p[1] > maxY) maxY = p[1];
    });
    var M_PER_DEG_LAT = 111320.0;
    var M_PER_DEG_LNG = M_PER_DEG_LAT * Math.cos((latC || 0) * Math.PI / 180);
    var w = (maxX - minX) * M_PER_DEG_LNG;
    var d = (maxY - minY) * M_PER_DEG_LAT;
    return { w: Math.max(w, 0.1), d: Math.max(d, 0.1) };
  }

  // Convert feature geometry → fitting position (facility-local meters)
  function _featureToFittingPos(feature, facCenter, facOrientDeg) {
    if (!feature || !feature.geometry || !facCenter) return { x: 0, y: 0, z: 0 };
    var fc = _featureCentroid(feature.geometry);
    if (!fc) return { x: 0, y: 0, z: 0 };
    var latC = facCenter[1];
    var M_PER_DEG_LAT = 111320.0;
    var M_PER_DEG_LNG = M_PER_DEG_LAT * Math.cos(latC * Math.PI / 180);
    var dx_m = (fc[0] - facCenter[0]) * M_PER_DEG_LNG;
    var dy_m = (fc[1] - facCenter[1]) * M_PER_DEG_LAT;
    // Inverse-rotate around facility origin to convert world meters → local
    var theta = -((facOrientDeg || 0) * Math.PI / 180);
    var cosT = Math.cos(theta), sinT = Math.sin(theta);
    var lx = dx_m * cosT - dy_m * sinT;
    var lz = dx_m * sinT + dy_m * cosT;
    return { x: lx, z: lz };
  }

  function _kindFromFeature(feature) {
    var p = (feature && feature.properties) || {};
    var k = String(p.kind || p.aot_kind || p.equipment_type || p.feature_type || '').toLowerCase();
    if (k.includes('side_window') || k.includes('측창')) return 'side_window';
    if (k.includes('window') || k.includes('vent') || k.includes('창')) return 'window';
    if (k.includes('door') || k.includes('출입')) return 'door';
    if (k.includes('curtain') || k.includes('커튼')) return 'curtain';
    if (k.includes('fan') || k.includes('팬'))    return 'fan';
    if (k.includes('heater') || k.includes('히터')) return 'heater';
    if (k.includes('sensor') || k.includes('센서')) return 'sensor';
    return 'fixture';
  }

  async function importFromCatalog(geoId, facCenter, facOrientDeg) {
    if (!geoId) { alert('지도를 먼저 선택하세요.'); return; }
    try {
      var res = await fetch('/api/geo/overlays?map_uuid=' + encodeURIComponent(geoId) +
                            '&type=equipment', { credentials: 'same-origin' });
      var json = await res.json();
      var features = (json && json.features) || [];
      if (features.length === 0) { alert('카탈로그에 설비가 없습니다.'); return; }
      _openCatalogPicker(features, facCenter, facOrientDeg);
    } catch (e) {
      alert('카탈로그 조회 실패: ' + e.message);
    }
  }

  function _openCatalogPicker(features, facCenter, facOrientDeg) {
    // Remove existing
    var prev = document.getElementById('fittings-catalog-modal');
    if (prev) prev.remove();

    var overlay = document.createElement('div');
    overlay.id = 'fittings-catalog-modal';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;';

    var modal = document.createElement('div');
    modal.style.cssText = 'background:#fff;border-radius:12px;padding:1rem;max-width:540px;max-height:80vh;overflow-y:auto;box-shadow:0 8px 24px rgba(0,0,0,0.25);';
    modal.innerHTML =
      '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.75rem;">' +
      '<h5 style="margin:0;">📦 geo/design 설비 카탈로그</h5>' +
      '<button class="btn btn-sm btn-outline-secondary" id="cat-close">✕</button></div>' +
      '<div class="fac-hint" style="margin-bottom:0.5rem;">현재 지도의 설비를 선택해 fitting으로 추가합니다.</div>' +
      '<div id="cat-list"></div>';

    var list = modal.querySelector ? null : null;
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    var listEl = modal.querySelector('#cat-list');
    features.forEach(function (feat) {
      var p = feat.properties || {};
      var name = p.name || p.label || ('Feature #' + (p.db_id || ''));
      var inferredKind = _kindFromFeature(feat);
      var size = _featureSizeM(feat.geometry, facCenter ? facCenter[1] : 37.5);
      var sizeStr = size ? (size.w.toFixed(1) + '×' + size.d.toFixed(1) + 'm') : '?';
      var h = parseFloat(p.height_m) || null;
      var el = parseFloat(p.elevation_m) || 0;

      var item = document.createElement('div');
      item.style.cssText = 'display:flex;align-items:center;gap:8px;padding:0.5rem 0.75rem;border:1px solid #e8e8e8;border-radius:8px;margin-bottom:0.4rem;cursor:pointer;';
      item.innerHTML =
        '<span style="flex:1;font-size:0.88rem;"><b>' + name + '</b>' +
        '<br><small style="color:#888;">' + inferredKind + ' · ' + sizeStr +
        (h ? ' · 높이 ' + h + 'm' : '') + '</small></span>' +
        '<button class="btn btn-sm btn-primary">가져오기</button>';
      item.addEventListener('click', function () {
        var pos = _featureToFittingPos(feat, facCenter, facOrientDeg);
        var sz = size || { w: 1, h: 1, d: 1 };
        var heightM = h || (KIND_META[inferredKind] || KIND_META.fixture).defaults.h;
        _fittings.push({
          id: _uid(),
          kind: inferredKind,
          name: name,
          position: { x: pos.x || 0, y: el + heightM / 2, z: pos.z || 0 },
          size:     { w: sz.w, h: heightM, d: sz.d },
          rotation_deg: 0,
          source_feature_uuid: p.node_id || p.unique_id || null
        });
        _render();
        _notify();
        overlay.remove();
      });
      listEl.appendChild(item);
    });

    modal.querySelector('#cat-close').addEventListener('click', function () { overlay.remove(); });
    overlay.addEventListener('click', function (e) { if (e.target === overlay) overlay.remove(); });
  }

  // Aggregate count + size summary by kind ──────────────────
  function aggregate() {
    var byKind = {};
    var totalArea = 0;
    _fittings.forEach(function (f) {
      var k = f.kind || 'fixture';
      if (!byKind[k]) byKind[k] = { count: 0, area_m2: 0, volume_m3: 0 };
      byKind[k].count += 1;
      var area = (f.size.w || 0) * (f.size.d || 0);
      byKind[k].area_m2 += area;
      byKind[k].volume_m3 += area * (f.size.h || 0);
    });
    return { total: _fittings.length, by_kind: byKind, total_area_m2: Object.values(byKind).reduce(function (s, v) { return s + v.area_m2; }, 0) };
  }

  window.FittingsUI = {
    add: add, addAt: addAt, remove: remove, select: select,
    getSelectedId: getSelectedId,
    importFromCatalog: importFromCatalog,
    aggregate: aggregate,
    read: read, fill: fill, init: init
  };
})();

// ── Main facility design logic ─────────────────────────────────────────────────
(function () {
  'use strict';

  const State = {
    map: null,
    outerGeometry: null,
    facilityUuid: null,
    availableOutputs: [],
    center: null,           // [lng, lat] — facility center on the map
    orientationDeg: 0,      // 0~359, rotation around center
    placeMode: false,       // true while waiting for a single click to set center
    sites: [],              // site features for the active map
    selectedSiteUuid: null, // GeoShape unique_id of the selected site
    _baseStyleLayerIds: []  // snapshot of base style layer IDs for layer panel
  };

  const SITE_SRC = 'map-sites';
  const SITE_LYR_FILL = 'map-sites-fill';
  const SITE_LYR_LINE = 'map-sites-line';

  // CARTO Voyager raster fallback (used when AOT_GEO_CONFIG has no usable layer)
  const FALLBACK_RASTER_STYLE = {
    version: 8,
    sources: {
      basemap: {
        type: 'raster',
        tiles: [
          'https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
          'https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
          'https://c.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
          'https://d.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png'
        ],
        tileSize: 256,
        maxzoom: 19,
        attribution: '© OpenStreetMap contributors © CARTO'
      }
    },
    layers: [{ id: 'basemap', type: 'raster', source: 'basemap' }]
  };

  /**
   * Resolve a MapLibre style spec from window.AOT_GEO_CONFIG (same source of truth
   * as /geo/design). Tries:
   *   1. config.layers[*]: first enabled raster (xyz/wms/tile)
   *   2. config.providers.osm or .raster URL pattern
   *   3. CARTO Voyager fallback (cached above)
   */
  function resolveBaseStyle() {
    const cfg = window.AOT_GEO_CONFIG || {};
    const layers = Array.isArray(cfg.layers) ? cfg.layers : [];

    // 1. First active raster layer (xyz/wms/tile)
    for (const L of layers) {
      if (L && L.enabled === false) continue;
      const t = String(L.type || '').toLowerCase();
      const opts = L.options || L;
      const url = opts.url || opts.tileUrl || opts.tiles || L.url;
      if (url && (t.includes('xyz') || t.includes('tile') || t.includes('raster') || t.includes('osm'))) {
        return rasterStyleFromUrl(Array.isArray(url) ? url : [url], opts.attribution || L.attribution);
      }
    }

    // 2. providers fallback
    const providers = cfg.providers || {};
    for (const key of ['osm', 'raster', 'base', 'default']) {
      const p = providers[key];
      const url = (p && (p.url || p.tileUrl)) || null;
      if (url) {
        return rasterStyleFromUrl([url], (p && p.attribution) || '');
      }
    }

    // 3. fallback
    console.warn('[facility] AOT_GEO_CONFIG has no usable raster layer; using CARTO Voyager fallback.');
    return FALLBACK_RASTER_STYLE;
  }

  function rasterStyleFromUrl(tiles, attribution) {
    return {
      version: 8,
      sources: {
        basemap: {
          type: 'raster',
          tiles: tiles,
          tileSize: 256,
          maxzoom: 19,
          attribution: attribution || ''
        }
      },
      layers: [{ id: 'basemap', type: 'raster', source: 'basemap' }]
    };
  }

  document.addEventListener('DOMContentLoaded', async function () {
    const vars = JSON.parse(document.getElementById('facility-page-vars').textContent);
    State.facilityUuid = vars.facility_uuid || null;

    if (window.EnvelopeUI)  EnvelopeUI.init();
    if (window.ActuatorUI)  ActuatorUI.init();
    if (window.FittingsUI)  FittingsUI.init();
    initMap();
    bindEventHandlers();
    await loadOutputs();

    if (State.facilityUuid) {
      await loadFacility(State.facilityUuid);
      loadIntegration(State.facilityUuid);
    }
    // After map style/sources ready, populate facility-prod + sites for the active map.
    State.map.on('load', () => {
      const sel = document.getElementById('map-selector');
      const initialGeoId = (sel && sel.value) || null;
      if (initialGeoId) {
        loadSavedFacilities(initialGeoId);
        loadSites(initialGeoId);
      }
    });
    debouncedCompute();
  });

  // =========================================================
  // Map
  // =========================================================
  function initMap() {
    const cfg = window.AOT_GEO_CONFIG || {};
    const initLat  = parseFloat(cfg.default_lat)  || 37.5665;
    const initLng  = parseFloat(cfg.default_lng)  || 126.9780;
    const initZoom = parseFloat(cfg.zoom)         || 13;

    State.map = new maplibregl.Map({
      container: 'facility-map-canvas',
      style: resolveBaseStyle(),
      center: [initLng, initLat],
      zoom: initZoom,
      maxZoom: 19,             // basemap tiles end at z=19
      pitch: 45,               // start in 3D camera so extrusion is visible
      bearing: 0,
      doubleClickZoom: false   // legacy; no-op since draw mode removed
    });
    State.map.addControl(
      new maplibregl.NavigationControl({ showCompass: true, visualizePitch: true }),
      'top-left'
    );

    State.map.on('load', async () => {
      try {
      // ============================================================
      // facility-prod: All saved facilities for this map (3D footprints)
      // ============================================================
      // Capture base style layer IDs BEFORE adding any facility/site layers so that
      // FacilityLayerPanel correctly identifies which layers belong to the base style.
      // If captured after, facility-prod layers are mistakenly treated as base layers
      // and are not restored after a base-map style switch — causing fill-extrusion
      // to re-appear as visible after the switch.
      State._baseStyleLayerIds = (State.map.getStyle().layers || []).map(l => l.id);

      State.map.addSource('facility-prod', { type: 'geojson', data: emptyFC() });
      State.map.addLayer({
        id: 'facility-prod-fill', type: 'fill', source: 'facility-prod',
        paint: { 'fill-color': '#82898f', 'fill-opacity': 0.15 }
      });
      State.map.addLayer({
        id: 'facility-prod-line', type: 'line', source: 'facility-prod',
        paint: { 'line-color': '#5c656b', 'line-width': 1.5 }
      });
      State.map.addLayer({
        id: 'facility-prod-3d', type: 'fill-extrusion', source: 'facility-prod',
        layout: { visibility: 'none' },   // hidden: Three.js overlay replaces this
        paint: {
          'fill-extrusion-color': '#82898f',
          'fill-extrusion-height': ['coalesce', ['get', 'height_m'], 4],
          'fill-extrusion-base':   ['coalesce', ['get', 'base_m'], 0],
          'fill-extrusion-opacity': 0.55
        }
      });

      // ============================================================
      // map-sites: Site shapes belonging to the active map (toggle layer)
      // ============================================================

      State.map.addSource(SITE_SRC, { type: 'geojson', data: emptyFC() });
      State.map.addLayer({
        id: SITE_LYR_FILL, type: 'fill', source: SITE_SRC,
        paint: { 'fill-color': '#f5a623', 'fill-opacity': 0.15 }
      });
      State.map.addLayer({
        id: SITE_LYR_LINE, type: 'line', source: SITE_SRC,
        paint: { 'line-color': '#e07b00', 'line-width': 2, 'line-dasharray': [2, 1] }
      });

      // ============================================================
      // facility-preview: Currently-edited facility (highlight color)
      // ============================================================
      State.map.addSource('facility-preview', { type: 'geojson', data: emptyFC() });
      State.map.addLayer({
        id: 'facility-preview-fill', type: 'fill', source: 'facility-preview',
        paint: { 'fill-color': '#3388ff', 'fill-opacity': 0.18 }
      });
      State.map.addLayer({
        id: 'facility-preview-line', type: 'line', source: 'facility-preview',
        paint: { 'line-color': '#1565c0', 'line-width': 2.5 }
      });
      State.map.addLayer({
        id: 'facility-preview-3d', type: 'fill-extrusion', source: 'facility-preview',
        layout: { visibility: 'none' },   // hidden: Three.js overlay replaces this
        paint: {
          'fill-extrusion-color': '#3388cc',
          'fill-extrusion-height': ['coalesce', ['get', 'height_m'], 4],
          'fill-extrusion-base':   ['coalesce', ['get', 'base_m'], 0],
          'fill-extrusion-opacity': 0.7
        }
      });

      // 지도레이어 패널 초기화 (geo/design과 동일 기능)
      if (window.FacilityLayerPanel) FacilityLayerPanel.init(State);

      // Hover popup for saved facilities
      State.map.on('click', 'facility-prod-fill', onProdFacilityClick);
      State.map.on('mouseenter', 'facility-prod-fill', () => {
        State.map.getCanvas().style.cursor = 'pointer';
      });
      State.map.on('mouseleave', 'facility-prod-fill', () => {
        if (!State.placeMode) State.map.getCanvas().style.cursor = '';
      });

      // Register Three.js 3D overlay — hides fill-extrusion boxes, uses real mesh
      if (window.AoTFacilityMap3D) {
        AoTFacilityMap3D.attach(State.map, []);
      }

      // Push preloaded geometry to preview source
      if (State.outerGeometry) {
        rebuildOuterGeometry();
      }
      } catch (e) {
        console.error('[facility] map load handler error:', e);
      }
    });

    // Click/dblclick listeners — registered immediately (no race with 'load')
    State.map.on('click', onMapClick);
    State.map.on('dblclick', onMapDblClick);

    document.getElementById('map-selector').addEventListener('change', (e) => {
      const opt = e.target.selectedOptions[0];
      if (!opt) return;
      const lat = parseFloat(opt.dataset.lat);
      const lng = parseFloat(opt.dataset.lng);
      const zoom = parseFloat(opt.dataset.zoom) || 13;
      if (!isNaN(lat) && !isNaN(lng)) {
        State.map.flyTo({ center: [lng, lat], zoom });
      }
      // Reload saved facilities + sites for the newly selected map
      loadSavedFacilities(opt.value);
      loadSites(opt.value);
    });

    const siteSel = document.getElementById('site-selector');
    if (siteSel) siteSel.addEventListener('change', (e) => onSiteChange(e.target.value));
  }

  function emptyFC() {
    return { type: 'FeatureCollection', features: [] };
  }

  function setOuterGeometry(geom, props) {
    State.outerGeometry = geom;
    const fc = geom
      ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: geom, properties: props || {} }] }
      : emptyFC();
    if (State.map && State.map.getSource('facility-preview')) {
      State.map.getSource('facility-preview').setData(fc);
    }
    _update3DPreview();
  }

  // =========================================================
  // Saved facilities (facility-prod source)
  // =========================================================
  async function loadSavedFacilities(geoId) {
    if (!State.map || !State.map.getSource('facility-prod')) return;
    if (!geoId) {
      State.map.getSource('facility-prod').setData(emptyFC());
      return;
    }
    try {
      const url = '/api/geo/facility/list?geo_id=' + encodeURIComponent(geoId);
      const res = await fetch(url, { credentials: 'same-origin' });
      const json = await res.json();
      if (!json.ok) return;
      const prodFacilities = (json.facilities || [])
        .filter(f => f.unique_id !== State.facilityUuid);  // exclude facility under edit
      const features = prodFacilities.map(toProdFeature).filter(Boolean);
      State.map.getSource('facility-prod').setData({
        type: 'FeatureCollection', features: features
      });
      _load3DProdFacilities(prodFacilities);
    } catch (e) {
      console.warn('[facility] loadSavedFacilities failed:', e);
    }
  }

  function toProdFeature(f) {
    const geom = f.outer_feature && f.outer_feature.geometry;
    if (!geom) return null;
    const g3d = f.geometry_3d || {};
    return {
      type: 'Feature',
      geometry: geom,
      properties: {
        facility_uuid: f.unique_id,
        name: f.name,
        preset: f.preset,
        structure: f.structure,
        bay_count: f.bay_count,
        height_m: g3d.ridge_height_m || 4,
        eave_h: g3d.eave_height_m || 2,
        base_m: 0
      }
    };
  }

  function onProdFacilityClick(e) {
    const ft = e.features && e.features[0];
    if (!ft) return;
    const p = ft.properties || {};
    const structureLabel = p.structure === 'connected'
      ? ' · connected ×' + p.bay_count
      : ' · single';
    const html =
      '<div style="font-size:13px"><strong>' + (p.name || '(unnamed)') + '</strong>' +
      '<br><small>' + (p.preset || '') + structureLabel + '</small>' +
      '<br><a href="?facility_uuid=' + p.facility_uuid + '">Edit</a></div>';
    new maplibregl.Popup({ closeOnClick: true })
      .setLngLat(e.lngLat)
      .setHTML(html)
      .addTo(State.map);
  }

  // =========================================================
  // Sites for the active map (Phase B — site selector)
  // =========================================================
  async function loadSites(geoId) {
    const sel = document.getElementById('site-selector');
    if (!sel) return;
    State.sites = [];
    State.selectedSiteUuid = null;
    sel.innerHTML = '';
    updateSiteLayerData();

    if (!geoId) {
      sel.disabled = true;
      sel.innerHTML = '<option value="" disabled selected>Select a Map first</option>';
      return;
    }
    try {
      const url = '/api/geo/overlays?map_uuid=' + encodeURIComponent(geoId) + '&type=site';
      const res = await fetch(url, { credentials: 'same-origin' });
      const json = await res.json();
      const features = (json && json.features) || [];
      State.sites = features;
      updateSiteLayerData();

      if (features.length === 0) {
        sel.disabled = true;
        sel.innerHTML = '<option value="" disabled selected>No sites in this map</option>';
        return;
      }
      sel.disabled = false;
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = '— Select a Site —';
      placeholder.selected = true;
      sel.appendChild(placeholder);
      features.forEach((f) => {
        const props = f.properties || {};
        const opt = document.createElement('option');
        opt.value = props.unique_id || props.db_id || '';
        opt.textContent = props.name || ('Site #' + (props.db_id || ''));
        sel.appendChild(opt);
      });
    } catch (e) {
      console.warn('[facility] loadSites failed:', e);
      sel.disabled = true;
      sel.innerHTML = '<option value="" disabled selected>Failed to load sites</option>';
    }
  }

  function onSiteChange(siteIdValue) {
    State.selectedSiteUuid = siteIdValue || null;
    if (!siteIdValue) return;
    const ft = State.sites.find((f) => {
      const p = f.properties || {};
      return String(p.unique_id) === siteIdValue || String(p.db_id) === siteIdValue;
    });
    if (!ft || !ft.geometry || !State.map) return;
    try {
      const bounds = geometryBounds(ft.geometry);
      if (bounds) State.map.fitBounds(bounds, { padding: 80, duration: 500, maxZoom: 18 });
    } catch (e) { /* ignore */ }
  }

  // =========================================================
  // Map-sites source update (called after loadSites)
  // =========================================================
  function updateSiteLayerData() {
    if (!State.map || !State.map.getSource) return;
    const src = State.map.getSource(SITE_SRC);
    if (!src) return;
    const feats = (State.sites || []).filter(f => f && f.geometry);
    src.setData({ type: 'FeatureCollection', features: feats });
  }

  // =========================================================
  // Place-on-Map mode + parametric rectangle generation
  // =========================================================
  function startPlaceMode() {
    State.placeMode = true;
    if (State.map) {
      State.map.getCanvas().style.cursor = 'crosshair';
      // dragPan steals 'click' on tiny mouse movement — disable for the placement click
      State.map.dragPan.disable();
      State.map.boxZoom.disable();
      State.map.scrollZoom.disable();
      State.map.touchZoomRotate.disable();
    }
    showToast('Click on the map to set the facility center');
  }

  function finishPlaceMode() {
    State.placeMode = false;
    if (State.map) {
      State.map.getCanvas().style.cursor = '';
      State.map.dragPan.enable();
      State.map.boxZoom.enable();
      State.map.scrollZoom.enable();
      State.map.touchZoomRotate.enable();
    }
  }

  function onMapClick(e) {
    if (!State.placeMode) return;
    State.center = [e.lngLat.lng, e.lngLat.lat];
    rebuildOuterGeometry();
    finishPlaceMode();
    debouncedCompute();
  }

  function onMapDblClick(e) {
    // No-op — kept for backward compat with previous draw-mode listeners
  }

  /** Build outer GeoJSON from form: dimensions + center + orientation + structure/bays/spacing. */
  function rebuildOuterGeometry() {
    if (!State.center) return;
    const span = parseFloat(document.getElementById('span-width').value) || 7;
    const length = parseFloat(document.getElementById('length-m').value) || 30;
    const ridgeH = parseFloat(document.getElementById('ridge-height').value) || 4;
    const eaveH  = parseFloat(document.getElementById('eave-height').value) || 2;
    const struct = (document.querySelector('input[name="structure"]:checked') || {}).value || 'single';
    const bayCount = Math.max(parseInt(document.getElementById('bay-count').value, 10) || 1, 1);
    const spacing = parseFloat((document.getElementById('spacing-m') || {}).value) || 0;
    const deg = Number.isFinite(State.orientationDeg) ? State.orientationDeg : 0;

    let geom;
    if (struct === 'single' && bayCount > 1) {
      // N detached single-bay greenhouses arranged in a row with `spacing` between
      geom = buildMultiRectGeoJSON(State.center, span, length, bayCount, spacing, deg);
    } else {
      // Single (1 bay) OR Connected (one envelope spanning all bays)
      const W = struct === 'connected' ? span * bayCount : span;
      geom = buildRotatedRectGeoJSON(State.center, W, length, deg);
    }
    setOuterGeometry(geom, { height_m: ridgeH, eave_h: eaveH, base_m: 0 });
  }

  /** One rotated rectangle (Polygon) at center. */
  function buildRotatedRectGeoJSON(center, W_m, L_m, deg) {
    const ring = rotatedRectRing(center, 0, 0, W_m, L_m, deg);
    return { type: 'Polygon', coordinates: [ring] };
  }

  /** N rotated rectangles arranged along the span axis (MultiPolygon).
   * The group is rotated together by `deg`, so each bay shares the same orientation.
   */
  function buildMultiRectGeoJSON(center, span, length, count, spacing, deg) {
    const totalSpan = span * count + spacing * (count - 1);
    const halfTotal = totalSpan / 2;
    const polygons = [];
    for (let i = 0; i < count; i++) {
      const offX = -halfTotal + span / 2 + i * (span + spacing);
      const ring = rotatedRectRing(center, offX, 0, span, length, deg);
      polygons.push([ring]);
    }
    return { type: 'MultiPolygon', coordinates: polygons };
  }

  /** Build a single ring (closed) for a rectangle whose local center is offset
   * by (offX, offY) from `center`, then rotate the whole thing by `deg` around `center`. */
  function rotatedRectRing(center, offX, offY, W_m, L_m, deg) {
    const cLng = center[0], cLat = center[1];
    const halfW = W_m / 2, halfL = L_m / 2;
    const localCorners = [
      [offX - halfW, offY - halfL],
      [offX + halfW, offY - halfL],
      [offX + halfW, offY + halfL],
      [offX - halfW, offY + halfL]
    ];
    const theta = (deg || 0) * Math.PI / 180;
    const cosT = Math.cos(theta), sinT = Math.sin(theta);
    const M_PER_DEG_LAT = 111320.0;
    const M_PER_DEG_LNG = M_PER_DEG_LAT * Math.cos(cLat * Math.PI / 180);
    const ring = localCorners.map(function (c) {
      const dx = c[0], dy = c[1];
      const rx = dx * cosT - dy * sinT;
      const ry = dx * sinT + dy * cosT;
      return [cLng + rx / M_PER_DEG_LNG, cLat + ry / M_PER_DEG_LAT];
    });
    ring.push(ring[0]);
    return ring;
  }

  /** Collect every coordinate of a (Multi)Polygon's outer ring(s). */
  function geometryAllCoords(geom) {
    if (!geom) return [];
    if (geom.type === 'Polygon') {
      return (geom.coordinates && geom.coordinates[0]) || [];
    }
    if (geom.type === 'MultiPolygon') {
      const all = [];
      const polys = geom.coordinates || [];
      for (let i = 0; i < polys.length; i++) {
        const ring = polys[i] && polys[i][0];
        if (ring && ring.length) {
          for (let j = 0; j < ring.length; j++) all.push(ring[j]);
        }
      }
      return all;
    }
    return [];
  }

  function polygonCentroid(geom) {
    const coords = geometryAllCoords(geom);
    if (coords.length < 2) return null;
    let sx = 0, sy = 0, n = 0;
    // ring is closed (last == first); skip duplicate
    for (let i = 0; i < coords.length - 1; i++) {
      sx += coords[i][0]; sy += coords[i][1]; n++;
    }
    return n > 0 ? [sx / n, sy / n] : null;
  }

  /** Compute bounds covering all polygons (single or multi). */
  function geometryBounds(geom) {
    const coords = geometryAllCoords(geom);
    if (coords.length === 0) return null;
    const b = new maplibregl.LngLatBounds(coords[0], coords[0]);
    for (let i = 1; i < coords.length; i++) b.extend(coords[i]);
    return b;
  }

  // =========================================================
  // Actuators
  // =========================================================
  async function loadOutputs() {
    try {
      const res = await fetch('/api/geo/devices', { credentials: 'same-origin' });
      const json = await res.json();
      const list = json.devices || json || [];
      State.availableOutputs = list.filter((d) => {
        const t = (d.type || '').toLowerCase();
        return ['output', 'function', 'custom_controller', 'custom', 'pid'].includes(t);
      });
      if (window.ActuatorUI) ActuatorUI.setDevices(State.availableOutputs);
    } catch (e) {
      console.warn('[facility] loadOutputs failed:', e);
    }
  }

  // =========================================================
  // Form ↔ State
  // =========================================================
  function readForm() {
    const data = {
      facility_uuid: State.facilityUuid || undefined,
      geo_id: document.getElementById('map-selector').value,
      site_shape_uuid: State.selectedSiteUuid || '',
      name: document.getElementById('facility-name').value || 'New Facility',
      preset: document.getElementById('facility-preset').value,
      structure: (document.querySelector('input[name="structure"]:checked') || {}).value || 'single',
      bay_count: parseInt(document.getElementById('bay-count').value, 10) || 1,
      outer_geometry: State.outerGeometry,
      geometry_3d: {
        span_width_m: parseFloat(document.getElementById('span-width').value) || 7,
        eave_height_m: parseFloat(document.getElementById('eave-height').value) || 2,
        ridge_height_m: parseFloat(document.getElementById('ridge-height').value) || 4,
        length_m: parseFloat(document.getElementById('length-m').value) || 30,
        orientation_deg: State.orientationDeg || 0,
        roof_type: (document.getElementById('roof-type') || {}).value || 'arch',
        spacing_m: parseFloat((document.getElementById('spacing-m') || {}).value) || 0,
        center_lng: State.center ? State.center[0] : null,
        center_lat: State.center ? State.center[1] : null,
      },
      envelope:  window.EnvelopeUI  ? EnvelopeUI.read()  : {},
      actuators: window.ActuatorUI  ? ActuatorUI.read()  : [],
      fittings:  window.FittingsUI  ? FittingsUI.read()  : []
    };
    return data;
  }

  function fillForm(f) {
    State.facilityUuid = f.unique_id;
    State.outerGeometry = (f.outer_feature && f.outer_feature.geometry) || null;
    setOuterGeometry(State.outerGeometry);

    document.getElementById('facility-name').value = f.name || '';
    document.getElementById('facility-preset').value = f.preset || 'standard_arch';
    document.querySelectorAll('input[name="structure"]').forEach((r) => {
      r.checked = (r.value === f.structure);
    });
    document.getElementById('bay-count').value = f.bay_count || 1;
    if (f.geo_id) {
      document.getElementById('map-selector').value = f.geo_id;
      // Reload sites for this map so the site-selector can be restored below
      loadSites(f.geo_id).then(() => {
        if (f.parent_site_uuid) {
          const sel = document.getElementById('site-selector');
          if (sel) {
            sel.value = f.parent_site_uuid;
            State.selectedSiteUuid = f.parent_site_uuid;
          }
        }
      });
      // facility-prod also needs to refresh for the loaded map
      loadSavedFacilities(f.geo_id);
    }

    if (f.geometry_3d) {
      document.getElementById('span-width').value = f.geometry_3d.span_width_m || 7;
      document.getElementById('eave-height').value = f.geometry_3d.eave_height_m || 2;
      document.getElementById('ridge-height').value = f.geometry_3d.ridge_height_m || 4;
      document.getElementById('length-m').value = f.geometry_3d.length_m || 30;
      const roofSel = document.getElementById('roof-type');
      if (roofSel) roofSel.value = f.geometry_3d.roof_type || 'arch';
      const spacingEl = document.getElementById('spacing-m');
      if (spacingEl) spacingEl.value = (f.geometry_3d.spacing_m != null ? f.geometry_3d.spacing_m : 1.0);
      State.orientationDeg = f.geometry_3d.orientation_deg || 0;
      const slider = document.getElementById('orientation-slider');
      const orientInput = document.getElementById('orientation-input');
      const orientValue = document.getElementById('orientation-value');
      if (slider) slider.value = State.orientationDeg;
      if (orientInput) orientInput.value = State.orientationDeg;
      if (orientValue) orientValue.textContent = State.orientationDeg;
    }
    // Recover center from saved polygon centroid (best-effort)
    if (State.outerGeometry) {
      State.center = polygonCentroid(State.outerGeometry);
    }
    if (f.envelope && window.EnvelopeUI) {
      EnvelopeUI.fill(f.envelope);
    }
    if (f.actuators && window.ActuatorUI) {
      ActuatorUI.fill(f.actuators);
    }
    if (window.FittingsUI) {
      FittingsUI.fill(f.fittings || []);
      _renderFittingsAggregate();
    }
    if (f.computed) updatePreview(f.computed);

    handleStructureChange();

    // Re-emit polygon with height_m/eave_h in properties so the 3D extrusion layer
    // picks up the correct ridge height for the loaded facility.
    if (State.center) {
      rebuildOuterGeometry();
    }

    // Recenter map on outer polygon (cap zoom at 18 to avoid OSM/CARTO 404 at z=20)
    // Supports both Polygon and MultiPolygon (Phase C: single + bays > 1).
    if (State.outerGeometry && State.map) {
      const bounds = geometryBounds(State.outerGeometry);
      if (bounds) {
        const doFit = (label) => {
          try {
            State.map.fitBounds(bounds, { padding: 60, duration: 0, maxZoom: 18 });
          } catch (e) {}
        };
        // Immediate (works if style/style-data is already loaded)
        doFit('immediate');
        // Safety net: fire on first idle in case the immediate call lost a race
        // with style loading or pending source data.
        try { State.map.once('idle', () => doFit('idle')); } catch (e) {}
      } else {
        console.warn('[facility v3] empty bounds for geometry', State.outerGeometry);
      }
    } else {
      console.warn('[facility v3] fillForm: no outerGeometry or map',
                   { hasGeom: !!State.outerGeometry, hasMap: !!State.map });
    }

    // Notify 3D preview to rebuild with the newly loaded facility data.
    document.dispatchEvent(new CustomEvent('facility-loaded'));
  }

  // =========================================================
  // Compute (debounced)
  // =========================================================
  let computeTimer = null;
  function debouncedCompute() {
    clearTimeout(computeTimer);
    computeTimer = setTimeout(doCompute, 500);
  }

  async function doCompute() {
    const data = readForm();
    if (!data.outer_geometry) return;
    try {
      const res = await fetch('/api/geo/facility/compute', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      if (res.status === 501) {
        // P4 facility_calc not yet available — leave preview as is
        return;
      }
      const json = await res.json();
      if (json.ok) updatePreview(json.computed);
    } catch (e) {
      console.warn('[facility] compute failed:', e);
    }
  }

  function updatePreview(c) {
    if (!c) return;
    const set = (id, val, unit) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (val == null) { el.textContent = '— ' + unit; return; }
      el.textContent = (typeof val === 'number' ? val.toFixed(1) : val) + ' ' + unit;
    };
    set('pv-floor', c.floor_m2, 'm²');
    set('pv-volume', c.volume_m3, 'm³');
    set('pv-glazing', c.glazing_m2, 'm²');
    set('pv-vent', c.vent_open_m2, 'm²');
    // Heating: prefer nameplate (kW from actuators) if present, else theoretical load
    const heatingVal = (c.nameplate_heating_kw > 0) ? c.nameplate_heating_kw : c.heating_kw;
    const heatingEl = document.getElementById('pv-heating');
    if (heatingEl) {
      const ratio = c.heating_kw > 0 ? (heatingVal / c.heating_kw) : null;
      heatingEl.textContent = (heatingVal != null ? heatingVal.toFixed(1) : '—') + ' kW';
      heatingEl.title = c.nameplate_heating_kw > 0
        ? '명판: ' + c.nameplate_heating_kw.toFixed(1) + ' kW  /  계산: ' + c.heating_kw.toFixed(1) + ' kW' +
          (ratio != null ? ' (' + Math.round(ratio * 100) + '%)' : '')
        : '이론 계산값. 액추에이터에 히터 용량 입력 시 명판값 표시.';
    }
    const coolingVal = (c.nameplate_cooling_kw > 0) ? c.nameplate_cooling_kw : c.cooling_kw;
    const coolingEl = document.getElementById('pv-cooling');
    if (coolingEl) {
      coolingEl.textContent = (coolingVal != null ? coolingVal.toFixed(1) : '—') + ' kW';
      coolingEl.title = c.nameplate_cooling_kw > 0
        ? '명판: ' + c.nameplate_cooling_kw.toFixed(1) + ' kW  /  계산: ' + c.cooling_kw.toFixed(1) + ' kW'
        : '이론 계산값. 액추에이터에 냉각기 용량 입력 시 명판값 표시.';
    }
    if (c.ach_total != null) {
      set('pv-ach', c.ach_total, '/h');
    } else if (c.ach_m3h != null && c.volume_m3) {
      set('pv-ach', c.ach_m3h / c.volume_m3, '/h');
    }

    // Render fittings/actuator summary panel if present
    const sumEl = document.getElementById('pv-summary');
    if (sumEl) {
      const lines = [];
      if (c.fittings_count > 0) {
        const KIND_LABELS = { window:'창호', door:'출입문', curtain:'커튼', fan:'팬', heater:'히터', sensor:'센서', fixture:'설비' };
        const parts = Object.entries(c.fittings_by_kind || {}).map(([k, v]) => (KIND_LABELS[k] || k) + ' ' + v);
        lines.push('설치물: ' + c.fittings_count + '개 · ' + parts.join(', ') + ' · ' + c.fittings_total_area_m2 + 'm²');
      }
      if (c.actuator_counts && Object.keys(c.actuator_counts).length > 0) {
        const aLabels = { side_window_motor:'측창모터', roof_vent_motor:'지붕창모터', thermal_curtain_motor:'커튼모터',
                          exhaust_fan:'환기팬', circulation_fan:'순환팬', heater:'히터', cooler:'냉각기',
                          heat_pump:'히트펌프', irrigation_valve:'관개밸브' };
        const aParts = Object.entries(c.actuator_counts).map(([k, v]) => (aLabels[k] || k) + ' ' + v);
        lines.push('액추에이터: ' + aParts.join(', '));
      }
      sumEl.innerHTML = lines.length ? lines.join('<br>') : '';
    }
  }

  // =========================================================
  // Save / Load
  // =========================================================
  async function saveFacility() {
    const data = readForm();
    if (!data.geo_id) { alert('Please select a map first.'); return; }
    if (!data.outer_geometry) { alert('Use "Place on Map" to set the facility location first.'); return; }

    try {
      const res = await fetch('/api/geo/facility', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      const json = await res.json();
      if (json.ok) {
        State.facilityUuid = json.facility_uuid;
        showToast('Saved.');
        setTimeout(() => {
          window.location.search = '?facility_uuid=' + json.facility_uuid;
        }, 600);
      } else {
        alert('Save failed: ' + (json.message || 'unknown error'));
      }
    } catch (e) {
      alert('Save error: ' + e.message);
    }
  }

  async function loadFacility(uuid) {
    try {
      const res = await fetch('/api/geo/facility/' + uuid, { credentials: 'same-origin' });
      const json = await res.json();
      if (json.ok && json.facility) fillForm(json.facility);
    } catch (e) {
      console.warn('[facility] loadFacility failed:', e);
    }
  }

  // =========================================================
  // Event handlers
  // =========================================================
  function bindEventHandlers() {
    // structure radio: toggle bay-count input + rebuild rect (W = span × bays)
    document.querySelectorAll('input[name="structure"]').forEach((r) => {
      r.addEventListener('change', () => {
        handleStructureChange();
        rebuildOuterGeometry();
        debouncedCompute();
      });
    });
    // EnvelopeUI / ActuatorUI / FittingsUI fire custom events → trigger compute
    document.addEventListener('envelope-changed',       debouncedCompute);
    document.addEventListener('envelope-data-changed',  debouncedCompute); // compute only, no 3D rebuild
    document.addEventListener('actuator-changed',       debouncedCompute);
    document.addEventListener('fittings-changed',       debouncedCompute);
    // Aggregate panel was retired with the legacy Fittings form section.
    // (FittingsUI.aggregate() is still public for compute summary use.)

    // Bridge so the 3D tool palette's catalog button can resolve State.center.
    // wireTools() in geo_facility.html passes facCenter=null; intercept here
    // and inject State.center if available.
    document.addEventListener('aot-facility-need-center', function (e) {
      if (e.detail && typeof e.detail.cb === 'function') {
        e.detail.cb(State.center || null, State.orientationDeg || 0);
      }
    });

    // Roof vent toggle (not managed by EnvelopeUI's _notify, wire directly)
    const roofVentEl = document.getElementById('outer-roof-vent');
    if (roofVentEl) roofVentEl.addEventListener('change', debouncedCompute);
    const shadeEl = document.getElementById('curtain-shade');
    if (shadeEl) shadeEl.addEventListener('change', debouncedCompute);

    // Fields that change footprint dimensions OR 3D height → rebuild + recompute
    // (heights propagate to the fill-extrusion layer via properties)
    const dimensionFields = [
      'span-width', 'length-m', 'bay-count', 'spacing-m',
      'eave-height', 'ridge-height'
    ];
    dimensionFields.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('input', () => {
        rebuildOuterGeometry();
        debouncedCompute();
      });
    });

    // Roof type — affects compute (and dashboard mimic) but not footprint
    const roofSel = document.getElementById('roof-type');
    if (roofSel) roofSel.addEventListener('change', debouncedCompute);

    // Orientation slider + numeric input — bidirectional sync
    const slider = document.getElementById('orientation-slider');
    const orientInput = document.getElementById('orientation-input');
    const orientValue = document.getElementById('orientation-value');
    function setOrientation(deg, syncSlider, syncInput) {
      const d = ((parseFloat(deg) || 0) % 360 + 360) % 360;
      State.orientationDeg = d;
      if (syncSlider && slider) slider.value = d;
      if (syncInput && orientInput) orientInput.value = d;
      if (orientValue) orientValue.textContent = Math.round(d);
      rebuildOuterGeometry();
      debouncedCompute();
    }
    if (slider) slider.addEventListener('input', (e) => setOrientation(e.target.value, false, true));
    if (orientInput) orientInput.addEventListener('change', (e) => setOrientation(e.target.value, true, false));

    // Place-on-map button (replaces old draw-polygon flow)
    const placeBtn = document.getElementById('btn-place-on-map');
    if (placeBtn) placeBtn.addEventListener('click', startPlaceMode);
    document.getElementById('btn-clear-shape').addEventListener('click', () => {
      setOuterGeometry(null);
      State.center = null;
      finishPlaceMode();
    });
    document.getElementById('btn-save-facility').addEventListener('click', saveFacility);

    const integRefreshBtn = document.getElementById('btn-integ-refresh');
    if (integRefreshBtn) {
      integRefreshBtn.addEventListener('click', () => loadIntegration(State.facilityUuid));
    }
  }

  function _renderFittingsAggregate() {
    const el = document.getElementById('fittings-aggregate');
    if (!el || !window.FittingsUI) return;
    const agg = FittingsUI.aggregate();
    if (agg.total === 0) { el.innerHTML = ''; return; }
    const KIND_LABELS = {
      window:'창호', door:'출입문', curtain:'커튼',
      fan:'팬', heater:'히터', sensor:'센서', fixture:'설비'
    };
    const parts = Object.entries(agg.by_kind).map(([k, v]) =>
      (KIND_LABELS[k] || k) + ' ' + v.count + '개 (' + v.area_m2.toFixed(1) + '㎡)');
    el.innerHTML =
      '<b>총 ' + agg.total + '개 설치물</b> · ' + parts.join(' · ') +
      ' · 전체 면적 ' + agg.total_area_m2.toFixed(1) + '㎡';
  }

  function handleStructureChange() {
    const sel = document.querySelector('input[name="structure"]:checked');
    const v = sel ? sel.value : 'single';
    // Bays count is meaningful for both single (detached row) and connected
    const bayBox = document.getElementById('bay-count-container');
    if (bayBox) bayBox.style.display = '';
    // Spacing only applies to detached single-bay rows (connected bays share walls)
    const spacingBox = document.getElementById('spacing-container');
    if (spacingBox) spacingBox.style.display = (v === 'single') ? '' : 'none';
  }

  // =========================================================
  // 3D overlay helpers (AoTFacilityMap3D integration)
  // =========================================================
  function _readFacilitySpec() {
    return {
      unique_id: State.facilityUuid || 'preview',
      preset:    document.getElementById('facility-preset').value || 'standard_arch',
      structure: (document.querySelector('input[name="structure"]:checked') || {}).value || 'single',
      bay_count: Math.max(parseInt(document.getElementById('bay-count').value, 10) || 1, 1),
      geometry_3d: {
        span_width_m:    parseFloat(document.getElementById('span-width').value)  || 7,
        eave_height_m:   parseFloat(document.getElementById('eave-height').value) || 2,
        ridge_height_m:  parseFloat(document.getElementById('ridge-height').value) || 4,
        length_m:        parseFloat(document.getElementById('length-m').value)    || 30,
        orientation_deg: State.orientationDeg || 0,
        roof_type:       (document.getElementById('roof-type') || {}).value || 'arch',
        spacing_m:       parseFloat((document.getElementById('spacing-m') || {}).value) || 0,
      },
      envelope: window.EnvelopeUI ? EnvelopeUI.read() : {},
    };
  }

  function _update3DPreview() {
    if (!window.AoTFacilityMap3D) return;
    if (!State.outerGeometry || !State.center) {
      AoTFacilityMap3D.clearPreview();
      return;
    }
    AoTFacilityMap3D.setPreview(_readFacilitySpec(), State.center);
  }

  function _load3DProdFacilities(facilities) {
    if (!window.AoTFacilityMap3D) return;
    AoTFacilityMap3D.loadProd(facilities || []);
  }

  // =========================================================
  // C1: IEC 통합 요약 패널
  // =========================================================
  const _INTEG_KIND_LABELS = {
    opening:'개구부', circulation_fan:'순환팬', exhaust_fan:'배기팬',
    heater:'히터', cooler:'냉각기', fogger:'가습기', co2_injector:'CO₂',
    shade:'차광', curtain:'커튼', lighting:'조명',
  };
  const _INTEG_FACE_LABELS = {
    south:'남', north:'북', east:'동', west:'서', roof:'지붕', floor:'바닥',
  };

  function _integFmt(v, d) {
    return (v != null && !isNaN(v)) ? Number(v).toFixed(d) : '—';
  }
  function _integEsc(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function _renderIntegration(d) {
    const cm = d.capacity_meta || {};
    const srcCls = { fittings:'integ-badge-fittings', envelope:'integ-badge-envelope', none:'integ-badge-none' }[cm.vent_open_source] || 'integ-badge-none';
    const srcLbl = { fittings:'Fittings (G1)', envelope:'Envelope', none:'없음' }[cm.vent_open_source] || (cm.vent_open_source || '');

    // ── capacity meta strip ──
    let html = '<div class="integ-meta-strip">';
    html += '<span>체적 <b>' + _integFmt(cm.volume_m3, 1) + ' m³</b></span>';
    html += '<span>외피 <b>' + _integFmt(cm.envelope_m2, 1) + ' m²</b></span>';
    html += '<span>U효과 <b>' + _integFmt(cm.u_effective, 3) + '</b></span>';
    html += '<span>환기면적 <b>' + _integFmt(cm.vent_open_m2, 2) + ' m²</b>'
          + ' <span class="integ-badge ' + srcCls + '">' + _integEsc(srcLbl) + '</span></span>';
    html += '</div>';

    // ── actuators_resolved ──
    const acts = d.actuators_resolved || [];
    if (acts.length) {
      html += '<div class="integ-section-label">액추에이터 연동 (' + acts.length + ')</div>';
      html += '<table class="integ-table"><thead><tr>'
            + '<th>Output</th><th>Kind</th><th>Slot</th><th>Vent m²</th><th>Fitting</th>'
            + '</tr></thead><tbody>';
      acts.forEach(a => {
        const kindLbl = _INTEG_KIND_LABELS[a.kind] || (a.kind || '—');
        const ventStr = a.vent_openings_area_m2 > 0 ? a.vent_openings_area_m2.toFixed(2) : '—';
        const fitCnt  = (a.fitting_ids || []).length || '—';
        html += '<tr>'
              + '<td>' + _integEsc(a.output_name || a.output_uuid) + '</td>'
              + '<td>' + _integEsc(kindLbl) + '</td>'
              + '<td class="integ-slot">' + _integEsc(a.slot_key || '—') + '</td>'
              + '<td>' + ventStr + '</td>'
              + '<td>' + fitCnt + '</td>'
              + '</tr>';
      });
      html += '</tbody></table>';
    }

    // ── vent_openings pills ──
    const vos = d.vent_openings || [];
    if (vos.length) {
      html += '<div class="integ-section-label">개구부 (' + vos.length + ')</div>';
      html += '<div class="integ-pills">';
      vos.forEach(v => {
        const face = _INTEG_FACE_LABELS[v.face] || (v.face || '?');
        html += '<span class="integ-pill">' + _integEsc(face) + ' ' + (v.area_m2 || 0).toFixed(2) + ' m²</span>';
      });
      html += '</div>';
    }

    // ── sensors_resolved ──
    const sensors = d.sensors_resolved || [];
    if (sensors.length) {
      html += '<div class="integ-section-label">센서 연동 (' + sensors.length + ')</div>';
      html += '<table class="integ-table"><thead><tr><th>센서</th><th>Input</th></tr></thead><tbody>';
      sensors.forEach(s => {
        const inputLbl = s.input_name || (s.input_uuid ? s.input_uuid.slice(0, 8) + '…' : '—');
        html += '<tr><td>' + _integEsc(s.name || s.fitting_id) + '</td><td>' + _integEsc(inputLbl) + '</td></tr>';
      });
      html += '</tbody></table>';
    }

    if (!acts.length && !vos.length && !sensors.length) {
      html += '<div class="integ-empty">연동된 액추에이터/센서가 없습니다. 피팅을 배치하고 저장하면 반영됩니다.</div>';
    }

    html += '<div class="integ-note">저장 후 IEC 통합 데이터가 반영됩니다.</div>';
    return html;
  }

  async function loadIntegration(uuid) {
    if (!uuid) return;
    const panel = document.getElementById('integ-panel');
    const body  = document.getElementById('integ-body');
    if (!panel || !body) return;
    panel.style.display = '';
    body.innerHTML = '<span class="integ-loading">통합 데이터 로드 중…</span>';
    try {
      const res  = await fetch('/api/geo/facility/' + uuid + '/integration', { credentials: 'same-origin' });
      const json = await res.json();
      body.innerHTML = json.ok ? _renderIntegration(json) : '<span class="integ-error">로드 실패: ' + _integEsc(json.message || '') + '</span>';
    } catch (e) {
      body.innerHTML = '<span class="integ-error">오류: ' + _integEsc(e.message) + '</span>';
    }
  }

  function showToast(msg) {
    const t = document.createElement('div');
    t.textContent = msg;
    t.style.cssText =
      'position:fixed;bottom:30px;right:30px;background:#333;color:#fff;' +
      'padding:.6rem 1.2rem;border-radius:6px;z-index:9999;' +
      'font-size:.9rem;box-shadow:0 2px 6px rgba(0,0,0,0.3);';
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2500);
  }
})();
