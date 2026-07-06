import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder 스무딩 방식 RSI.

    첫 period봉의 단순평균으로 씨앗값을 만들고, 이후 봉은 지수 스무딩으로 계속 갱신한다.
    반환 Series의 앞쪽 period개 위치는 NaN (계산 불가 구간).
    """
    delta = close.diff()               # 전 봉 대비 가격 변화
    gain = delta.clip(lower=0)         # 상승분만 (하락은 0 처리)
    loss = -delta.clip(upper=0)        # 하락분만, 절댓값으로 (상승은 0 처리)

    # 씨앗값: 첫 period봉의 단순평균
    gain_avg = gain.rolling(window=period).mean()
    loss_avg = loss.rolling(window=period).mean()

    result = pd.Series(float("nan"), index=close.index)

    prev_gain = gain_avg.iloc[period]
    prev_loss = loss_avg.iloc[period]
    result.iloc[period] = _rsi_value(prev_gain, prev_loss)

    # period+1 봉부터는 Wilder 지수 스무딩 적용
    for j in range(period + 1, len(close)):
        prev_gain = (prev_gain * (period - 1) + gain.iloc[j]) / period
        prev_loss = (prev_loss * (period - 1) + loss.iloc[j]) / period
        result.iloc[j] = _rsi_value(prev_gain, prev_loss)

    return result


def _rsi_value(gain_avg: float, loss_avg: float) -> float:
    """RSI 수치 하나를 계산하는 내부 헬퍼. 0 나누기 엣지케이스 처리 포함."""
    if loss_avg == 0:
        return 100.0   # 하락이 전혀 없으면 RSI = 100
    if gain_avg == 0:
        return 0.0     # 상승이 전혀 없으면 RSI = 0
    rs = gain_avg / loss_avg
    return round(100 - 100 / (1 + rs), 2)


def ma(series: pd.Series, period: int) -> pd.Series:
    """단순이동평균 (Simple Moving Average)."""
    return series.rolling(window=period).mean()


def slope(series: pd.Series) -> pd.Series:
    """이전 봉 대비 변화량 (diff). 부호만 보면 기울기 방향이 된다.

    사용 예: slope(ma(df["close"], 20)).iloc[-1] > 0  → 20MA 기울기 양수
    """
    return series.diff()
