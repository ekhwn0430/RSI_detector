"""
백테스트 하네스 (spec §6).

사용법:
    df_1m        = get_candles("005930", "1m", 2000)   # 종목 1분봉
    df_1m_nasdaq = get_candles("QQQ",    "1m", 2000)   # NASDAQ 1분봉
    trades = run_backtest("005930", df_1m, df_1m_nasdaq)
    for t in trades:
        print(t)

주의: 매 1분봉마다 전체 데이터를 리샘플링하므로 데이터가 클수록 느려진다.
    장기 백테스트는 이 구조를 최적화할 필요가 있다.
"""
import logging
from typing import Any

import pandas as pd

from config import BACKTEST_WARMUP_BARS
from detector import detect_paper_exit
from fsm import make_initial_state, process_symbol

logger = logging.getLogger(__name__)


def _resample(df_1m: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """1분봉을 minutes 단위로 리샘플링 (data_loader._resample과 동일 규칙)."""
    return (
        df_1m.resample(f"{minutes}min")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["open", "high", "low", "close"])
    )


def run_backtest(
    symbol: str,
    df_1m: pd.DataFrame,
    df_1m_nasdaq: pd.DataFrame,
    warmup_bars: int = BACKTEST_WARMUP_BARS,
) -> list[dict[str, Any]]:
    """1분봉 데이터를 시간순으로 재생해 FSM을 돌리고 알림·수익률을 기록한다.

    Args:
        symbol:        종목 심볼 (로그·결과 기록용)
        df_1m:         종목 1분봉 (timestamp 오름차순 인덱스)
        df_1m_nasdaq:  NASDAQ 1분봉 (같은 기간, 같은 인덱스 형식)
        warmup_bars:   FSM 평가 시작 전 누적할 최소 1분봉 수

    Returns:
        trade 기록 list. 알림 1건당 dict 1개이며, paper trading 진·청산 정보를 포함한다.
        [
            {
            "symbol":       str,
            "alert_time":   Timestamp,   # 매수 알림 발생 시각 (1m 기준)
            "entry_time":   Timestamp,   # 진입 5분봉 마감 시각
            "entry_price":  float,
            "exit_time":    Timestamp | None,
            "exit_price":   float | None,
            "return_pct":   float | None,
            "exit_reason":  "signal" | "forced_idle" | "backtest_end",
            },
        ]
    """
    state = make_initial_state()
    trades: list[dict[str, Any]] = []
    paper: dict | None = None  # 현재 열려 있는 가상 포지션

    for i in range(warmup_bars, len(df_1m)):
        # 현재 틱까지만 보이는 슬라이스 (미래 데이터를 차단해 lookahead bias 방지)
        w_sym = df_1m.iloc[: i + 1]
        w_nas = df_1m_nasdaq.iloc[: i + 1]

        df_30m     = _resample(w_sym, 30)
        df_5m      = _resample(w_sym, 5)
        nasdaq_30m = _resample(w_nas, 30)
        nasdaq_5m  = _resample(w_nas, 5)

        # RSI·MA 계산에 봉이 부족하면 스킵 (워밍업 직후 경계 방어)
        if len(df_30m) < 2 or len(df_5m) < 2:
            continue

        # ── FSM 한 틱 진행 ───────────────────────────────────────────────
        new_state, alert = process_symbol(
            symbol, state, df_30m, nasdaq_30m, df_5m, nasdaq_5m
        )
        state = new_state

        # ── 매수 알림 → paper 포지션 진입 ───────────────────────────────
        if alert and paper is None:
            # 진입가 = 알림을 유발한 마감 5분봉의 종가
            df_5m_closed = df_5m.iloc[:-1]
            entry_price  = float(df_5m_closed.iloc[-1]["close"])
            entry_time   = df_5m_closed.index[-1]
            paper = {
                "symbol":      symbol,
                "alert_time":  df_1m.index[i],
                "entry_time":  entry_time,
                "entry_price": entry_price,
            }
            logger.info(f"[{symbol}] 알림 @ {entry_time}  진입가={entry_price}")

        # ── paper 포지션이 열려 있는 경우 청산 조건 체크 ─────────────────
        if paper is not None:
            df_5m_closed = df_5m.iloc[:-1]

            if state["state"] == "IDLE":
                # Signal 이탈로 FSM이 IDLE로 전이됨 → 강제 청산
                _close_paper(trades, paper, df_5m_closed, "forced_idle")
                paper = None

            elif len(df_5m_closed) >= 2 and detect_paper_exit(df_5m_closed):
                # Paper exit 조건 충족 → 청산
                _close_paper(trades, paper, df_5m_closed, "signal")
                paper = None

    # ── 백테스트 기간 종료 시 미청산 포지션 강제 마감 ──────────────────
    if paper is not None:
        df_5m_final = _resample(df_1m, 5).iloc[:-1]
        _close_paper(trades, paper, df_5m_final, "backtest_end")

    return trades


def _close_paper(
    trades: list,
    paper: dict,
    df_5m_closed: pd.DataFrame,
    reason: str,
) -> None:
    """paper 포지션을 청산하고 결과를 trades 리스트에 추가하는 내부 헬퍼."""
    exit_price  = float(df_5m_closed.iloc[-1]["close"])
    exit_time   = df_5m_closed.index[-1]
    return_pct  = (exit_price - paper["entry_price"]) / paper["entry_price"] * 100

    record = {
        **paper,
        "exit_time":   exit_time,
        "exit_price":  exit_price,
        "return_pct":  round(return_pct, 2),
        "exit_reason": reason,
    }
    trades.append(record)
    logger.info(
        f"[{paper['symbol']}] 청산({reason}) @ {exit_time}"
        f"  청산가={exit_price}  수익률={return_pct:.2f}%"
    )
