# coding=utf-8
#
#  actuator_bidirectional.py - 멀티채널 액츄에이터 정/역 제어 Function
#
import json
import time
import traceback

from aot.config_translations import TRANSLATIONS
from aot.databases.models import CustomController, FunctionChannel
from aot.functions.base_function import AbstractFunction
from aot.aot_client import DaemonControl
from aot.aot_flask.utils.utils_general import (
    custom_channel_options_return_json, delete_entry_with_id)
from aot.utils.constraints_pass import constraints_pass_positive_value
from aot.utils.database import db_retrieve_table_daemon
from aot.utils.functions import parse_function_information
from aot.utils.influx import write_influxdb_value

STATE_STOP = 0
STATE_FORWARD = 1
STATE_REVERSE = 2
STATE_UNKNOWN = -1

STATE_LABELS = {
    STATE_STOP: 'stop',
    STATE_FORWARD: 'forward',
    STATE_REVERSE: 'reverse',
    STATE_UNKNOWN: 'unknown',
}


# ═══════════════════════════════════════════════════════════════
#  execute_at_creation — Function 최초 등록 시 기본 채널 1개 생성
# ═══════════════════════════════════════════════════════════════
def execute_at_creation(error, new_func, dict_functions=None):
    try:
        dict_controllers = parse_function_information()

        new_channel = FunctionChannel()
        new_channel.name = "Channel 1"
        new_channel.function_id = new_func.unique_id
        new_channel.channel = 0

        error, custom_options = custom_channel_options_return_json(
            error, dict_controllers, None,
            new_func.unique_id, 0,
            device=new_func.device, use_defaults=True)
        custom_options_dict = json.loads(custom_options)
        custom_options_dict["name"] = new_channel.name
        new_channel.custom_options = json.dumps(custom_options_dict)
        new_channel.save()

    except Exception:
        error.append("execute_at_creation() Error: {}".format(traceback.print_exc()))

    return error, new_func


# ═══════════════════════════════════════════════════════════════
#  execute_at_modification — channel_count 변경 시 채널 추가/삭제
# ═══════════════════════════════════════════════════════════════
def execute_at_modification(
        messages,
        mod_function,
        request_form,
        custom_options_dict_presave,
        custom_options_channels_dict_presave,
        custom_options_dict_postsave,
        custom_options_channels_dict_postsave):
    page_refresh = False

    try:
        dict_controllers = parse_function_information()

        channels = FunctionChannel.query.filter(
            FunctionChannel.function_id == mod_function.unique_id)

        target = int(custom_options_dict_postsave.get('channel_count', 1))
        target = max(1, min(target, 8))
        current = channels.count()

        if target > current:
            page_refresh = True
            for idx in range(current, target):
                new_channel = FunctionChannel()
                new_channel.name = f"Channel {idx + 1}"
                new_channel.function_id = mod_function.unique_id
                new_channel.channel = idx

                messages["error"], ch_opts = custom_channel_options_return_json(
                    messages["error"], dict_controllers, request_form,
                    mod_function.unique_id, idx,
                    device=mod_function.device, use_defaults=True)
                ch_dict = json.loads(ch_opts)
                ch_dict["name"] = new_channel.name
                new_channel.custom_options = json.dumps(ch_dict)
                new_channel.save()

        elif target < current:
            page_refresh = True
            for idx, each_channel in enumerate(channels.all()):
                if idx >= target:
                    delete_entry_with_id(FunctionChannel, each_channel.unique_id)

    except Exception:
        messages["error"].append(
            "execute_at_modification() Error: {}".format(traceback.print_exc()))

    return (messages,
            mod_function,
            custom_options_dict_postsave,
            custom_options_channels_dict_postsave,
            page_refresh)


