# -*- coding: utf-8 -*-
"""
[새로운 AoT 위젯] widget_AoT_controller_act_deact.py

- 성공/실패 메시지 Toastr 제거 (유지)
- refresh_seconds 주기로 서버 상태를 업데이트하도록 setInterval 복원
- 나머지 기능(버튼 이벤트, UI 로직 등)은 그대로 유지
"""

import logging
from flask import jsonify
from flask_babel import lazy_gettext
from flask_login import current_user

from aot-ai.databases.models import Conditional, CustomController, Function, Input, Trigger
from aot-ai.aot-ai_client import DaemonControl
from aot-ai.aot-ai_flask.utils.utils_general import user_has_permission
from aot-ai.utils.constraints_pass import constraints_pass_positive_value

logger = logging.getLogger(__name__)

def controller_state(unique_id):
    if not current_user.is_authenticated:
        return "You are not logged in and cannot access this endpoint"

    input_ = Input.query.filter(Input.unique_id == unique_id).first()
    function = Function.query.filter(Function.unique_id == unique_id).first()
    customfunction = CustomController.query.filter(CustomController.unique_id == unique_id).first()
    trigger = Trigger.query.filter(Trigger.unique_id == unique_id).first()
    conditional = Conditional.query.filter(Conditional.unique_id == unique_id).first()

    controller = None
    if input_:
        controller = input_
    elif function:
        controller = function
    elif customfunction:
        controller = customfunction
    elif trigger:
        controller = trigger
    elif conditional:
        controller = conditional

    if controller:
        return jsonify({"status": "Success", "state": controller.is_activated})

    return jsonify({"status": "Error", "state": f"Could not find Controller with ID {unique_id}"})


def controller_activate_deactivate(unique_id, state):
    """Activate/Deactivate Controller (Input/Function/Trigger/Conditional/CustomController)."""
    if not current_user.is_authenticated:
        return "You are not logged in and cannot access this endpoint"
    if not user_has_permission('edit_controllers'):
        return 'Insufficient user permissions to manipulate Controller'

    input_ = Input.query.filter(Input.unique_id == unique_id).first()
    function = Function.query.filter(Function.unique_id == unique_id).first()
    customfunction = CustomController.query.filter(CustomController.unique_id == unique_id).first()
    trigger = Trigger.query.filter(Trigger.unique_id == unique_id).first()
    conditional = Conditional.query.filter(Conditional.unique_id == unique_id).first()

    controller = None
    if input_:
        controller = input_
    elif function:
        controller = function
    elif customfunction:
        controller = customfunction
    elif trigger:
        controller = trigger
    elif conditional:
        controller = conditional

    if not controller or not unique_id or state not in ['activate', 'deactivate']:
        return "Invalid inputs: Controller ID or State"

    daemon = DaemonControl()
    if state == 'activate':
        controller.is_activated = True
        controller.save()
        _, return_str = daemon.controller_activate(unique_id)
        return return_str
    elif state == 'deactivate':
        controller.is_activated = False
        controller.save()
        _, return_str = daemon.controller_deactivate(unique_id)
        return return_str

