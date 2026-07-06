import os
from dotenv import load_dotenv

load_dotenv()  # .env 파일을 환경변수로 로드

# ──────────────────────────────────────────
# API 인증
# ──────────────────────────────────────────
TOSS_CLIENT_ID = os.environ["TOSS_CLIENT_ID"]
TOSS_CLIENT_SECRET = os.environ["TOSS_CLIENT_SECRET"]
TOSS_BASE_URL = "https://openapi.tossinvest.com"

# ──────────────────────────────────────────
# 텔레그램 봇
# ──────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# 토큰 만료 X초 전에 미리 갱신 (spec §6 token_refresh_buffer_seconds)
TOKEN_REFRESH_BUFFER_SEC = 300

# ──────────────────────────────────────────
# 캔들 데이터 조회
# ──────────────────────────────────────────
# 토스 API는 1m, 1d 봉만 제공 (spec §3.1) → 5m/30m은 1m을 리샘플링해서 만든다
CANDLE_BASE_INTERVAL = "1m"
# 토스 /api/v1/candles 1회 호출당 최대 봉 개수 (spec §3.1)
MAX_CANDLES_PER_REQUEST = 200
# 리샘플 대상 interval -> 몇 분 단위인지 매핑
RESAMPLE_MINUTES = {
    "5m": 5,
    "30m": 30,
}

# ──────────────────────────────────────────
# 지표 공통 (spec §6)
# ──────────────────────────────────────────
RSI_PERIOD = 14
MA_PERIOD = 20

# ──────────────────────────────────────────
# Signal 레이어 — 30분봉 (spec §5.1, §5.2)
# ──────────────────────────────────────────
SIGNAL_RSI_FLAG_LEVEL = 30    # 30 상향 돌파 → rsi_30_crossed_up = True
SIGNAL_RSI_ENTRY_LEVEL = 35   # IDLE → WATCH 진입 임계값
SIGNAL_RSI_EXIT_LEVEL = 30    # WATCH → IDLE 이탈 임계값 (hysteresis: 진입 35, 이탈 30)

# ──────────────────────────────────────────
# Entry 레이어 — 5분봉 (spec §5.3)
# ──────────────────────────────────────────
ENTRY_RSI_LEVEL = 35
ENTRY_BREAKOUT_BARS = 7       # close > 직전 N봉 max(high)
ENTRY_VOLUME_MA_BARS = 20     # volume > 직전 N봉 평균

# ──────────────────────────────────────────
# Paper Trading 청산 — 5분봉 (spec §5.4)
# ──────────────────────────────────────────
PAPER_EXIT_RSI_LEVEL = 35
PAPER_EXIT_BREAKDOWN_BARS = 7  # close < 직전 N봉 min(low)

# ──────────────────────────────────────────
# 백테스트
# ──────────────────────────────────────────
# RSI(14) + 20MA를 30분봉에서 쓰려면 1분봉이 최소 21*30=630개 필요.
# 여기서는 여유분을 더해 700개를 기본값으로 사용.
BACKTEST_WARMUP_BARS = 700

# ──────────────────────────────────────────
# 라이브 폴링 루프
# ──────────────────────────────────────────
POLL_INTERVAL_SEC = 60

# 매 폴링마다 조회할 리샘플 봉 개수.
# RSI(14) + slope(20MA) 계산에는 21봉이면 충분하지만 여유분을 둔다.
LIVE_COUNT_30M = 30
LIVE_COUNT_5M = 30

# NASDAQ 필터 심볼. 토스에서 실제로 조회 가능한 ticker를 확인 후 수정 필요 (spec §7.3 TBD).
NASDAQ_SYMBOL = "QQQ"

# 감시할 종목 심볼 목록. 실제 사용 전에 여기에 종목을 추가한다.
WATCHLIST: list[str] = ["SOXL"]