# ═══════════════════════════════════════════════════════════════
#  FUNCTION_INFORMATION
# ═══════════════════════════════════════════════════════════════
FUNCTION_INFORMATION = {
    'function_name_unique': 'ACTUATOR_BIDIRECTIONAL',
    'function_name': '액츄에이터 정/역 제어 (멀티채널)',
    'function_name_short': 'Actuator Bidirectional',

    'message': (
        '액츄에이터(모터, 밸브 등)의 정방향/역방향 동작을 제어하는 멀티채널 Function입니다.<br>'
        '채널마다 독립적인 정/역 Output과 상태 감지 Measurement를 지정할 수 있습니다.<br>'
        '외부 시스템(타 PLC, MQTT 등)에서 장치를 작동시킨 경우에도 실제 상태를 감지합니다.<br>'
        '리미트 감지는 State Measurement를 공유하므로 별도 인터락 설정이 불필요합니다.<br>'
        '<b>채널 수 변경 후 저장하면 채널이 자동 추가/삭제되고 페이지가 새로고침됩니다.</b>'
    ),

    'options_enabled': [
        'custom_options',
        'function_status'
    ],
    'options_disabled': ['measurements_select'],

    'execute_at_creation': execute_at_creation,
    'execute_at_modification': execute_at_modification,

    # ── 전역 설정 ────────────────────────────────────────────────
    'custom_options': [
        {
            'id': 'channel_count',
            'type': 'integer',
            'default_value': 1,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': '채널 수 (1~8)',
            'phrase': '사용할 채널 수. 저장 시 채널이 자동으로 추가/삭제됩니다.'
        },
        {
            'id': 'loop_period',
            'type': 'float',
            'default_value': 5.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': '루프 주기 (초)',
            'phrase': '상태 점검 및 제어 루프 실행 주기'
        },
        {
            'id': 'mismatch_action',
            'type': 'select',
            'default_value': 'alert',
            'required': True,
            'options_select': [
                ('alert', 'Alert — 로그/이벤트 기록, 동작 유지 (기본)'),
                ('force_stop', 'Force Stop — 즉시 양쪽 Output OFF'),
                ('resync', 'Resync — detected 상태를 commanded로 반영'),
                ('ignore', 'Ignore — 불일치 무시'),
            ],
            'name': '상태 불일치 시 동작',
            'phrase': 'commanded_state(명령)와 detected_state(감지)가 다를 때 취할 동작'
        },
    ],

    # ── 채널별 설정 (FunctionChannel 기반, 동적 N개) ───────────────
    'custom_channel_options': [
        # 기본 설정
        {
            'id': 'output_forward',
            'type': 'select_measurement_channel',
            'default_value': '',
            'required': False,
            'options_select': ['Output_Channels_Measurements'],
            'name': '정방향(Forward) Output',
            'phrase': '정회전 동작 시 켜질 Output 채널'
        },
        {
            'id': 'output_reverse',
            'type': 'select_measurement_channel',
            'default_value': '',
            'required': False,
            'options_select': ['Output_Channels_Measurements'],
            'name': '역방향(Reverse) Output',
            'phrase': '역회전 동작 시 켜질 Output 채널'
        },
        {
            'id': 'state_source',
            'type': 'select',
            'default_value': 'none',
            'required': True,
            'options_select': [
                ('none', 'None — 명령 상태만 추적'),
                ('measurement', 'Measurement — Input / MQTT Input 등으로 실제 상태 감지'),
            ],
            'name': '상태 감지 소스',
            'phrase': '장치의 실제 동작 상태를 감지하는 방법 선택'
        },
        {
            'id': 'state_measurement',
            'type': 'select_measurement',
            'default_value': '',
            'required': False,
            'options_select': ['Input', 'Function', 'Output'],
            'name': '상태 Measurement',
            'phrase': '상태 감지에 사용할 Measurement (MQTT Input 포함). state_source=Measurement일 때만 적용'
        },
        {
            'id': 'state_meas_max_age',
            'type': 'integer',
            'default_value': 60,
            'required': False,
            'constraints_pass': constraints_pass_positive_value,
            'name': '상태 Measurement Max Age (초)',
            'phrase': '상태 Measurement 유효 최대 경과 시간'
        },
        # 고급 설정
        {
            'type': 'message',
            'default_value': '▼ Advanced'
        },
        {
            'id': 'state_fwd_threshold',
            'type': 'float',
            'default_value': 1.0,
            'required': False,
            'name': 'Forward 상태 임계값 (>=)',
            'phrase': (
                'Measurement 값 ≥ 이 값이면 장치가 정방향 동작 중으로 판정.\n'
                '예) MQTT 페이로드 1=정회전 → 1.0 입력'
            )
        },
        {
            'id': 'state_rev_threshold',
            'type': 'float',
            'default_value': -1.0,
            'required': False,
            'name': 'Reverse 상태 임계값 (<=)',
            'phrase': (
                'Measurement 값 ≤ 이 값이면 장치가 역방향 동작 중으로 판정.\n'
                '예) MQTT 페이로드 -1=역회전 → -1.0 입력'
            )
        },
        {
            'id': 'fwd_limit_threshold',
            'type': 'float',
            'default_value': 0.0,
            'required': False,
            'name': 'Forward 리미트 임계값 (>=, 0=비활성)',
            'phrase': (
                'State Measurement 값 ≥ 이 값이면 정방향 리미트 도달로 판단하고 자동 정지.\n'
                '0이면 비활성. 예) 위치센서 100%=리미트 → 100.0 입력'
            )
        },
        {
            'id': 'rev_limit_threshold',
            'type': 'float',
            'default_value': 0.0,
            'required': False,
            'name': 'Reverse 리미트 임계값 (<=, 0=비활성)',
            'phrase': (
                'State Measurement 값 ≤ 이 값이면 역방향 리미트 도달로 판단하고 자동 정지.\n'
                '0이면 비활성. 예) 위치센서 0%=리미트 → 0.0 입력'
            )
        },
        {
            'id': 'dead_time',
            'type': 'float',
            'default_value': 0.5,
            'required': False,
            'name': 'Dead Time (초)',
            'phrase': (
                '방향 전환(Forward↔Reverse) 시 양쪽 Output을 동시에 OFF로 유지할 시간(초).\n'
                '모터·릴레이 보호용. 0이면 비활성'
            )
        },
        {
            'id': 'max_run_time',
            'type': 'float',
            'default_value': 0.0,
            'required': False,
            'name': '최대 동작 시간 (초, 0=비활성)',
            'phrase': (
                '동작 시작 후 이 시간(초)을 초과하면 자동 정지.\n'
                '센서 오작동 등 비정상 상황의 안전 타임아웃. 0이면 비활성'
            )
        },
    ],

    # ── 채널별 수동 제어 버튼 (최대 8채널 × 3버튼, 비활성 채널은 응답만 거부) ──
    'custom_commands': (lambda cmds: cmds)(
        [
            {
                'type': 'message',
                'default_value': '각 채널을 직접 제어합니다. 비활성 채널의 버튼은 무시됩니다.'
            },
            {
                'id': 'cmd_stop_all',
                'type': 'button',
                'wait_for_return': True,
                'name': '■■ Stop All',
                'phrase': '모든 활성 채널 즉시 강제 정지'
            },
        ] + [
            item
            for n in range(8)
            for item in [
                {
                    'type': 'message',
                    'default_value': f'── Channel {n + 1} ──'
                },
                {
                    'id': f'ch{n}_cmd_forward',
                    'type': 'button',
                    'wait_for_return': True,
                    'name': f'Ch{n + 1} ▶ Forward',
                    'phrase': f'Channel {n + 1} 정방향 동작 시작'
                },
                {
                    'id': f'ch{n}_cmd_reverse',
                    'type': 'button',
                    'wait_for_return': True,
                    'name': f'Ch{n + 1} ◀ Reverse',
                    'phrase': f'Channel {n + 1} 역방향 동작 시작'
                },
                {
                    'id': f'ch{n}_cmd_stop',
                    'type': 'button',
                    'wait_for_return': True,
                    'name': f'Ch{n + 1} ■ Stop',
                    'phrase': f'Channel {n + 1} 정지'
                },
            ]
        ]
    )
}


