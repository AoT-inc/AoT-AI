# coding=utf-8
#
#  widget_indicator.py - Indicator dashboard widget
#
#  (생략)
#
import logging

from flask_babel import lazy_gettext

from aot-ai.utils.constraints_pass import constraints_pass_positive_value

logger = logging.getLogger(__name__)

WIDGET_INFORMATION = {
    'widget_name_unique': 'widget_indicator',
    'widget_name': 'Indicator',
    'widget_library': '',
    'no_class': True,

    'message': 'Displays a red or yellow circular image based on a measurement value. Useful for showing if an Output is on or off.',

    'widget_width': 2,
    'widget_height': 7,

    'custom_options': [
        {
            'id': 'measurement',
            'type': 'select_measurement',
            'default_value': '',
            'options_select': [
                'Input',
                'Function',
                'Output_Channels_Measurements',
                'PID'
            ],
            'name': lazy_gettext('Measurement'),
            'phrase': 'Select a measurement to display'
        },
        {
            'id': 'measurement_max_age',
            'type': 'integer',
            'default_value': 120,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': "{} ({})".format(lazy_gettext('Max Age'), lazy_gettext('Seconds')),
            'phrase': lazy_gettext('The maximum age of the measurement to use')
        },
        {
            'id': 'refresh_seconds',
            'type': 'float',
            'default_value': 30.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': '{} ({})'.format(lazy_gettext("Refresh"), lazy_gettext("Seconds")),
            'phrase': 'The period of time between refreshing the widget'
        },
        {
            'id': 'decimal_places',
            'type': 'integer',
            'default_value': 2,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Decimal Places',
            'phrase': 'The number of measurement decimal places'
        },
        {
            'id': 'option_invert',
            'type': 'bool',
            'default_value': False,
            'name': 'Invert Colors',
            'phrase': 'Invert the indicator colors'
        }
    ],

    'widget_dashboard_head': """<!-- No head content -->""",

    'widget_dashboard_title_bar': """<span style="font-size: {{each_widget.font_em_name}}em">{{each_widget.name}}</span>""",

    'widget_dashboard_body': """<div class="widget-indicator-body"><img id="value-{{each_widget.unique_id}}" src="" alt=""></div>""",

    'widget_dashboard_js': """
  // Retrieve the latest/last measurement for indicator widget
  function getLastDataIndicator(widget_id,
                       unique_id,
                       measure_type,
                       measurement_id,
                       max_measure_age_sec,
                       decimal_places,
                       invert) {
    if (decimal_places === null) {
      decimal_places = 1;
    }
    if (measure_type === "output") {
      const url = '/outputstate_unique_id/' + unique_id + '/' + measurement_id;
      $.ajax(url, {
        success: function (data, responseText, jqXHR) {
          // 데이터가 없거나 HTTP 204일 경우 off로 처리
          if (jqXHR.status === 204 || data === null) {
            document.getElementById('value-' + widget_id).src = '/static/img/button-red.png';
            document.getElementById('value-' + widget_id).title = "{{_('Off')}}";
          }
          else {
            if (data !== 'off') {
              document.getElementById('value-' + widget_id).title = "{{_('On')}}";
            } else {
              document.getElementById('value-' + widget_id).title = "{{_('Off')}}";
            }
            if ((data !== 'off' && !invert) || (data === 'off' && invert)) {
              document.getElementById('value-' + widget_id).src = '/static/img/button-yellow.png';
            }
            else {
              document.getElementById('value-' + widget_id).src = '/static/img/button-red.png';
            }
          }
        },
        error: function (jqXHR, textStatus, errorThrown) {
          document.getElementById('value-' + widget_id).src = '/static/img/button-red.png';
          document.getElementById('value-' + widget_id).innerHTML = "{{_('Off')}}";
        }
      });
    }
    else {
      const url = '/last/' + unique_id + '/' + measure_type + '/' + measurement_id + '/' + max_measure_age_sec.toString();
      $.ajax(url, {
        success: function(data, responseText, jqXHR) {
          // 데이터가 없으면 off로 처리
          if (jqXHR.status === 204 || data === null) {
            document.getElementById('value-' + widget_id).src = '/static/img/button-red.png';
            document.getElementById('value-' + widget_id).title = "{{_('Off')}}: 0";
          }
          else {
            const formattedTime = epoch_to_timestamp(data[0] * 1000);
            const measurement = data[1];
            if ((measurement && !invert) || (!measurement && invert)) {
              document.getElementById('value-' + widget_id).src = '/static/img/button-yellow.png';
            } else {
              document.getElementById('value-' + widget_id).src = '/static/img/button-red.png';
            }
            document.getElementById('value-' + widget_id).title = "{{_('Value')}}: " + measurement.toFixed(decimal_places);
          }
        },
        error: function(jqXHR, textStatus, errorThrown) {
          document.getElementById('value-' + widget_id).src = '/static/img/button-red.png';
          document.getElementById('value-' + widget_id).title = "{{_('Off')}}: 0";
        }
      });
    }
  }

  // Repeat function for getLastDataIndicator()
  function repeatLastDataIndicator(widget_id,
                                   dev_id,
                                   measure_type,
                                   measurement_id,
                                   period_sec,
                                   max_measure_age_sec,
                                   decimal_places,
                                   invert) {
    setInterval(function () {
      getLastDataIndicator(widget_id,
                           dev_id,
                           measure_type,
                           measurement_id,
                           max_measure_age_sec,
                           decimal_places,
                           invert)
    }, period_sec * 1000);
  }
""",

    'widget_dashboard_js_ready': """<!-- No JS ready content -->""",

    'widget_dashboard_js_ready_end': """
  {%- set device_id = widget_options['measurement'].split(",")[0] -%}
  {%- set measurement_id = widget_options['measurement'].split(",")[1] -%}
  {%- set channel_id = widget_options['measurement'].split(",")[2] -%}
  
  {% for each_input in input if each_input.unique_id == device_id %}
  getLastDataIndicator('{{each_widget.unique_id}}', '{{each_input.unique_id}}', 'input', '{{measurement_id}}', {{widget_options['measurement_max_age']}}, {{widget_options['decimal_places']}}, {{widget_options['option_invert']|int}});
  repeatLastDataIndicator('{{each_widget.unique_id}}', '{{each_input.unique_id}}', 'input', '{{measurement_id}}', {{widget_options['refresh_seconds']}}, {{widget_options['measurement_max_age']}}, {{each_widget.decimal_places}}, {{widget_options['option_invert']|int}});
  {%- endfor -%}

  {% for each_output in output if each_output.unique_id == device_id %}
  getLastDataIndicator('{{each_widget.unique_id}}', '{{each_output.unique_id}}', 'output', '{{channel_id}}', {{widget_options['measurement_max_age']}}, {{widget_options['decimal_places']}}, {{widget_options['option_invert']|int}});
  repeatLastDataIndicator('{{each_widget.unique_id}}', '{{each_output.unique_id}}', 'output', '{{channel_id}}', {{widget_options['refresh_seconds']}}, {{widget_options['measurement_max_age']}}, {{each_widget.decimal_places}}, {{widget_options['option_invert']|int}});
  {%- endfor -%}

  {% for each_pid in pid if each_pid.unique_id == device_id %}
  getLastDataIndicator('{{each_widget.unique_id}}', '{{each_pid.unique_id}}', 'pid', '{{measurement_id}}', {{widget_options['measurement_max_age']}}, {{widget_options['decimal_places']}}, {{widget_options['option_invert']|int}});
  repeatLastDataIndicator('{{each_widget.unique_id}}', '{{each_pid.unique_id}}', 'pid', '{{measurement_id}}', {{widget_options['refresh_seconds']}}, {{widget_options['measurement_max_age']}}, {{each_widget.decimal_places}}, {{widget_options['option_invert']|int}});
  {%- endfor -%}
"""
}