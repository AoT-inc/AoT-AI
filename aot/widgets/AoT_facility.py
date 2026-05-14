# coding=utf-8
#
#  AoT_facility.py - Dashboard widget for facility operation view
#
#  Renders SVG mimic + environment summary + AI advice cards
#  Pattern follows AoT_map.py (Mycodo widget framework)
#
import logging
import json
from flask_babel import lazy_gettext

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Widget Definition
# ------------------------------------------------------------------------------

def execute_at_modification(mod_widget, request_form, custom_options_presave, custom_options_postsave):
    """Merge framework-parsed options with manual/legacy form data.

    @phase active
    """
    options = {}
    try:
        if mod_widget.custom_options:
            options = (json.loads(mod_widget.custom_options)
                       if isinstance(mod_widget.custom_options, str)
                       else dict(mod_widget.custom_options))
    except Exception:
        pass

    final = options.copy()
    if custom_options_postsave:
        for k, v in custom_options_postsave.items():
            final[k] = v
    return True, True, mod_widget, final


def widget_variables(widget_unique_id, widget_options):
    """Resolve template variables: selected facility + selector list.

    @phase active
    """
    from aot.databases.models import GeoFacility

    options = widget_options or {}
    facility_uuid = options.get('facility_uuid', '') if options else ''

    facility = None
    if facility_uuid:
        facility = GeoFacility.query.filter_by(unique_id=facility_uuid).first()
    if not facility:
        facility = GeoFacility.query.order_by(GeoFacility.updated_at.desc()).first()

    facility_data = None
    if facility:
        facility_data = {
            'unique_id': facility.unique_id,
            'name': facility.name,
            'preset': facility.preset,
            'structure': facility.structure,
            'bay_count': facility.bay_count or 1,
            'geometry_3d': facility.geometry_3d,
            'envelope': facility.envelope,
            'actuators': facility.actuators,
            'bays': facility.bays,
            'computed': facility.computed,
        }

    all_facilities = GeoFacility.query.order_by(GeoFacility.updated_at.desc()).all()
    facility_list = [{'unique_id': f.unique_id, 'name': f.name} for f in all_facilities]

    return {
        'facility': facility_data,
        'facilities': facility_list,
        'period': options.get('period', 60),
        'show_ai_advice': options.get('show_ai_advice', True),
    }


# ------------------------------------------------------------------------------
# Widget HTML Templates
# ------------------------------------------------------------------------------