# ═══════════════════════════════════════════════════════════════
#  런타임 채널 상태
# ═══════════════════════════════════════════════════════════════
class _ChState:
    __slots__ = (
        'commanded', 'detected', 'run_start_time',
        'direction_changes', 'dead_time_end',
        'fwd_device_id', 'fwd_channel',
        'rev_device_id', 'rev_channel',
        'state_device_id', 'state_measurement_id',
    )

    def __init__(self):
        self.commanded = STATE_STOP
        self.detected = STATE_UNKNOWN
        self.run_start_time = None
        self.direction_changes = 0
        self.dead_time_end = 0.0
        self.fwd_device_id = None
        self.fwd_channel = None
        self.rev_device_id = None
        self.rev_channel = None
        self.state_device_id = None
        self.state_measurement_id = None


# ═══════════════════════════════════════════════════════════════
#  CustomModule
# ═══════════════════════════════════════════════════════════════
class CustomModule(AbstractFunction):
    """멀티채널 액츄에이터 정/역 제어 Function.

    채널마다 정/역 Output 한 쌍과 상태 감지 Measurement를 독립 운용한다.
    채널 수는 channel_count 설정으로 동적 변경되며, 저장 시 FunctionChannel이 추가/삭제된다.

    @phase core
    @stability experimental
    @dependency AbstractFunction, DaemonControl, FunctionChannel, InfluxDB
    """

    def __init__(self, function, testing=False):
        super().__init__(function, testing=testing, name=__name__)

        self.control = DaemonControl()
        self.timer_loop = time.time()
        self.options_channels = {}

        # 전역 옵션 초기화
        self.channel_count = 1
        self.loop_period = 5.0
        self.mismatch_action = 'alert'

        custom_function = db_retrieve_table_daemon(
            CustomController, unique_id=self.unique_id)
        self.setup_custom_options(
            FUNCTION_INFORMATION['custom_options'], custom_function)

        # 런타임 채널 상태 (최대 8개 슬롯)
        self._ch = [_ChState() for _ in range(8)]

        if not testing:
            self.try_initialize()

    def initialize(self):
        # 채널별 옵션 로드 (FunctionChannel DB rows)
        function_channels = db_retrieve_table_daemon(
            FunctionChannel,
            entry='all',
            unique_id=self.unique_id)
        self.options_channels = self.setup_custom_channel_options_json(
            FUNCTION_INFORMATION['custom_channel_options'], function_channels)

        # 채널별 런타임 상태 초기화
        for i, opts in self.options_channels.items():
            rt = self._ch[i]
            fwd_ch_id = getattr(opts, 'output_forward_channel_id', None)
            rev_ch_id = getattr(opts, 'output_reverse_channel_id', None)
            rt.fwd_device_id = getattr(opts, 'output_forward_device_id', None)
            rt.fwd_channel = self.get_output_channel_from_channel_id(fwd_ch_id)
            rt.rev_device_id = getattr(opts, 'output_reverse_device_id', None)
            rt.rev_channel = self.get_output_channel_from_channel_id(rev_ch_id)
            rt.state_device_id = getattr(opts, 'state_measurement_device_id', None)
            rt.state_measurement_id = getattr(opts, 'state_measurement_measurement_id', None)

        self.logger.info(
            f"ActuatorBidirectional 초기화: 채널={len(self.options_channels)}, "
            f"루프={self.loop_period}s, 불일치={self.mismatch_action}")

    # ──────────────────────────────────────────────── loop
    def loop(self):
        if self.timer_loop > time.time():
            return
        while self.timer_loop < time.time():
            self.timer_loop += self.loop_period

        for i in self.options_channels:
            try:
                self._process(i)
            except Exception:
                self.logger.exception(f"Ch{i+1} 처리 오류")

    # ──────────────────────────────────────────────── per-channel logic
    def _process(self, i):
        rt = self._ch[i]
        opts = self.options_channels[i]
        lbl = f"Ch{i+1}[{getattr(opts, 'name', '')}]"

        if self._check_limit(i, rt, opts, lbl):
            return
        if self._check_timeout(i, rt, opts, lbl):
            return

        self._update_detected(i, rt, opts)

        src = getattr(opts, 'state_source', 'none')
        if src == 'measurement' and rt.detected != STATE_UNKNOWN and rt.commanded != rt.detected:
            self._handle_mismatch(i, rt, lbl)

        if time.time() >= rt.dead_time_end:
            self._apply_output(rt)

        self._record(i, 'commanded_state', rt.commanded)
        self._record(i, 'direction_changes', rt.direction_changes)

    def _check_limit(self, i, rt, opts, lbl):
        if getattr(opts, 'state_source', 'none') != 'measurement':
            return False
        if not rt.state_device_id or not rt.state_measurement_id:
            return False

        max_age = int(getattr(opts, 'state_meas_max_age', 60))
        last = self.get_last_measurement(rt.state_device_id, rt.state_measurement_id,
                                         max_age=max_age)
        if not last:
            return False

        val = float(last[1])
        fwd_lim = float(getattr(opts, 'fwd_limit_threshold', 0.0))
        rev_lim = float(getattr(opts, 'rev_limit_threshold', 0.0))

        if fwd_lim != 0.0 and rt.commanded == STATE_FORWARD and val >= fwd_lim:
            self.logger.warning(f"{lbl} Forward 리미트 (값={val:.3f} >= {fwd_lim}). 정지.")
            self._force_stop(rt)
            self._record(i, 'limit_event', 1)
            return True

        if rev_lim != 0.0 and rt.commanded == STATE_REVERSE and val <= rev_lim:
            self.logger.warning(f"{lbl} Reverse 리미트 (값={val:.3f} <= {rev_lim}). 정지.")
            self._force_stop(rt)
            self._record(i, 'limit_event', -1)
            return True

        return False

    def _check_timeout(self, i, rt, opts, lbl):
        max_t = float(getattr(opts, 'max_run_time', 0.0))
        if max_t <= 0 or rt.commanded == STATE_STOP or rt.run_start_time is None:
            return False
        elapsed = time.time() - rt.run_start_time
        if elapsed >= max_t:
            self.logger.warning(f"{lbl} 최대 동작 시간 초과 ({elapsed:.1f}s >= {max_t}s). 정지.")
            self._force_stop(rt)
            self._record(i, 'timeout_event', 1)
            return True
        return False

    def _update_detected(self, i, rt, opts):
        if getattr(opts, 'state_source', 'none') != 'measurement':
            return
        if not rt.state_device_id or not rt.state_measurement_id:
            return

        max_age = int(getattr(opts, 'state_meas_max_age', 60))
        last = self.get_last_measurement(rt.state_device_id, rt.state_measurement_id,
                                         max_age=max_age)
        if not last:
            rt.detected = STATE_UNKNOWN
            return

        val = float(last[1])
        fwd_t = float(getattr(opts, 'state_fwd_threshold', 1.0))
        rev_t = float(getattr(opts, 'state_rev_threshold', -1.0))

        rt.detected = (STATE_FORWARD if val >= fwd_t
                       else STATE_REVERSE if val <= rev_t
                       else STATE_STOP)
        self._record(i, 'detected_state', rt.detected)

    def _handle_mismatch(self, i, rt, lbl):
        cmd = STATE_LABELS[rt.commanded]
        det = STATE_LABELS[rt.detected]
        action = self.mismatch_action

        if action == 'ignore':
            return
        self._record(i, 'mismatch_event', 1)
        if action == 'alert':
            self.logger.warning(f"{lbl} 불일치: commanded={cmd}, detected={det} (동작 유지)")
        elif action == 'force_stop':
            self.logger.warning(f"{lbl} 불일치: commanded={cmd}, detected={det} → 강제 정지")
            self._force_stop(rt)
        elif action == 'resync':
            self.logger.info(f"{lbl} 불일치: resync {cmd} → {det}")
            rt.commanded = rt.detected

    def _apply_output(self, rt):
        if rt.commanded == STATE_FORWARD:
            self._on(rt.fwd_device_id, rt.fwd_channel)
            self._off(rt.rev_device_id, rt.rev_channel)
        elif rt.commanded == STATE_REVERSE:
            self._off(rt.fwd_device_id, rt.fwd_channel)
            self._on(rt.rev_device_id, rt.rev_channel)
        else:
            self._off(rt.fwd_device_id, rt.fwd_channel)
            self._off(rt.rev_device_id, rt.rev_channel)

    # ──────────────────────────────────────────────── state change
    def _set_state(self, i, new_state, source='loop'):
        rt = self._ch[i]
        opts = self.options_channels.get(i)
        if new_state == rt.commanded:
            return

        prev = rt.commanded
        dead = float(getattr(opts, 'dead_time', 0.5)) if opts else 0.5

        if prev != STATE_STOP and new_state != STATE_STOP and dead > 0:
            self._off(rt.fwd_device_id, rt.fwd_channel)
            self._off(rt.rev_device_id, rt.rev_channel)
            rt.dead_time_end = time.time() + dead

        rt.commanded = new_state
        if new_state != STATE_STOP:
            rt.run_start_time = time.time()
            if prev != new_state:
                rt.direction_changes += 1
        else:
            rt.run_start_time = None

        self.logger.info(
            f"Ch{i+1} {STATE_LABELS[prev]} → {STATE_LABELS[new_state]} (by {source})")

    def _force_stop(self, rt):
        rt.commanded = STATE_STOP
        rt.run_start_time = None
        rt.dead_time_end = 0.0
        self._off(rt.fwd_device_id, rt.fwd_channel)
        self._off(rt.rev_device_id, rt.rev_channel)

    # ──────────────────────────────────────────────── output helpers
    def _on(self, device_id, channel):
        if device_id and channel is not None:
            try:
                self.control.output_on(device_id, output_channel=channel)
            except Exception as e:
                self.logger.error(f"output_on 오류 ({device_id}): {e}")

    def _off(self, device_id, channel):
        if device_id and channel is not None:
            try:
                self.control.output_off(device_id, output_channel=channel)
            except Exception as e:
                self.logger.error(f"output_off 오류 ({device_id}): {e}")

    def _record(self, ch_idx, metric, value):
        try:
            write_influxdb_value(
                self.unique_id, unit='dimensionless',
                value=float(value), measure=metric, channel=ch_idx)
        except Exception as e:
            self.logger.debug(f"기록 오류 ch{ch_idx}/{metric}: {e}")

    # ──────────────────────────────────────────────── custom commands
    def cmd_stop_all(self, args_dict):
        for i in self.options_channels:
            self._force_stop(self._ch[i])
        return f"전체 {len(self.options_channels)}채널 강제 정지"

    def __getattr__(self, name):
        """ch{n}_cmd_forward / ch{n}_cmd_reverse / ch{n}_cmd_stop 동적 디스패치."""
        import re
        m = re.match(r'^ch(\d+)_cmd_(forward|reverse|stop)$', name)
        if not m:
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

        ch_idx = int(m.group(1))
        action = m.group(2)
        state_map = {'forward': STATE_FORWARD, 'reverse': STATE_REVERSE, 'stop': STATE_STOP}

        def _handler(args_dict, _i=ch_idx, _a=action):
            if _i not in self.options_channels:
                active = sorted(self.options_channels.keys())
                return (f"Ch{_i+1}은 비활성 채널입니다. "
                        f"활성 채널: {[i+1 for i in active]}")
            self._set_state(_i, state_map[_a], source='manual')
            return f"Ch{_i+1} → {_a}"

        return _handler

    # ──────────────────────────────────────────────── stop / status
    def stop_function(self):
        for i in self.options_channels:
            self._force_stop(self._ch[i])
        self.logger.info("ActuatorBidirectional: 전체 채널 정지 후 종료")

    def function_status(self):
        lines = [
            f"활성 채널: {len(self.options_channels)}  "
            f"루프: {self.loop_period}s  불일치: {self.mismatch_action}",
            ""
        ]
        for i, opts in self.options_channels.items():
            rt = self._ch[i]
            name = getattr(opts, 'name', f'Ch{i+1}')
            cmd = STATE_LABELS.get(rt.commanded, '?')
            det = STATE_LABELS.get(rt.detected, '?')
            src = getattr(opts, 'state_source', 'none')
            elapsed = f"  경과={time.time()-rt.run_start_time:.0f}s" if rt.run_start_time else ''
            max_t = float(getattr(opts, 'max_run_time', 0.0))
            max_str = f"  최대={max_t}s" if max_t > 0 else ''
            dead_str = '  [dead-time]' if time.time() < rt.dead_time_end else ''
            det_str = f"  detected={det}" if src == 'measurement' else ''
            lines.append(
                f"  Ch{i+1} [{name}]  commanded={cmd}{det_str}"
                f"  전환={rt.direction_changes}회{elapsed}{max_str}{dead_str}"
            )
        return {'string_status': '\n'.join(lines), 'error': []}
