import pandas as pd

from detector import (
    detect_buy_alert,
    detect_watch_entry,
    detect_watch_exit,
    should_set_rsi_30_flag
)


def make_initial_state() -> dict:
    """새 종목 등록 시 초기 state dict 반환 (spec §4)."""
    return {
        "state": "IDLE",
        "rsi_30_crossed_up": False,
        "entered_at": None,
        "alerted_at": None,
        "last_5m_ts": None   # 마지막으로 Entry 레이어를 평가한 5분봉 timestamp (중복 방지용)
    }


def process_symbol(
    symbol: str,
    state: dict,
    df_30m: pd.DataFrame,
    nasdaq_30m: pd.DataFrame,
    df_5m: pd.DataFrame,
    nasdaq_5m: pd.DataFrame
) -> tuple[dict, str | None]:
    """한 종목의 FSM을 한 틱 진행한다.

    매 1분 폴링마다 호출되며, 상태 전이가 발생하면 new_state에 반영한다.
    WATCH → ALERTED 전이가 일어나면 alert_message를 반환하고, 아니면 None을 반환한다.
    """
    new_state = state.copy()
    alert = None

    # ── 1단계: rsi_30_crossed_up 플래그 갱신 ───────────────────────────────
    # 플래그가 아직 False일 때만 체크. 한 번 True가 되면 IDLE 복귀 전까지 유지.
    if not new_state["rsi_30_crossed_up"]:
        if should_set_rsi_30_flag(df_30m):
            new_state["rsi_30_crossed_up"] = True

    current = new_state["state"]

    # ── 2단계: WATCH/ALERTED → IDLE 이탈 체크 ────────────────────────────
    if current in ("WATCH", "ALERTED"):
        if detect_watch_exit(df_30m, nasdaq_30m):
            return _reset_to_idle(new_state), alert   # 이탈하면 아래 단계 생략

    # ── 3단계: IDLE → WATCH 진입 체크 ───────────────────────────────────
    if current == "IDLE":
        if detect_watch_entry(df_30m, nasdaq_30m, new_state):
            new_state["state"] = "WATCH"
            new_state["entered_at"] = pd.Timestamp.now(tz="UTC")

    # ── 4단계: WATCH → ALERTED 매수 알림 (5분봉 마감 시에만) ─────────────
    if new_state["state"] == "WATCH":
        # 마지막 행(형성 중 봉)을 제외하고 마감된 봉만 사용
        df_5m_closed = df_5m.iloc[:-1]
        nasdaq_5m_closed = nasdaq_5m.iloc[:-1]
        latest_5m_ts = df_5m_closed.index[-1]

        # 이전 폴링에서 이미 같은 마감봉을 평가했으면 건너뜀 (중복 알림 방지)
        if latest_5m_ts != new_state["last_5m_ts"]:
            new_state["last_5m_ts"] = latest_5m_ts

            if detect_buy_alert(df_5m_closed, nasdaq_5m_closed):
                new_state["state"] = "ALERTED"
                new_state["alerted_at"] = pd.Timestamp.now(tz="UTC")
                bar = df_5m_closed.iloc[-1]
                alert = (
                    f"<b>[매수 알림] {symbol}</b>\n"
                    f"시각: {latest_5m_ts}\n"
                    f"5분봉 종가: {float(bar['close']):,.2f}"
                )

    return new_state, alert


def _reset_to_idle(state: dict) -> dict:
    """WATCH/ALERTED → IDLE 전이 시 state를 초기화한다 (spec §5.2).

    last_5m_ts 는 유지한다 — 이전에 평가한 봉을 IDLE 복귀 후 재진입 시 다시 평가하지 않으려면
    이 값이 남아 있어야 한다. (다음 5분봉이 올 때까지 자동 대기)
    """
    return {
        "state": "IDLE",
        "rsi_30_crossed_up": False,   # spec: 이탈 시 플래그 리셋
        "entered_at": None,
        "alerted_at": None,
        "last_5m_ts": state.get("last_5m_ts")
    }
