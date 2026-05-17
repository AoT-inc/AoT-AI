# coding=utf-8
"""
_runtime_state_mixin.py — RuntimeStateMixin: PI state persistence (P2-5).

P0 강화 (2026-05-16):
- 저장 실패 시 짧은 재시도 (transient SQLite lock 대응)
- 최종 실패 시 CRITICAL 로그 + decision_log 채널 기록
  → 사용자가 "왜 재시작 후 PI 적분이 사라졌나" 추적 가능
"""

import json
import time

from aot.config import AOT_DB_PATH
from aot.databases.models import FunctionRuntimeState
from aot.databases.utils import session_scope
from aot.functions.utils.env_control import (
    CH_RUNTIME_STATE_FAIL,
    write_decision_log,
)


class RuntimeStateMixin:
    """Mixin: load/save CoordinatorState to FunctionRuntimeState DB table."""

    _SAVE_RETRY_COUNT = 3
    _SAVE_RETRY_BACKOFF_SEC = 0.3

    def _load_runtime_state(self):
        """DB에서 PI 상태를 읽어 CoordinatorState 를 복원한다."""
        try:
            with session_scope(AOT_DB_PATH) as sess:
                row = sess.query(FunctionRuntimeState).filter(
                    FunctionRuntimeState.function_id == self.unique_id
                ).first()
                if row is None:
                    return
                integral      = json.loads(row.integral_json    or '{}')
                prev_commands = json.loads(row.prev_cmds_json   or '{}')
                active_vars   = json.loads(row.active_vars_json or '{}')
                last_ts       = row.last_cycle_ts or 0.0
                sess.expunge_all()

            self._coord_state.integral      = integral
            self._coord_state.prev_commands = prev_commands
            self._coord_state.active_vars   = active_vars
            self._last_cycle_ts             = last_ts
            self.logger.info(
                'EnvCoordinator: PI 상태 복원 — integral=%s prev_cmds=%s',
                integral, prev_commands)
        except Exception:
            self.logger.exception(
                'EnvCoordinator: runtime state 로드 실패 — 초기 상태로 시작')

    def _save_runtime_state(self):
        """CoordinatorState 를 DB에 upsert 한다.

        Transient 실패(SQLite busy 등)에 짧은 재시도. 최종 실패 시
        CRITICAL 로그 + decision_log 기록 — 사용자가 재시작 후 PI 불연속
        원인을 추적할 수 있게 한다.
        """
        last_exc = None
        for attempt in range(self._SAVE_RETRY_COUNT):
            try:
                now = time.time()
                with session_scope(AOT_DB_PATH) as sess:
                    row = sess.query(FunctionRuntimeState).filter(
                        FunctionRuntimeState.function_id == self.unique_id
                    ).first()
                    if row is None:
                        row = FunctionRuntimeState(function_id=self.unique_id)
                        sess.add(row)
                    row.integral_json    = json.dumps(self._coord_state.integral)
                    row.prev_cmds_json   = json.dumps(self._coord_state.prev_commands)
                    row.active_vars_json = json.dumps(
                        {k: bool(v) for k, v in self._coord_state.active_vars.items()})
                    row.last_cycle_ts    = self._last_cycle_ts
                    row.updated_at       = now
                    sess.commit()
                # 성공 시 누적 실패 카운터는 다음 실패까지 보존(외부 관찰자가
                # rate를 계산할 수 있도록 누적값만 갱신)
                return
            except Exception as exc:
                last_exc = exc
                self.logger.warning(
                    'EnvCoordinator: runtime state 저장 실패 (시도 %d/%d): %s',
                    attempt + 1, self._SAVE_RETRY_COUNT, exc)
                if attempt < self._SAVE_RETRY_COUNT - 1:
                    time.sleep(self._SAVE_RETRY_BACKOFF_SEC * (attempt + 1))

        # 최종 실패: CRITICAL + decision_log
        self._runtime_state_fail_count = (
            getattr(self, '_runtime_state_fail_count', 0) + 1)
        self.logger.critical(
            'EnvCoordinator: runtime state 저장 최종 실패 (%d회 누적) — '
            '재시작 시 PI 적분/이전 명령 손실 위험. 마지막 예외: %s',
            self._runtime_state_fail_count, last_exc)
        try:
            write_decision_log(
                self.unique_id, 'runtime_state_save_fail',
                CH_RUNTIME_STATE_FAIL, float(self._runtime_state_fail_count))
        except Exception:
            # 로그 채널 자체 실패는 무시 — 본 사이클 진행을 막지 않는다.
            pass