WIDGET_INFORMATION = {
    'widget_name_unique': 'AoT_controller_act_deact',
    'widget_name': 'AoT 컨트롤러 스위치',
    'widget_library': '',
    'no_class': True,

    'message': '컨트롤러를 켜고 끌 수 있는 스위치.',

    'widget_width': 24,
    'widget_height': 5,

    'endpoints': [
        ("/controller_state/<unique_id>", "controller_state", controller_state, ["GET"]),
        ("/controller_activate_deactivate/<unique_id>/<state>", "controller_activate_deactivate", controller_activate_deactivate, ["GET"])
    ],

    'custom_options': [
        {
            'id': 'controller',
            'type': 'select_device',
            'default_value': '',
            'options_select': [
                'Input',
                'Function',
                'Conditional',
                'Trigger'
                # PID, CustomController 등은 필요시 확장 가능
            ],
            'name': lazy_gettext('컨트롤러'),
            'phrase': lazy_gettext('컨트롤러를 선택하세요.')
        },
        {
            'id': 'refresh_seconds',
            'type': 'float',
            'default_value': 3.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': '{} ({})'.format(lazy_gettext("새로고침"), lazy_gettext("초")),
            'phrase': '위젯을 주기적으로 새로 고침하는 간격 (초)'
        }
    ],

    # -------------------- HEAD (CSS) --------------------
    'widget_dashboard_head': """
    """,

    # -------------------- TITLE BAR --------------------
    'widget_dashboard_title_bar': """
{%- if each_widget.name %}
  <span>{{ each_widget.name }}</span>
{%- else %}
  <span>컨트롤러 스위치</span>
{%- endif %}
""",

    # -------------------- BODY --------------------
    'widget_dashboard_body': """
  <div class="frame-aot inactive-background"
      id="frame_aot_{{each_widget.unique_id}}">
    
    <div class="row-aot-1-1">
      <div class="col-aot-1">
        <span class="prt-text" id="aot_controller_txt_{{each_widget.unique_id}}">
          대기중
        </span>
      </div>

      <div class="col-aot-2">
        <label class="btn-toggle">
          <input type="checkbox"
                 id="aot_controller_toggle_{{each_widget.unique_id}}"
                 class="btn-toggle-input"
                 name="{{widget_options['controller']}}">
          <span class="btn-toggle-slider">
            <span class="btn-toggle-thumb"></span>
          </span>
        </label>
      </div>
    </div>

  </div>
""",

    # -------------------- JAVASCRIPT --------------------
    'widget_dashboard_js': """
  function printControllerErrorAoT(wid){
    // 화면 업데이트를 제거하고, 오류를 콘솔 및 서버 로그로 전송합니다.
    console.error("AoT Controller Error on widget:", wid);
    
    // 선택사항: AJAX로 서버 로그 엔드포인트에 오류 정보를 전송
    $.ajax({
      type: "POST",
      url: "/log_error",  // 서버에 로그를 수신하는 엔드포인트 (구현 필요)
      data: JSON.stringify({
        widget: "AoT_controller",
        widget_id: wid,
        error: "(Error)"
      }),
      contentType: "application/json",
      success: function(){},
      error: function(){ console.error("Error logging failed."); }
    });
  }

  // 컨트롤러 상태 확인 (1회)
  function getControllerStateAoT(wid, dev_id){
    $.ajax({
      url: "/controller_state/" + dev_id,
      type: "GET",
      success: function(data, textStatus, jqXHR){
        if(data.status === "Error"){
          printControllerErrorAoT(wid);
        } else {
          let isActive = data.state; // data.state: true or false
          updateControllerUIAoT(wid, isActive);
        }
      },
      error: function(jqXHR, textStatus, errorThrown){
        printControllerErrorAoT(wid);
      }
    });
  }

  // UI 갱신 (토글/배경색/문구)
  function updateControllerUIAoT(wid, isActive){
    let toggler = document.getElementById("aot_controller_toggle_"+wid);
    let contDiv = document.getElementById("frame_aot_"+wid);
    let stateSpan = document.getElementById("aot_controller_txt_"+wid);
    
    if(!toggler || !contDiv || !stateSpan) return;

    contDiv.classList.remove("pause-background",
                            "active-background",
                            "inactive-background");

    if(isActive){
      toggler.checked = true;
      contDiv.classList.add("active-background");
      stateSpan.innerHTML = "작동중";
    } else {
      toggler.checked = false;
      contDiv.classList.add("inactive-background");
      stateSpan.innerHTML = "대기중";
    }
  }

// 컨트롤러 On/Off
function setControllerStateAoT(dev_id, newState, wid){
  $.ajax({
    url: "/controller_activate_deactivate/"+dev_id+"/"+newState,
    type: "GET",
    success: function(res){
      // Toastr 메시지 제거됨
      // (원하면 console.log로 대체)
      console.log("Controller set success:", res);

      // 명령 후 재확인 (1회)
      getControllerStateAoT(wid, dev_id);
    },
    error: function(jqXHR, textStatus, errorThrown){
      console.error("Controller set error:", textStatus, errorThrown);
      printControllerErrorAoT(wid);
    }
  });
}

// ---------------------- 복원된 "주기적 상태 갱신" 로직 ----------------------
function repeatControllerStateAoT(wid, dev_id, refSec){
  // refresh_seconds <= 0이면 자동 갱신 X
  if(!refSec || refSec <= 0){
    console.log("[AoT Controller] Auto-refresh disabled for widget:", wid);
    return;
  }

  console.log("[AoT Controller] Auto-refresh every", refSec, "seconds (widget:", wid, ")");
  setInterval(function(){
    getControllerStateAoT(wid, dev_id);
  }, refSec * 1000);
}
""",

    # -------------------- JS READY --------------------
    'widget_dashboard_js_ready': """
  $('#frame_aot_{{widget.unique_id}} .btn-toggle-input')
    .off('change')
    .on('change', function(){
      let wid = this.id.replace('aot_controller_toggle_', '');
      let dev_id = $(this).attr('name');
      let isOn = $(this).is(':checked');

      if(!dev_id){
        console.error("No Controller ID found for widget:", wid);
        return;
      }

      let action = isOn ? "activate" : "deactivate";
      setControllerStateAoT(dev_id, action, wid);
  });
""",

    # -------------------- JS READY END --------------------
    'widget_dashboard_js_ready_end': """
  $('#aot_controller_toggle_{{each_widget.unique_id}}')
  .attr('name', '{{widget_options['controller']}}');

  getControllerStateAoT('{{each_widget.unique_id}}', '{{widget_options['controller']}}');

  repeatControllerStateAoT(
    '{{each_widget.unique_id}}',
    '{{widget_options['controller']}}',
    {{widget_options['refresh_seconds']}}
  );
"""
}