WIDGET_HEAD_HTML = """
<script src="/static/js/widget/AoT_facility/three.min.js?v=2"></script>
<script src="/static/js/widget/AoT_facility/OrbitControls.js?v=1"></script>
<script src="/static/js/widget/AoT_facility/three-mesh-bvh.js?v=1"></script>
<script src="/static/js/widget/AoT_facility/GLTFLoader.js?v=1"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js" crossorigin="anonymous"></script>
<script src="/static/js/widget/AoT_facility/aot-facility-3d.js?v=5"></script>
<script src="/static/js/widget/AoT_facility/aot-facility-widget.js?v=2"></script>
<style>
  .aot-facility-container {
    width: 100%; height: 100%; overflow: auto; padding: 0.75rem;
    font-family: 'Inter', -apple-system, sans-serif;
    background: #f5f7fa;
  }
  .aot-facility-section {
    background: #fff; border-radius: 10px; padding: 0.85rem 1rem;
    margin-bottom: 0.75rem; box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  }
  .aot-facility-section h6 {
    font-weight: 600; color: #555; margin-bottom: 0.6rem; font-size: 0.95rem;
  }

  /* 3D canvas */
  .aot-facility-3d-wrap {
    width: 100%; height: 340px; border-radius: 8px;
    overflow: hidden; background: #f0f4f8; position: relative;
  }
  .aot-facility-3d-wrap canvas {
    width: 100% !important; height: 100% !important; display: block;
  }
  .aot-facility-3d-hint {
    position: absolute; bottom: 6px; right: 8px;
    font-size: 0.68rem; color: rgba(0,0,0,0.35); pointer-events: none;
  }

  .aot-facility-env {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
    gap: 0.4rem;
  }
  .env-cell { padding: 0.4rem 0.6rem; background: #f8f9fa; border-radius: 6px; }
  .env-label { font-size: 0.72rem; color: #888; }
  .env-value { font-size: 1rem; font-weight: 600; color: #2c3e50; }

  .advice-card {
    border-radius: 8px; padding: 0.65rem 0.85rem; margin-bottom: 0.45rem;
    border-left: 4px solid #ccc;
  }
  .advice-card.now { border-left-color: #e53935; background: #ffebee; }
  .advice-card.h1  { border-left-color: #fb8c00; background: #fff3e0; }
  .advice-card.h6  { border-left-color: #43a047; background: #e8f5e9; }
  .advice-title { font-weight: 600; font-size: 0.88rem; margin-bottom: 0.2rem; }
  .advice-conf { color: #888; font-size: 0.72rem; float: right; font-weight: 400; }
  .advice-actions { font-size: 0.84rem; color: #333; margin: 0.2rem 0; }
  .advice-reason { font-size: 0.78rem; color: #666; font-style: italic; }
  .advice-effect { font-size: 0.78rem; color: #1976d2; margin-top: 0.2rem; }
  .advice-buttons { margin-top: 0.4rem; }
  .advice-buttons button {
    font-size: 0.72rem; padding: 0.18rem 0.55rem; margin-right: 0.25rem;
    border-radius: 4px; border: 1px solid #ccc; background: white; cursor: pointer;
  }
  .advice-buttons button.approve {
    background: #1976d2; color: white; border-color: #1976d2;
  }

  .preset-badge {
    display: inline-block; padding: 0.1rem 0.4rem; background: #e3f2fd;
    border-radius: 3px; font-size: 0.7rem; color: #1976d2; margin-left: 0.3rem;
  }
</style>
"""

WIDGET_BODY_HTML = """
<div id="aot-facility-{{each_widget.unique_id}}" class="aot-facility-container">

  <div class="d-flex justify-content-between align-items-center mb-2">
    <select id="aot-facility-select-{{each_widget.unique_id}}"
            class="form-control form-control-sm" style="max-width:280px;">
      {% if widget_variables.facilities %}
        {% for f in widget_variables.facilities %}
          <option value="{{ f.unique_id }}"
            {% if widget_variables.facility and f.unique_id == widget_variables.facility.unique_id %}selected{% endif %}>
            {{ f.name }}
          </option>
        {% endfor %}
      {% else %}
        <option disabled>{{ _('No facilities — register one in /geo/facility') }}</option>
      {% endif %}
    </select>
    <small class="text-muted" id="aot-facility-status-{{each_widget.unique_id}}">—</small>
  </div>

  {% if widget_variables.facility %}

  <!-- Section A: 3D View -->
  <div class="aot-facility-section">
    <h6>§ A. {{ _('Facility 3D View') }}
      <span class="preset-badge">{{ widget_variables.facility.preset }}</span>
      {% if widget_variables.facility.structure == 'connected' %}
        <span class="preset-badge">{{ _('connected') }} ×{{ widget_variables.facility.bay_count }}</span>
      {% endif %}
      {% if widget_variables.facility.envelope and widget_variables.facility.envelope.layer_count == 2 %}
        <span class="preset-badge">{{ _('double layer') }}</span>
      {% endif %}
    </h6>
    <div class="aot-facility-3d-wrap">
      <canvas id="aot-facility-canvas-{{each_widget.unique_id}}"></canvas>
      <div class="aot-facility-3d-hint">우클릭: 회전 &nbsp;·&nbsp; 좌클릭: 팬/선택 &nbsp;·&nbsp; 스크롤: 줌</div>
    </div>
  </div>

  <!-- Section B: Environment summary -->
  <div class="aot-facility-section">
    <h6>§ B. {{ _('Environment') }}</h6>
    <div class="aot-facility-env" id="aot-facility-env-{{each_widget.unique_id}}">
      <div class="env-cell"><div class="env-label">{{ _('Indoor temp') }}</div><div class="env-value" data-key="indoor_temp">— °C</div></div>
      <div class="env-cell"><div class="env-label">{{ _('Indoor humidity') }}</div><div class="env-value" data-key="indoor_humidity">— %</div></div>
      <div class="env-cell"><div class="env-label">CO₂</div><div class="env-value" data-key="indoor_co2">— ppm</div></div>
      <div class="env-cell"><div class="env-label">{{ _('Outdoor temp') }}</div><div class="env-value" data-key="outdoor_temp">— °C</div></div>
      <div class="env-cell"><div class="env-label">{{ _('Wind') }}</div><div class="env-value" data-key="wind">— m/s</div></div>
      <div class="env-cell"><div class="env-label">{{ _('Solar') }}</div><div class="env-value" data-key="solar">— W/m²</div></div>
    </div>
  </div>

  <!-- Section C: AI advice -->
  {% if widget_variables.show_ai_advice %}
  <div class="aot-facility-section">
    <h6>§ C. {{ _('AI Advice') }}</h6>
    <div id="aot-facility-advice-{{each_widget.unique_id}}">
      <div class="text-muted small">{{ _('Loading…') }}</div>
    </div>
  </div>
  {% endif %}

  {% else %}
  <div class="alert alert-warning">
    {{ _('No facility selected. Register one at') }}
    <a href="/geo/facility">/geo/facility</a>.
  </div>
  {% endif %}
</div>

<script type="application/json" id="aot-facility-vars-{{each_widget.unique_id}}">
{{ {
    'widgetId': each_widget.unique_id,
    'facility': widget_variables.facility,
    'period': widget_variables.period or 60,
    'showAiAdvice': widget_variables.show_ai_advice or False
} | tojson | safe }}
</script>

<script>
;(function() {
    if (typeof window.initAoTFacilityWidget === 'function') {
        window.initAoTFacilityWidget('{{each_widget.unique_id}}');
    } else {
        console.warn('[AoT Facility] widget JS not loaded');
    }
})();
</script>
"""

