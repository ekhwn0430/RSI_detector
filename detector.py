import pandas as pd

from config import (
    ENTRY_BREAKOUT_BARS,
    ENTRY_RSI_LEVEL,
    ENTRY_VOLUME_MA_BARS,
    MA_PERIOD,
    PAPER_EXIT_BREAKDOWN_BARS,
    PAPER_EXIT_RSI_LEVEL,
    RSI_PERIOD,
    SIGNAL_RSI_ENTRY_LEVEL,
    SIGNAL_RSI_EXIT_LEVEL,
    SIGNAL_RSI_FLAG_LEVEL
)
from indicators import ma, rsi, slope


def should_set_rsi_30_flag(df_30m: pd.DataFrame) -> bool:
    """30분봉 RSI가 SIGNAL_RSI_FLAG_LEVEL(=30)을 상향 돌파했으면 True 반환.

    FSM이 이 결과를 보고 state['rsi_30_crossed_up']을 True로 셋한다.
    """
    rsi_vals = rsi(df_30m["close"], RSI_PERIOD)
    prev = rsi_vals.iloc[-2]
    curr = rsi_vals.iloc[-1]
    return prev <= SIGNAL_RSI_FLAG_LEVEL and curr > SIGNAL_RSI_FLAG_LEVEL


def detect_watch_entry(
    df_30m: pd.DataFrame, nasdaq_30m: pd.DataFrame, state: dict
) -> bool:
    """Signal 레이어 — IDLE → WATCH 진입 여부 판단 (spec §5.1).

    세 조건 모두 충족해야 True.
    """
    # 조건 1: 과거에 RSI 30 상향 돌파 이력이 있어야 함
    if not state["rsi_30_crossed_up"]:
        return False

    # 조건 2: 30분봉 RSI가 35를 상향 돌파
    rsi_vals = rsi(df_30m["close"], RSI_PERIOD)
    prev = rsi_vals.iloc[-2]
    curr = rsi_vals.iloc[-1]
    rsi_crossed = prev <= SIGNAL_RSI_ENTRY_LEVEL and curr > SIGNAL_RSI_ENTRY_LEVEL

    # 조건 3: NASDAQ 30분봉 20MA 기울기 양수
    nasdaq_slope = slope(ma(nasdaq_30m["close"], MA_PERIOD))
    nasdaq_bullish = nasdaq_slope.iloc[-1] > 0

    return rsi_crossed and nasdaq_bullish


def detect_watch_exit(df_30m: pd.DataFrame, nasdaq_30m: pd.DataFrame) -> bool:
    """Signal 레이어 — WATCH/ALERTED → IDLE 이탈 여부 판단 (spec §5.2).

    두 조건 중 하나라도 충족하면 True.
    """
    # 조건 A: 30분봉 RSI가 30을 하향 돌파 (hysteresis — 진입 35, 이탈 30)
    rsi_vals = rsi(df_30m["close"], RSI_PERIOD)
    prev = rsi_vals.iloc[-2]
    curr = rsi_vals.iloc[-1]
    rsi_dropped = prev >= SIGNAL_RSI_EXIT_LEVEL and curr < SIGNAL_RSI_EXIT_LEVEL

    # 조건 B: NASDAQ 30분봉 20MA 기울기 음수
    nasdaq_slope = slope(ma(nasdaq_30m["close"], MA_PERIOD))
    nasdaq_bearish = nasdaq_slope.iloc[-1] < 0

    return rsi_dropped or nasdaq_bearish


def detect_buy_alert(df_5m: pd.DataFrame, nasdaq_5m: pd.DataFrame) -> bool:
    """Entry 레이어 — WATCH → ALERTED 매수 알림 여부 판단 (spec §5.3).

    네 조건 모두 충족해야 True.
    ※ 반드시 5분봉 마감 직후에 호출할 것 (df_5m의 마지막 행 = 막 마감된 봉).
    """
    # 조건 1: 5분봉 RSI가 35를 상향 돌파
    rsi_vals = rsi(df_5m["close"], RSI_PERIOD)
    prev = rsi_vals.iloc[-2]
    curr = rsi_vals.iloc[-1]
    rsi_crossed = prev <= ENTRY_RSI_LEVEL and curr > ENTRY_RSI_LEVEL

    # 조건 2: 현재 봉 close > 직전 ENTRY_BREAKOUT_BARS봉의 max(high)
    # iloc[-1]이 현재 봉, iloc[-(BREAKOUT+1):-1]이 직전 N봉
    prev_highs = df_5m["high"].iloc[-(ENTRY_BREAKOUT_BARS + 1):-1]
    high_breakout = df_5m["close"].iloc[-1] > prev_highs.max()

    # 조건 3: 현재 봉 volume > 직전 ENTRY_VOLUME_MA_BARS봉의 평균 (현재 봉 제외)
    prev_volumes = df_5m["volume"].iloc[-(ENTRY_VOLUME_MA_BARS + 1):-1]
    volume_breakout = df_5m["volume"].iloc[-1] > prev_volumes.mean()

    # 조건 4: NASDAQ 5분봉 20MA 기울기 양수
    nasdaq_slope = slope(ma(nasdaq_5m["close"], MA_PERIOD))
    nasdaq_bullish = nasdaq_slope.iloc[-1] > 0

    return rsi_crossed and high_breakout and volume_breakout and nasdaq_bullish


def detect_paper_exit(df_5m: pd.DataFrame) -> bool:
    """Paper Trading 청산 조건 (spec §5.4). 알림 없이 수익률 추적용으로만 사용.

    두 조건 중 하나라도 충족하면 True.
    """
    # 조건 A: 5분봉 RSI가 35를 하향 돌파
    rsi_vals = rsi(df_5m["close"], RSI_PERIOD)
    prev = rsi_vals.iloc[-2]
    curr = rsi_vals.iloc[-1]
    rsi_dropped = prev >= PAPER_EXIT_RSI_LEVEL and curr < PAPER_EXIT_RSI_LEVEL

    # 조건 B: 현재 봉 close < 직전 PAPER_EXIT_BREAKDOWN_BARS봉의 min(low)
    prev_lows = df_5m["low"].iloc[-(PAPER_EXIT_BREAKDOWN_BARS + 1):-1]
    low_breakdown = df_5m["close"].iloc[-1] < prev_lows.min()

    return rsi_dropped or low_breakdown
