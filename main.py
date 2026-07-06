"""
라이브 폴링 루프 (spec §7, §8).

실행:  python main.py
중단: Ctrl+C
"""
import logging
import signal
import sys
import time
from datetime import datetime

import pandas as pd
# rich: 터미널에 색깔 있는 표(Table)를 그려주는 라이브러리
from rich.console import Console   # 터미널 출력 담당 객체
from rich.live import Live         # 표를 제자리에서 주기적으로 갱신하는 컨텍스트
from rich.table import Table       # 표 구성 객체

from config import (
    LIVE_COUNT_30M,
    LIVE_COUNT_5M,
    NASDAQ_SYMBOL,
    POLL_INTERVAL_SEC,
    WATCHLIST,
)
from data_loader import get_candles
from fsm import make_initial_state, process_symbol
from telegram import send_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Console은 rich가 터미널에 출력할 때 쓰는 핸들. print 대신 console.print()를 쓴다.
console = Console()

# 종목별 FSM 상태 (메모리 내 유지, 재시작 시 초기화)
_states: dict[str, dict] = {}

# 종목별 가장 최근 조회된 종가 (표 출력용)
_prices: dict[str, float] = {}

# 마지막으로 폴링이 완료된 시각 (표 하단에 표시)
_last_poll: datetime | None = None


# ── 상태 테이블 ───────────────────────────────────────────────────────────────

# FSM 상태별 글자 색상. IDLE은 흐리게, WATCH는 노란색 굵게, ALERTED는 초록 굵게
_STATE_STYLE = {
    "IDLE":    "dim white",
    "WATCH":   "bold yellow",
    "ALERTED": "bold green",
}


def _build_table() -> Table:
    """현재 watchlist 전 종목의 상태를 rich Table 객체로 만들어 반환한다.

    Live 컨텍스트가 이 함수를 매초 호출해서 표를 다시 그린다.
    """
    now_str  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    poll_str = _last_poll.strftime("%H:%M:%S") if _last_poll else "-"

    table = Table(
        title=f"RSI 알림봇  |  현재 시각: {now_str}  |  마지막 폴링: {poll_str}",
        show_lines=True,
    )

    # 열 정의: 각 열의 이름, 정렬, 최소 너비를 지정
    table.add_column("심볼",       style="cyan",  justify="center", min_width=8)
    table.add_column("FSM 상태",   justify="center", min_width=10)
    # RSI30 돌파: rsi_30_crossed_up 플래그. True면 O, False면 X
    table.add_column("RSI30 돌파", justify="center", min_width=10)
    # 최근 종가: 마지막으로 조회한 5분봉의 종가 (형성 중인 봉 포함)
    table.add_column("최근 종가",  justify="right",  min_width=10)
    # 알림 시각: ALERTED 상태가 된 시각. 아직 알림이 없으면 -
    table.add_column("알림 시각",  justify="center", min_width=18)

    for symbol in WATCHLIST:
        state = _states.get(symbol)

        # 아직 첫 폴링 전이라 state가 없는 경우 — 빈 행으로 표시
        if state is None:
            table.add_row(symbol, "대기중", "-", "-", "-")
            continue

        fsm     = state["state"]
        flag    = "O" if state["rsi_30_crossed_up"] else "X"
        price   = f"{_prices[symbol]:,.2f}" if symbol in _prices else "-"

        # alerted_at은 UTC Timestamp. strftime으로 한국 시각처럼 포맷
        alerted_at = state.get("alerted_at")
        alerted = alerted_at.strftime("%m-%d %H:%M:%S") if alerted_at else "-"

        # FSM 상태에 따라 줄 색상을 다르게
        row_style = _STATE_STYLE.get(fsm, "")
        table.add_row(symbol, fsm, flag, price, alerted, style=row_style)

    return table


# ── 알림 발송 ─────────────────────────────────────────────────────────────────

def _dispatch_alert(symbol: str, message: str) -> None:
    """매수 알림을 텔레그램으로 발송한다."""
    logger.info(f"[{symbol}] 알림 발송")
    send_message(message)


# ── 데이터 조회 ──────────────────────────────────────────────────────────────