WIDGET_INFORMATION = {
    'widget_name_unique': 'AoT_facility',
    'widget_name': lazy_gettext('AoT Facility'),
    'widget_library': 'SVG mimic + Mycodo widget framework',
    'no_class': True,
    'head_html': WIDGET_HEAD_HTML,
    'body_html': WIDGET_BODY_HTML,
    'configure_html': None,
    'widget_dashboard_configure_options': None,

    'message': lazy_gettext(
        'Facility cross-section mimic, environment summary, and AI advice — '
        'supports single/connected and single/double envelope.'
    ),

    'widget_width': 20,
    'widget_height': 20,
    'generate_page_variables': widget_variables,
    'execute_at_modification': execute_at_modification,

    'custom_options': [
        {
            'type': 'header',
            'name': lazy_gettext('General')
        },
        {
            'id': 'period',
            'type': 'integer',
            'default_value': 60,
            'name': lazy_gettext('Period (seconds)'),
            'phrase': lazy_gettext('Refresh interval. 0 to disable.'),
            'constraints': {'min': 0, 'max': 3600}
        },
        {
            'id': 'facility_uuid',
            'type': 'text',
            'default_value': '',
            'name': lazy_gettext('Facility UUID'),
            'phrase': lazy_gettext('unique_id of the selected facility (set via dropdown).')
        },
        {
            'id': 'show_ai_advice',
            'type': 'bool',
            'default_value': True,
            'name': lazy_gettext('Show AI Advice'),
            'phrase': lazy_gettext('Display AI recommendation cards (now / 1h / 6h).')
        },
    ],

    'widget_dashboard_head': WIDGET_HEAD_HTML,
    'widget_dashboard_title_bar': """
    <span style="padding-right: 0.5em">{{each_widget.name}}</span>
    """,
    'widget_dashboard_body': WIDGET_BODY_HTML,
    'widget_dashboard_js_ready': """""",
    'widget_dashboard_js_ready_end': """""",
}
