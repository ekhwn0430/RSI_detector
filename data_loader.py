import logging
import pandas as pd
import requests
from auth import auth
from config import MAX_CANDLES_PER_REQUEST, RESAMPLE_MINUTES, TOSS_BASE_URL

logger = logging.getLogger(__name__)


def _request_candle_page(symbol: str, before: str | None = None) -> dict:
    """토스 /api/v1/candles 1회 호출 (1분봉 최대 200개). 401이면 토큰 강제 갱신 후 1회 재시도."""
    url = f"{TOSS_BASE_URL}/api/v1/candles"
    params = {
        "symbol": symbol,
        "interval": "1m",
        "count": MAX_CANDLES_PER_REQUEST
    }
    if before is not None:
        params["before"] = before

    headers = {"Authorization": f"Bearer {auth.get_token()}"}
    response = requests.get(url, params=params, headers=headers, timeout=10)

    if response.status_code == 401:
        logger.warning(f"{symbol} 캔들 조회 401, 토큰 강제 갱신 후 재시도")
        headers = {"Authorization": f"Bearer {auth.force_refresh()}"}
        response = requests.get(url, params=params, headers=headers, timeout=10)

    response.raise_for_status()
    return response.json()["result"]


def _fetch_1m_candles(symbol: str, min_count: int) -> pd.DataFrame:
    """1분봉을 min_count개 이상 모일 때까지 `before` 페이지네이션으로 누적 조회.

    반환: timestamp 오름차순(과거 -> 최신) DataFrame, 컬럼 open/high/low/close/volume (float).
    """
    rows = []
    before = None

    while len(rows) < min_count:
        page = _request_candle_page(symbol, before=before)
        candles = page["candles"]
        if not candles:
            break
        rows.extend(candles)
        before = page.get("nextBefore")
        if before is None:
            break

    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    df = df.rename(
        columns={
            "openPrice": "open",
            "highPrice": "high",
            "lowPrice": "low",
            "closePrice": "close"
        }
    )
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def _resample(df_1m: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """1분봉을 minutes 단위로 리샘플링 (spec §3.2 집계 규칙)."""
    rule = f"{minutes}min"
    resampled = df_1m.resample(rule).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum"
        }
    )
    return resampled.dropna(subset=["open", "high", "low", "close"])


def get_candles(symbol: str, interval: str, count: int) -> pd.DataFrame:
    """symbol의 캔들을 interval 단위로 최근 count개 반환.

    interval: '1m' | '5m' | '30m'.
    토스 API는 1m/1d만 지원하므로(spec §3.1), 5m/30m은 1m을 받아 리샘플링한다(spec §3.2).

    주의: 마지막 행이 아직 마감되지 않은(진행 중인) 봉일 수 있다.
    Entry 레이어처럼 마감된 봉만 써야 하는 호출부는 이 함수가 반환한 DataFrame의
    마지막 행을 직접 제외하고 사용해야 한다 (이 함수는 그 판단을 하지 않는다).
    """
    if interval == "1m":
        return _fetch_1m_candles(symbol, count).tail(count)

    if interval not in RESAMPLE_MINUTES:
        raise ValueError(f"지원하지 않는 interval: {interval}")

    minutes = RESAMPLE_MINUTES[interval]
    # count개의 리샘플 봉을 만들려면 1분봉이 최소 count*minutes개 필요.
    # 가장 오래된 구간은 봉 경계에 안 맞아 잘릴 수 있어 1구간만큼 여유를 더 받는다.
    raw_count = count * minutes + minutes
    df_1m = _fetch_1m_candles(symbol, raw_count)
    return _resample(df_1m, minutes).tail(count)