def _fetch_nasdaq() -> tuple[pd.DataFrame, pd.DataFrame]:
    """NASDAQ 30분봉·5분봉을 조회한다. 모든 종목이 공유하므로 사이클당 1회만 호출."""
    nasdaq_30m = get_candles(NASDAQ_SYMBOL, "30m", LIVE_COUNT_30M)
    nasdaq_5m  = get_candles(NASDAQ_SYMBOL, "5m",  LIVE_COUNT_5M)
    return nasdaq_30m, nasdaq_5m


def _fetch_symbol(symbol: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """종목의 30분봉·5분봉을 조회한다."""
    df_30m = get_candles(symbol, "30m", LIVE_COUNT_30M)
    df_5m  = get_candles(symbol, "5m",  LIVE_COUNT_5M)
    return df_30m, df_5m


# ── 단일 폴링 사이클 ─────────────────────────────────────────────────────────

def run_once() -> None:
    """WATCHLIST 전 종목을 한 사이클 평가한다."""
    global _last_poll

    # NASDAQ 데이터 조회 실패 시 이번 사이클 전체를 건너뜀.
    # NASDAQ 없이는 Signal/Entry 레이어 판단 자체가 불가하기 때문.
    try:
        nasdaq_30m, nasdaq_5m = _fetch_nasdaq()
    except Exception as exc:
        logger.warning(f"NASDAQ 조회 실패 — 이번 사이클 건너뜀: {exc}")
        return

    for symbol in WATCHLIST:
        # 처음 보는 종목은 IDLE 상태로 초기화
        if symbol not in _states:
            _states[symbol] = make_initial_state()

        # 종목 캔들 조회 + 최근 종가 저장 (표 출력용)
        try:
            df_30m, df_5m = _fetch_symbol(symbol)
            # iloc[-1]: 현재 형성 중인 봉 (마감 전이지만 최신 가격으로 표시)
            _prices[symbol] = float(df_5m.iloc[-1]["close"])
        except Exception as exc:
            logger.warning(f"[{symbol}] 데이터 조회 실패 — 건너뜀: {exc}")
            continue

        # FSM 한 틱 진행
        try:
            new_state, alert = process_symbol(
                symbol, _states[symbol], df_30m, nasdaq_30m, df_5m, nasdaq_5m
            )
        except Exception as exc:
            logger.error(f"[{symbol}] FSM 오류: {exc}")
            continue

        # 상태 전이가 발생했을 때만 로그 출력 (매 폴링마다 찍으면 너무 많음)
        prev = _states[symbol]["state"]
        curr = new_state["state"]
        if prev != curr:
            logger.info(f"[{symbol}] {prev} → {curr}")

        _states[symbol] = new_state

        if alert:
            _dispatch_alert(symbol, alert)

    # 폴링 완료 시각 기록 (표 헤더에 표시)
    _last_poll = datetime.now()


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if not WATCHLIST:
        console.print("[red]config.py의 WATCHLIST가 비어 있습니다.[/red]")
        sys.exit(1)

    # Ctrl+C를 누르면 예외 대신 로그를 남기고 깔끔하게 종료
    def _on_sigint(sig, frame):
        console.print("\n[yellow]Ctrl+C — 봇 종료[/yellow]")
        sys.exit(0)

    signal.signal(signal.SIGINT, _on_sigint)

    console.print(f"[green]봇 시작[/green]  watchlist={WATCHLIST}  interval={POLL_INTERVAL_SEC}s\n")

    # Live: 터미널 같은 자리에서 표를 계속 덮어쓰며 갱신하는 컨텍스트 매니저.
    # screen=False → 터미널 전체를 점령하지 않고 표만 아래로 출력
    # refresh_per_second=1 → 1초에 한 번 화면을 다시 그림
    with Live(console=console, refresh_per_second=1, screen=False) as live:
        while True:
            try:
                run_once()
            except Exception as exc:
                logger.error(f"폴링 루프 예외: {exc}")

            # 폴링 완료 후 즉시 표 갱신
            live.update(_build_table())

            # 다음 폴링까지 1초마다 카운트다운을 표 하단(caption)에 표시
            for remaining in range(POLL_INTERVAL_SEC, 0, -1):
                table = _build_table()
                table.caption = f"다음 폴링까지 {remaining}초"
                live.update(table)
                time.sleep(1)


if __name__ == "__main__":
    main()
