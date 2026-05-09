// aot-facility-widget.js — Dashboard widget controller (3D, Three.js)
// PRD/DESIGN-GEO-FACILITY-001 · MVP v2
(function () {
  'use strict';

  const STATE = {};  // { [widgetId]: { vars, threeCtx, runtime } }

  // ── Entry point ──────────────────────────────────────────────────────────────
  function init(widgetId) {
    const varsEl = document.getElementById('aot-facility-vars-' + widgetId);
    if (!varsEl) return;
    let vars;
    try { vars = JSON.parse(varsEl.textContent); }
    catch (e) { console.error('[AoT Facility] vars parse failed', e); return; }

    STATE[widgetId] = { vars, threeCtx: null, runtime: null };

    // Facility selector dropdown
    const sel = document.getElementById('aot-facility-select-' + widgetId);
    if (sel) {
      sel.addEventListener('change', function () {
        // PoC: reload page — proper impl patches widget custom_options via API
        if (sel.value && confirm('선택한 시설로 전환할까요? (위젯이 새로고침됩니다)')) {
          location.reload();
        }
      });
    }

    if (!vars.facility) return;

    // Wait for Three.js + AoTFacility3D to be ready
    _ensureThree(function () {
      _initScene(widgetId);
      _refreshRuntime(widgetId);
      if (vars.showAiAdvice) _renderAdvice(widgetId);

      if (vars.period && vars.period > 0) {
        setInterval(function () {
          _refreshRuntime(widgetId);
          if (vars.showAiAdvice) _renderAdvice(widgetId);
        }, vars.period * 1000);
      }
    });
  }

  // ── Three.js readiness check ──────────────────────────────────────────────────
  // Injects three.min.js dynamically if the widget head failed to include it.
  function _ensureThree(cb) {
    if (window.THREE && window.AoTFacility3D) { cb(); return; }

    // Self-heal: inject script tag if three.min.js is not already queued
    if (!window.THREE && !document.querySelector('script[src*="three.min.js"]')) {
      var s = document.createElement('script');
      s.src = '/static/js/widget/AoT_facility/three.min.js';
      document.head.appendChild(s);
    }

    // Poll until both THREE and AoTFacility3D are ready (up to 6s)
    var tries = 0;
    var poll = setInterval(function () {
      if ((window.THREE && window.AoTFacility3D) || ++tries > 60) {
        clearInterval(poll);
        if (window.THREE && window.AoTFacility3D) cb();
        else console.error('[AoT Facility] THREE or AoTFacility3D not available after 6s');
      }
    }, 100);
  }

  // ── Build / rebuild 3D scene ─────────────────────────────────────────────────
  function _initScene(widgetId) {
    const { vars, runtime } = STATE[widgetId];
    const canvas = document.getElementById('aot-facility-canvas-' + widgetId);
    if (!canvas || !window.AoTFacility3D) return;

    // Dispose previous context if any
    if (STATE[widgetId].threeCtx) {
      STATE[widgetId].threeCtx.dispose();
    }

    const ctx = window.AoTFacility3D.buildScene(canvas, vars.facility, runtime);
    STATE[widgetId].threeCtx = ctx;
  }

  // ── Fetch runtime data ────────────────────────────────────────────────────────
  async function _refreshRuntime(widgetId) {
    const { vars } = STATE[widgetId];
    const uuid = vars.facility.unique_id;
    const statusEl = document.getElementById('aot-facility-status-' + widgetId);

    try {
      const resp = await fetch('/api/aot/facility/' + uuid + '/runtime');
      if (!resp.ok) throw new Error(resp.status);
      const data = await resp.json();
      STATE[widgetId].runtime = data;

      _updateEnvPanel(widgetId, data);
      _publishAiContext(widgetId, data);

      // Rebuild scene with live actuator states
      if (window.AoTFacility3D) _initScene(widgetId);

      if (statusEl) statusEl.textContent = new Date().toLocaleTimeString();
    } catch (e) {
      console.warn('[AoT Facility] runtime fetch failed', e);
      if (statusEl) statusEl.textContent = '연결 오류';
    }
  }

  // ── Environment panel update ──────────────────────────────────────────────────
  function _updateEnvPanel(widgetId, runtime) {
    const envEl = document.getElementById('aot-facility-env-' + widgetId);
    if (!envEl) return;

    const outdoor = runtime.outdoor || {};
    const indoor  = runtime.indoor  || {};

    const vals = {
      indoor_temp:     indoor.temp_c     != null ? indoor.temp_c.toFixed(1) + ' °C' : '— °C',
      indoor_humidity: indoor.humidity_pct != null ? indoor.humidity_pct.toFixed(0) + ' %' : '— %',
      indoor_co2:      indoor.co2_ppm    != null ? indoor.co2_ppm.toFixed(0) + ' ppm' : '— ppm',
      outdoor_temp:    outdoor.temp_c    != null ? outdoor.temp_c.toFixed(1) + ' °C' : '— °C',
      wind:            outdoor.wind_ms   != null ? outdoor.wind_ms.toFixed(1) + ' m/s' : '— m/s',
      solar:           outdoor.solar_wm2 != null ? outdoor.solar_wm2.toFixed(0) + ' W/m²' : '— W/m²',
    };
    Object.entries(vals).forEach(([key, val]) => {
      const cell = envEl.querySelector('[data-key="' + key + '"]');
      if (cell) cell.textContent = val;
    });
  }

  // ── AI context publication ─────────────────────────────────────────────────────
  function _publishAiContext(widgetId, runtime) {
    const { vars } = STATE[widgetId];
    const f = vars.facility;
    if (!f) return;

    if (!window.AOT_AI_CONTEXT) window.AOT_AI_CONTEXT = {};
    if (!window.AOT_AI_CONTEXT.facility) window.AOT_AI_CONTEXT.facility = {};

    window.AOT_AI_CONTEXT.facility[widgetId] = {
      facility: {
        name:         f.name,
        preset:       f.preset,
        structure:    f.structure,
        bay_count:    f.bay_count,
        orientation_deg: (f.geometry_3d || {}).orientation_deg,
        geometry: {
          span_m:       (f.geometry_3d || {}).span_width_m,
          eave_m:       (f.geometry_3d || {}).eave_height_m,
          ridge_m:      (f.geometry_3d || {}).ridge_height_m,
          length_m:     (f.geometry_3d || {}).length_m,
          roof_type:    (f.geometry_3d || {}).roof_type,
        },
        envelope: {
          layers:       (f.envelope || {}).layer_count,
          outer_cover:  ((f.envelope || {}).outer || {}).cover_material,
          side_vent:    (((f.envelope || {}).outer || {}).side_vent || {}).enabled,
          roof_vent:    (((f.envelope || {}).outer || {}).roof_vent || {}).enabled,
          thermal_curtain: ((f.envelope || {}).curtain || {}).thermal,
          shade_curtain:   ((f.envelope || {}).curtain || {}).shade,
        },
      },
      capacity: f.computed || {},
      runtime: {
        outdoor:   (runtime || {}).outdoor  || {},
        indoor:    (runtime || {}).indoor   || {},
        actuators: (runtime || {}).actuator_states || {},
      },
      ts: new Date().toISOString(),
    };
  }

  // ── AI advice cards ───────────────────────────────────────────────────────────
  async function _renderAdvice(widgetId) {
    const adviceEl = document.getElementById('aot-facility-advice-' + widgetId);
    if (!adviceEl) return;
    const facility = STATE[widgetId].vars.facility;
    if (!facility) return;

    // Mock — real impl: GET /api/aot/facility/<uuid>/advice
    const cards = [
      { cls: 'now', title: '🔴 즉시 조치', actions: '측창 모터 닫기 권장', reason: '외기 강하 + 풍속 증가', effect: '열 손실 절감 예상', confidence: 0.84, horizon: 'now' },
      { cls: 'h1',  title: '🟡 1시간 내',  actions: '보온 커튼 전개 준비', reason: '일몰 후 외기 하강 예보', effect: '난방 부하 -25%',    confidence: 0.72, horizon: '1h' },
      { cls: 'h6',  title: '🟢 6시간 내',  actions: '새벽 단시간 환기 권장', reason: '이슬점 상승 예측',   effect: '결로 위험 억제',    confidence: 0.65, horizon: '6h' },
    ];

    adviceEl.innerHTML = cards.map(function (a) {
      return '<div class="advice-card ' + a.cls + '">' +
        '<div class="advice-title">' + a.title +
          '<span class="advice-conf">신뢰도 ' + Math.round(a.confidence * 100) + '%</span>' +
        '</div>' +
        '<div class="advice-actions">' + _esc(a.actions) + '</div>' +
        '<div class="advice-reason">' + _esc(a.reason) + '</div>' +
        '<div class="advice-effect">' + _esc(a.effect) + '</div>' +
        '<div class="advice-buttons">' +
          '<button class="approve" onclick="window.aotFacilityApprove(\'' + widgetId + '\',\'' +
            facility.unique_id + '\',\'' + a.horizon + '\')">승인하고 적용</button>' +
          '<button onclick="window.aotFacilityModify(\'' + a.horizon + '\')">수정</button>' +
          '<button onclick="window.aotFacilityIgnore(\'' + a.horizon + '\')">무시</button>' +
        '</div>' +
      '</div>';
    }).join('');
  }

  function _esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }

  // ── Approval handlers (PoC) ───────────────────────────────────────────────────
  window.aotFacilityApprove = function (widgetId, facilityUuid, horizon) {
    if (!confirm('AI 권고를 적용하시겠습니까? (' + horizon + ')')) return;
    alert('권고 적용 기록 (mock). 실제 output 명령 발행은 차기 단계.');
  };
  window.aotFacilityModify = function (horizon) { alert('수정 기능 — 차기 단계 (' + horizon + ')'); };
  window.aotFacilityIgnore = function (horizon) { alert('무시 기록 (mock, ' + horizon + ')'); };

  window.initAoTFacilityWidget = init;
})();
