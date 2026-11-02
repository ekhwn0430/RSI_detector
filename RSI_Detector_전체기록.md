# RSI Detector — 프로젝트 전체 기록

> 개인 매매 방식을 자동 알림 시스템으로 옮긴 트레이딩 보조 도구.
> 기획부터 완성까지의 과정, 설계 결정의 근거, 기술 구현, 한계점을 기록한 문서.

- **상태**: 완성, 실사용 중
- **저장소 성격**: 개인 프로젝트
- **대상 시장**: 미국 주식 (SOXL/SOXX 반도체 섹터 중심)
- **최종 범위**: 매수 신호 알림 전용 (주문 실행 없음, 매도 수동)

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [개발 일지](#2-개발-일지)
3. [전략 명세](#3-전략-명세)
4. [기술 구현](#4-기술-구현)
5. [설계 결정과 근거](#5-설계-결정과-근거)
6. [한계점](#6-한계점)
7. [배운 것](#7-배운-것)
8. [후속 방향](#8-후속-방향)

---

## 1. 프로젝트 개요

### 1.1 동기

트레이딩뷰를 상시 확인하지 않고도, 본인이 매매에 사용하던 조건이 충족되는 순간 알림을 받기 위해 제작.

핵심은 "새로운 전략을 만든 것"이 아니라 **이미 수동으로 실행하던 매매 방식을 그대로 코드로 옮긴 것**이다. 이 점이 이후 백테스트 생략 판단의 근거가 된다.

### 1.2 전략의 성격

**역추세(평균회귀) 전략.** RSI 과매도 구간에서 매수해 반등을 노린다.

- 3~5월 상승장: 5분봉 RSI 과매도 매수 → RSI 70 돌파 시 분할 익절 → 추세 꺾임 시 전량 청산. 수익 발생
- 이 수동 매매 방식의 조건을 그대로 프로그램화

### 1.3 범위 결정

개발 도중 토스증권 Open API에 주문 생성(`POST /api/v1/orders`) 기능이 있음을 확인했으나, 다음 이유로 **알림 전용으로 범위를 제한**했다.

- 토스 API에 모의투자(sandbox) 환경이 없음 → 주문 호출은 즉시 실제 자금
- 백테스트 하네스가 없는 상태에서 자동 주문은 위험
- 매도 타이밍 판단은 여전히 사람이 하는 것이 낫다고 판단

---

## 2. 개발 일지

### 2.1 시작 상태

최초 코드는 세 파일이었다.

**`data_loader.py`**
```python
import yfinance as yf

def load_data(ticker):
    df = yf.download([ticker], interval="5m", period="60d")
    res = df.xs(ticker, axis=1, level=1)
    return res

def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # ... for 루프로 Wilder 평활 구현
```

**`detector.py`**
```python
watch_list = []

def check_rsi_signal(rsi, lookback=7, low=30, high=35):
    recent_min = rsi.rolling(window=lookback).min()
    cond1 = recent_min < low
    cond2 = (rsi > high) & (rsi.shift(1) <= high)
    return cond1 & cond2
```

**`readme.md`** — IDLE → WATCH → IN_POSITION → EXIT 전략 서술

### 2.2 초기 진단

코드와 문서 사이에 불일치가 여럿 있었다.

| 문제 | 내용 |
|------|------|
| 타임프레임 불일치 | readme는 30분봉 기준인데 `data_loader`는 5분봉 수집 |
| 상태 관리 부재 | `watch_list = []` 한 줄이 전부. FSM 없음 |
| 함수 귀속 불명확 | `check_rsi_signal`이 1단계용인지 2단계용인지 불분명 |
| 조건 해석 차이 | readme의 "30 돌파 → 35 돌파"와 코드의 "lookback 내 최소값 < 30" 의미 차이 |

### 2.3 lookback 파라미터 재검토

`lookback=7`의 근거를 묻는 과정에서 설계 문제가 드러났다.

- 초기 답변: 7 → 6으로 변경. 근거는 "5분봉 6개 = 30분"
- **문제**: 이 논리는 5분봉 기준인데, readme상 해당 조건은 30분봉 신호 레이어에 속함. 30분봉 6개는 3시간이지 30분이 아님
- 결론: 레이어가 섞여 있었다. 1단계(신호)와 2단계(진입)의 조건이 서로 다른데 하나의 함수로 처리하려 했음

이 지점에서 **레이어 분리**가 설계의 핵심 과제로 떠올랐다.

### 2.4 전략 명세서 작성 (Spec v1)

코드를 더 작성하기 전에 명세부터 확정하기로 결정. 모호한 부분을 전부 TBD로 나열했다.

작성 당시 미결 항목 (총 11개):
- 상승 돌파의 정확한 부등호 위치
- "최근 7봉 고점"의 현재 봉 포함 여부
- "현재 거래량"의 정의 (진행 중 봉 vs 마감 봉)
- NASDAQ 심볼 (토스에서 조회 가능한 티커)
- 기존 `check_rsi_signal`의 레이어 귀속
- `lookback_bars=6`의 의미 재정의
- WATCH 타임아웃 정책
- 알림 쿨다운 정책
- 봇 부팅 시 워밍업 방식
- 토큰 갱신 실패 시 동작
- Rate limit 초과 시 동작

### 2.5 TBD 해결 과정

각 항목을 하나씩 결정했다.

#### (1) 부등호 위치

```
"30 상승 돌파" = prev_rsi <= 30 AND curr_rsi > 30
```
RSI가 정확히 30일 때는 돌파로 인정하지 않음. 다음 봉에서 30을 넘어야 트리거.

#### (2) 7봉 고점 돌파 판정

세 가지 선택지를 검토했다.

| 방식 | 내용 | 문제 |
|------|------|------|
| (a) 봉의 High 기준 | 진행 중 봉의 high가 직전 7봉 max 돌파 | 위꼬리 가짜돌파 포착 |
| (b) 종가 + 봉 마감 대기 | 마감된 봉의 close로 판정 | 최대 5분 지연 |
| (c) 현재가 + 쿨다운 | 실시간 현재가 + N분 차단 | 쿨다운 길이를 또 정해야 함 |

**(b) 선택.** 근거: 봉 진행 중 가격이 고점 위로 잠깐 찔렀다가 아래로 마감하는 **위꼬리 가짜돌파(fakeout)** 를 걸러낼 수 있음. 매도가 수동이므로 5분 지연이 치명적이지 않음.

#### (3) 거래량 비교 기준

(2)의 결정으로 자동 해결됨. 봉 마감 시점 평가이므로:
- 좌변 "현재 거래량" = 방금 마감된 5분봉의 거래량
- 우변 "MA" = 그 **이전** 20봉의 거래량 평균

**현재 봉을 MA에서 제외**하는 것이 핵심. 포함하면 비교 좌변이 우변에 들어가 편향이 생긴다.

예시 — 거래량이 `100, 100, 100, 100, 1000`이고 MA(5)를 볼 때:
- 포함: MA = 280 → 1000 vs 280 = 3.5배
- 제외: MA = 100 → 1000 vs 100 = 10배

같은 데이터인데 "평균 대비 크다"의 강도가 완전히 달라진다. 구현은 `.rolling(20).mean().shift(1)`.

> **차트와의 차이**: 트레이딩뷰 등 차트에 그려지는 MA는 현재 봉을 포함한다(그래서 봉 진행 중 MA 끝이 출렁임). 백테스트/시그널 평가에서는 편향 방지를 위해 제외하는 것이 표준. 봉 마감 후 평가하므로 실제 차이는 작지만, 정의를 명확히 하기 위해 표준 방식 채택.

#### (4) 기존 함수 처리

`check_rsi_signal` **폐기.** 레이어별로 새 함수 작성:
- `detect_watch_entry(df_30m, nasdaq_30m, state)` — Signal 레이어
- `detect_watch_exit(df_30m, nasdaq_30m)` — Signal 레이어
- `detect_buy_alert(df_5m, nasdaq_5m)` — Entry 레이어
- `detect_paper_exit(df_5m)` — 페이퍼 청산

폐기와 동시에 `lookback_bars=6` 문제도 소멸.

#### (5) "30 돌파 이력" 관리 방식

세 가지를 검토했다.

| 방식 | 내용 |
|------|------|
| lookback 윈도우 | 최근 N봉 내 30 미만 이력 확인 |
| 영구 플래그 | state에 `rsi_30_crossed_up` 저장 |
| 만료 플래그 | 플래그 + 유효기간 |

**영구 플래그 선택.** 근거:
- 30분봉 RSI 30 돌파는 드문 이벤트. lookback이 짧으면 놓치고 길면 의미 없음
- 종목별 state dict를 어차피 관리하므로 필드 하나 추가로 해결
- 만료 정책이 필요해지면 나중에 추가 가능

#### (6) NASDAQ 기울기 정의

- 방식: 단순 차분(`diff() > 0`)이 아니라 **MA의 기울기**
- 기간: Signal/Entry 레이어 **둘 다 20MA**

근거: NASDAQ은 거시 지표이므로 짧은 MA를 쓰면 노이즈에 휘둘린다. 5분봉에 5MA면 25분 평균인데, 그 정도 시간에 지수 방향이 바뀌었다고 매매 판단에 반영하는 것은 과민반응. 20MA 통일 시 Signal은 10시간(30m×20), Entry는 100분(5m×20) 평균으로 자연스럽게 비례.

#### (7) 알림 중복 방지

| 방식 | 내용 |
|------|------|
| (a) 봉당 1회 | 봉 마감 평가이므로 자동 충족. 연속 봉에서 반복 알림 |
| (b) WATCH 재진입 전까지 1회 | 한 번 알림 후 IDLE 복귀해야 재알림 |
| (c) 시간 쿨다운 | N분 차단 |

**(b) 선택.** 근거: 매도가 수동이므로 한 번 알림을 받고 매수했으면 같은 종목 재알림이 불필요. state machine과 자연스럽게 통합되고 마법 숫자가 생기지 않음. 종목이 진짜 강해서 두 번째 기회가 온다면 RSI가 30 밑으로 갔다가 다시 올라온 것이므로 진짜 새 신호.

#### (8) WATCH 이탈 조건

| 케이스 | 결정 |
|--------|------|
| RSI 하락 | **30 하향 돌파 시 이탈.** 30 밑으로 갔다면 미래에 더 좋은 매수 지점이 나올 수 있음 |
| NASDAQ 기울기 음전 | **이탈.** 최대한 방어적으로 매매 |
| 장기간 entry 미발생 | **유지.** 진짜 안 될 타점이면 위 두 조건에 걸릴 것 (타임아웃 미구현, 한계점 참조) |
| 반복 진입/이탈 | **허용.** watch list 깜빡임은 손해 없음 |

> **히스테리시스**: 진입은 RSI 35 상향, 이탈은 RSI 30 하향. 임계값을 다르게 둔 것이 곧 이력현상(hysteresis) 구조다. RSI가 31~37 사이에서 깜빡거려도 한 번 들어온 종목이 빠지지 않는다. 에어컨이 26도에서 켜고 24도에서 끄는 것과 같은 원리.

### 2.6 데이터 소스 전환 검토

yfinance의 한계(한국 데이터 빈약, 5분봉 60일 제한)로 토스증권 Open API 검토.

OpenAPI 스펙 분석 결과 21개 엔드포인트 확인:
```
POST /oauth2/token              OAuth2 토큰 발급
GET  /api/v1/orderbook          호가 조회
GET  /api/v1/prices             현재가 조회
GET  /api/v1/trades             최근 체결 내역
GET  /api/v1/price-limits       상/하한가
GET  /api/v1/candles            캔들 차트
GET  /api/v1/stocks             종목 기본 정보
GET  /api/v1/exchange-rate      환율
GET  /api/v1/market-calendar/*  장 운영 정보
GET  /api/v1/accounts           계좌 목록
GET  /api/v1/holdings           보유 주식
POST /api/v1/orders             주문 생성      ← 사용 안 함
POST /api/v1/orders/{id}/cancel 주문 취소      ← 사용 안 함
...
```

주문 기능이 있었으나 위 1.3의 이유로 데이터 조회만 사용하기로 결정.

### 2.7 Spec v2 확정

모든 TBD 해결 후 명세를 재작성. 레이어별 평가 시점의 **비대칭 구조**가 이 버전의 핵심.

### 2.8 구현 및 핸드오프

`config.py`, `auth.py`, `.env`, `.gitignore`, `requirements.txt` 작성 후 VSCode의 Claude Code로 핸드오프. 데이터 어댑터·시그널 함수·FSM·폴링 루프·텔레그램 연동을 완성해 실사용 중.

---

## 3. 전략 명세

### 3.1 아키텍처 — 3레이어 분리

| 레이어 | 역할 | 타임프레임 | 평가 시점 | Repainting |
|--------|------|-----------|----------|-----------|
| **Signal** | watch list 진입/이탈 | 30분봉 | 매 1분 폴링 (실시간) | 허용 |
| **Filter** | NASDAQ 거시 환경 게이트 | 30분봉 / 5분봉 | 각 레이어와 동시 | — |
| **Entry** | 매수 알림 트리거 | 5분봉 | **봉 마감 시에만** | 불허 |

**비대칭의 근거**: watch list 진입/이탈은 실제 자금이 걸리지 않으므로 신호가 깜빡여도 손해가 없다 → 실시간 평가로 빠른 반응. Entry는 실제 매수 트리거이므로 봉 마감 후 확정 신호만 수용 → 가짜돌파 차단.

구현상으로는 폴링이 매 1분 돌지만, Entry 평가는 **새 1분봉 수신으로 5분봉 하나가 새로 마감됐을 때만** 수행한다 (분 단위 :04, :09, :14, ...).

### 3.2 상태 기계 (FSM)

```
       [IDLE]
         │
         │ Signal 진입 조건
         ▼
       [WATCH]  ──── Signal 이탈 조건 ────► [IDLE]
         │
         │ Entry 조건 (텔레그램 알림 1회)
         ▼
      [ALERTED]
         │
         │ Signal 이탈 조건 (동일)
         ▼
       [IDLE]
```

종목별 상태 저장:
```python
{
  symbol: {
    'state': 'IDLE' | 'WATCH' | 'ALERTED',
    'rsi_30_crossed_up': bool,      # 영구 플래그
    'entered_at': timestamp,         # WATCH 진입 시각
    'alerted_at': timestamp | None,  # 알림 발송 시각
  }
}
```

페이퍼 트레이딩 포지션은 별도 dict로 관리.

### 3.3 조건 정의

#### WATCH 진입 (IDLE → WATCH)

아래 **전부** 충족:

1. `state.rsi_30_crossed_up == True`
   - 플래그 갱신 규칙: 매 30분봉 평가 시 `prev_rsi <= 30 AND curr_rsi > 30`이면 True
2. 30분봉 RSI(14) 35 상향 돌파: `prev_rsi <= 35 AND curr_rsi > 35`
3. NASDAQ 30분봉 20MA 기울기 > 0

#### WATCH 이탈 (WATCH/ALERTED → IDLE)

아래 중 **하나라도** 충족:

- 30분봉 RSI(14) 30 하향 돌파: `prev_rsi >= 30 AND curr_rsi < 30`
- NASDAQ 30분봉 20MA 기울기 < 0

이탈 시 state 전체 초기화 (플래그 포함).

#### Entry 알림 (WATCH → ALERTED, 1회만)

**5분봉 마감 시점에만 평가.** 아래 **전부** 충족:

1. 5분봉 RSI(14) 35 상향 돌파: `prev_rsi <= 35 AND curr_rsi > 35`
2. 마감된 5분봉 `close` > **직전 7봉의 max(high)** — 현재 봉 미포함
3. 마감된 5분봉 `volume` > **직전 20봉 volume 평균** — `.shift(1)`로 현재 봉 제외
4. NASDAQ 5분봉 20MA 기울기 > 0

알림 발송 후 `ALERTED`로 전환. 재알림은 IDLE 복귀 후 WATCH 재진입해야 가능.

#### 페이퍼 트레이딩 청산 (알림 없음, 내부 기록만)

아래 중 하나라도 충족:
- 5분봉 RSI(14) 35 하향 돌파: `prev_rsi >= 35 AND curr_rsi < 35`
- 5분봉 종가 < 직전 7봉의 min(low) — 현재 봉 미포함

---

## 4. 기술 구현

### 4.1 데이터 소스: 토스증권 Open API

#### 확인된 제약

| 항목 | 내용 |
|------|------|
| 인증 | OAuth2 client_credentials grant |
| refresh token | **미제공.** 만료 시 동일 엔드포인트로 재발급 |
| 토큰 동시성 | **client당 유효 토큰 1개.** 재발급 시 이전 토큰 즉시 무효화 |
| 캔들 interval | **`1m`, `1d` 만 지원** |
| 1회 조회량 | 최대 200봉 |
| 페이지네이션 | `before` 파라미터 (ISO 8601, exclusive). 응답의 `nextBefore` 사용 |
| 가격 형식 | **문자열로 반환** (`"71600"`) → `float()` 변환 필요 |
| 모의투자 | **없음.** sandbox/paper/mock 전부 미지원 |
| Rate limit | 그룹별 상이 (`AUTH`, `MARKET_DATA_CHART`, `ORDER`). 실제 수치는 별도 문서 |

#### 캔들 응답 구조

```json
{
  "result": {
    "candles": [
      {
        "timestamp": "2026-03-25T09:00:00+09:00",
        "openPrice": "71600",
        "highPrice": "72300",
        "lowPrice": "71500",
        "closePrice": "72000",
        "volume": "3521000",
        "currency": "KRW"
      }
    ],
    "nextBefore": "..."
  }
}
```

### 4.2 리샘플링

API가 5분봉·30분봉을 직접 제공하지 않으므로 1분봉을 받아 직접 재집계.

```python
1m raw → resample('5min')  → 5분봉 (Entry layer)
1m raw → resample('30min') → 30분봉 (Signal layer)
```

집계 규칙:
```python
{'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
```

**히스토리 깊이 문제**: 1회 200봉 제한 때문에, 1분봉 200개는 3시간 20분치에 불과하다. 30분봉으로 리샘플하면 약 6~7개밖에 안 나와 RSI(14) 계산이 불가능. 따라서 `before` 페이지네이션으로 과거 데이터를 추가 수집해야 한다.

필요 호출 수 (RSI 안정화 + 20MA + 여유 포함):
- 30분봉 50봉 필요 → 1분봉 약 1,500개 → **8회 이상**
- 5분봉 50봉 필요 → 1분봉 약 250개 → **2회**

### 4.3 인증 모듈

```python
class TossAuth:
    def __init__(self, client_id, client_secret):
        self._access_token = None
        self._expires_at = 0.0       # Unix timestamp
        self._lock = Lock()          # 멀티스레드 대비

    def get_token(self):
        with self._lock:
            if self._needs_refresh():
                self._fetch_new_token()
            return self._access_token

    def force_refresh(self):
        """401 수신 시 강제 재발급"""
        with self._lock:
            self._fetch_new_token()
            return self._access_token

    def _needs_refresh(self):
        if self._access_token is None:
            return True
        return time.time() >= (self._expires_at - TOKEN_REFRESH_BUFFER_SEC)
```

설계 포인트:
- **절대 만료 시각 저장**: API가 `expires_in`(남은 초)을 주므로 `time.time() + expires_in`으로 변환해 저장. 비교가 단순해짐
- **버퍼 갱신**: 만료 5분(300초) 전에 미리 갱신. 호출 도중 만료되는 상황 방지
- **401 안전망**: 만료 전이어도 토큰이 무효화됐을 수 있으므로 `force_refresh()` 제공. "사전 갱신 + 사후 복구" 이중 구조
- **Lock**: 토스가 client당 토큰 1개만 허용하므로, 동시 갱신 시 서로를 무효화할 수 있음. 단일 스레드에서는 불필요하나 확장 대비

### 4.4 지표 구현

#### Wilder RSI

초기 코드는 for 루프로 재귀 평활을 구현했으나, pandas의 `ewm`이 동일한 결과를 내므로 벡터화.

```python
def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.where(avg_loss != 0, 100)   # 전부 상승 시 RSI = 100
    return rsi
```

파라미터 의미:
- `alpha=1/period` — Wilder 공식의 평활 계수
- `adjust=False` — 재귀 공식 그대로 적용 (True면 다른 가중 방식)
- `min_periods=period` — 초기 N봉은 NaN

Wilder 방식을 쓰는 이유: 증권사 HTS·트레이딩뷰 표준이므로 차트에서 보는 값과 봇 계산값이 일치한다. 단순이동평균 방식은 오래된 봉이 윈도우에서 빠질 때 값이 튀는 문제가 있다.

#### 거래량 MA

```python
vol_ma = volume.rolling(20).mean().shift(1)   # 현재 봉 제외
signal = volume > vol_ma
```

### 4.5 설정 분리

모든 임계값·기간을 한 곳에 모아 관리.

```yaml
signal_layer:
  timeframe: 30m
  rsi_period: 14
  rsi_entry_low: 30      # 30 상향 돌파 → 플래그 셋
  rsi_entry_high: 35     # 35 상향 돌파 → WATCH 진입
  rsi_exit_low: 30       # 30 하향 돌파 → IDLE (hysteresis)

filter_layer:
  index_symbol: <TBD>
  ma_period: 20          # Signal/Entry 공통
  signal_timeframe: 30m
  entry_timeframe: 5m

entry_layer:
  timeframe: 5m
  rsi_period: 14
  rsi_threshold: 35
  breakout_bars: 7
  volume_ma_bars: 20
  evaluation: bar_close

paper_trading:
  exit_rsi_threshold: 35
  exit_breakdown_bars: 7

polling:
  interval_seconds: 60

api:
  base_url: https://openapi.tossinvest.com
  token_refresh_buffer_seconds: 300
```

분리 목적:
- 파라미터 튜닝 시 코드 수정 불필요
- 백테스트에서 조합 실험 가능 (lookback 5/6/7/8 등)
- 실행 시 config를 함께 저장하면 "왜 이렇게 동작했는지" 사후 추적 가능

### 4.6 보안 처리

```
.env            ← client_id, client_secret (gitignore)
.gitignore      ← .env, __pycache__/, *.pyc, .venv/, *.log
config.py       ← os.environ["..."] 로 읽기 (없으면 KeyError, fail fast)
```

인증 정보는 `os.environ.get()`이 아니라 `os.environ[...]`으로 읽는다. 없으면 즉시 예외가 나야 하기 때문 (봇이 인증 없이 돌아갈 이유가 없음).

### 4.7 파일 구성

```
toss_bot/
├── .env                  # 인증 정보 (gitignore)
├── .gitignore
├── config.py             # 모든 설정값
├── auth.py               # OAuth2 토큰 관리
├── data_loader.py        # 캔들 수집 + 리샘플링
├── indicators.py         # RSI, MA 기울기
├── detectors.py          # 레이어별 시그널 함수 (stateless)
├── fsm.py                # 상태 전이 로직
├── backtest.py           # 백테스트 하네스
├── main.py               # 폴링 루프 + 텔레그램
└── requirements.txt
```

### 4.8 시그널 함수와 FSM 분리

시그널 함수는 **stateless**로 작성한다 — "이 데이터에 이 패턴이 있는가"만 판정.

```python
detect_watch_entry(df_30m, nasdaq_30m, state) -> bool
detect_watch_exit(df_30m, nasdaq_30m)         -> bool
detect_buy_alert(df_5m, nasdaq_5m)            -> bool
detect_paper_exit(df_5m)                      -> bool
```

FSM은 그 위에서 **stateful**하게 동작 — "현재 상태에서 어떤 시그널을 확인하고, 충족 시 어디로 전이하는가".

```python
def process_symbol(symbol, state, data_30m, data_5m, nasdaq):
    if state['state'] == 'IDLE':
        if detect_rsi_30_cross(data_30m):
            state['rsi_30_crossed_up'] = True
        if detect_watch_entry(data_30m, nasdaq, state):
            state['state'] = 'WATCH'
            state['entered_at'] = now()

    elif state['state'] == 'WATCH':
        if detect_watch_exit(data_30m, nasdaq):   # 이탈 우선
            reset_state(state)
            return state
        if detect_buy_alert(data_5m, nasdaq):
            send_telegram_alert(symbol)
            state['state'] = 'ALERTED'
            state['alerted_at'] = now()

    elif state['state'] == 'ALERTED':
        if detect_watch_exit(data_30m, nasdaq):   # 재알림 없음
            reset_state(state)

    return state
```

**분리의 이유**: 백테스트와 실시간 루프가 시그널 함수와 FSM을 100% 공유할 수 있다. 유일한 차이는 데이터가 과거인지 실시간인지뿐.

---

## 5. 설계 결정과 근거

전체 결정 사항을 한 표로 정리.

| 결정 | 선택 | 근거 |
|------|------|------|
| 전략 레이어 | 3단계 분리 (Signal/Filter/Entry) | 각 레이어의 입력·타임프레임·조건이 모두 다름. 한 함수로 처리하면 반드시 꼬임 |
| 평가 시점 | Signal 실시간 / Entry 봉 마감 | 돈이 걸린 쪽만 확정 신호를 쓰는 비대칭 구조 |
| 돌파 부등호 | `prev <= X AND curr > X` | 임계값 정확히 일치 시 미발동. 명확한 이벤트 정의 |
| 고점 돌파 기준 | 마감 종가 | 위꼬리 가짜돌파 필터링. 5분 지연은 수동 매도이므로 무해 |
| 거래량 MA | 현재 봉 제외 (`shift(1)`) | 좌변이 우변에 포함되는 편향 방지 (표준 방식) |
| 30 돌파 이력 | 영구 플래그 (state) | lookback 윈도우는 짧으면 놓치고 길면 무의미 |
| NASDAQ 기울기 | 20MA, 양 레이어 공통 | 거시 지표는 짧은 MA에서 노이즈에 휘둘림 |
| 진입/이탈 임계값 | 35 / 30 (히스테리시스) | 경계 구간 깜빡임 방지 |
| 알림 횟수 | WATCH 재진입 전까지 1회 | 매도가 수동이므로 반복 알림 불필요. 마법 숫자 회피 |
| 주문 실행 | 미구현 | sandbox 부재 + 백테스트 부재 상태에서 위험 |
| 매직 넘버 | config 분리 | 튜닝·실험·사후 추적 용이 |
| 시그널 함수 | stateless | 백테스트/실시간 코드 공유 |
| RSI 구현 | Wilder, `ewm` 벡터화 | 차트 값과 일치 + 속도 |

---

## 6. 한계점

### 6.1 핵심 한계 — 단일 국면 전용 전략

이 시스템은 역추세(평균회귀) 전략이다. **상승장과 횡보장에서만 유효하다.**

실전 검증 결과:

| 시기 | 시장 국면 | 결과 |
|------|----------|------|
| 3~5월 | 상승 추세 | 정상 작동. 수익 발생 |
| 6월 중순~ | 하락·횡보 전환 | **작동 실패** |

하락 추세에서 과매도 매수는 "떨어지는 칼날 잡기"가 된다. RSI 30이 28 되고 25 되고 20 되는 동안 계속 매집하게 됨.

**도출된 결론**: 수익의 실제 근원은 RSI 신호가 아니라 **상승 추세 그 자체**였다. RSI는 타이밍만 제공했다. 하나의 전략은 모든 시장 국면에서 유효하지 않다.

### 6.2 미해결 설계 항목

#### WATCH 타임아웃 없음

진입 후 장기간 Entry 조건이 발생하지 않아도 자동 제거되지 않는다.

가정했던 시나리오: "진짜 안 될 타점이면 RSI 30 하향이나 NASDAQ 음전에 걸려서 빠질 것."

하지만 걸리지 않는 경우가 있다 — 종목이 watch list 진입 후 **RSI 31~34 구간에서 2주간 횡보**하고 NASDAQ 기울기도 양수를 유지하면, A·B 조건 어디에도 안 걸린다. 2주 전 신호가 여전히 살아있게 된다. 신호에도 신선도가 있어야 한다.

운영 중 패턴을 보고 `N봉 이내 entry 미발생 시 자동 제거` 규칙을 추가할 계획으로 보류.

#### 백테스트 하네스 미구현

**생략 근거**: 봇 로직이 사용자의 수동 매매 방식을 그대로 복제한 것이므로, 실전 매매 이력 자체가 검증 역할을 한다고 판단. 통계적 백테스트보다 정보 가치가 낮지도 않다 — 실제 슬리피지·심리·시장 미시구조가 모두 반영된 결과이므로.

**남는 문제**: 사람과 봇의 행동이 다르다.
- 사람은 알림이 없어도 차트를 보다가 "이건 신호긴 한데 안 좋아 보임"을 걸러낸다
- 사람은 여러 신호 중 좋은 것만 선택적으로 매매한다
- 봇은 조건 충족 시 전부 알림을 보낸다

따라서 **수동 매매 성과와 봇 알림 성과는 일치하지 않을 수 있다.** 이 차이는 백테스트로도 알 수 없고 라이브 운영으로만 확인 가능하다.

#### 기타 미해결

| 항목 | 내용 |
|------|------|
| Rate limit 미측정 | 그룹별 실제 호출 제한 수치를 확인하지 않음. watch list가 커지면 429 위험 |
| NASDAQ 심볼 미확정 | 토스에서 `QQQ`/`^IXIC`/`^NDX` 중 무엇이 조회되는지 코드로 확인 필요 |
| 페이퍼 진입가 정의 | 알림 시점 종가 vs 다음 봉 시가 (슬리피지 모델) 미결정 |
| 포지션 사이징 없음 | 진입 신호만 제공, 투입 규모 로직 부재 |
| 청산 수동 | EXIT 조건은 페이퍼 기록용. 실제 매도는 사람이 판단 |
| 워밍업 전략 | 부팅 시 히스토리 일괄 로드 vs 점진 누적 미결정 |

### 6.3 레버리지 ETF 미반영

주 매매 대상인 SOXL은 3배 레버리지 ETF다. 방향성 없는 횡보 구간에서 **변동성 잠식(volatility decay)** 이 발생한다.

예시 — 기초지수가 `100 → 110 (+10%) → 99 (-10%)` 로 움직이면:
- 기초: -1%
- 3배 ETF: +30% → 77 → -30% → **-46%** (단순 -3%가 아님)

현 시스템은 이를 신호 로직에 반영하지 않는다. 국면 판단이 없으므로 잠식 구간에서도 진입 신호를 낼 수 있다.

### 6.4 구조적 한계

- **후행 지표 의존**: RSI는 과거 데이터의 평균이므로 항상 실시간보다 늦게 반응한다. "돌파" 신호 시점에는 이미 움직임이 상당히 진행됐을 수 있음
- **단일 자산군**: 미국 주식 전용. 다른 시장/자산군 미대응
- **단일 방향**: 매수 신호만. 숏 포지션 미지원

---

## 7. 배운 것

### 7.1 설계가 코드보다 먼저다

진입 신호 함수 자체는 금방 짰다. 시간의 대부분은 spec을 잡고 엣지 케이스를 정의하는 데 들어갔다. "부등호를 `<`로 할지 `<=`로 할지" 같은 사소해 보이는 결정이 신호 발생 횟수를 바꾼다.

참고한 현직 퀀트 자료에서도 "전략 코드보다 spec 쓰는 시간이 더 길다"는 언급이 반복된다.

### 7.2 신호(Signal)와 진입(Entry)은 다른 레이어다

가장 크게 꼬였던 부분. 느린 타임프레임에서 "뭔가 일어났다"를 감지하는 것과, 빠른 타임프레임에서 "지금 산다"를 결정하는 것은 입력·조건·평가 시점이 전부 다르다. 하나의 함수로 처리하려 하면 반드시 모순이 생긴다.

### 7.3 State와 Event를 구분해야 한다

- `IDLE`/`WATCH`/`ALERTED`는 **state** — 종목별로 저장
- "RSI 30 돌파"는 **event** — 매 봉 계산
- 둘을 잇는 **transition 함수**가 별도로 필요

초기 코드에 event 감지 함수만 있고 state 관리가 없었던 것이 진도가 안 나간 원인이었다.

### 7.4 Repainting을 어디까지 허용할지는 손실 여부로 결정한다

"신호가 깜빡이면 나쁘다"가 아니라 "깜빡여서 손해를 보는가"를 기준으로 판단해야 한다. watch list는 깜빡여도 돈이 안 나가므로 실시간 반응이 이득이고, 매수 알림은 돈이 나가므로 확정 신호만 받아야 한다.

### 7.5 매직 넘버는 처음부터 분리한다

`lookback=7`의 근거를 설명하지 못했던 것이 설계 결함을 드러낸 계기였다. 숫자를 config로 빼두면 "왜 이 값인가"를 묻게 되고, 나중에 실험도 쉬워진다.

### 7.6 평균 비교 시 자기 자신을 포함하지 않는다

거래량 MA에 현재 봉을 포함하면 비교의 의미가 희석된다. 차트의 시각적 표현과 백테스트의 통계적 정의가 다를 수 있다는 것을 인지해야 한다.

---

## 8. 후속 방향

### 8.1 목표 구조 — 국면 판단 + 국면별 전략 전환

```
시장 국면 판단
├─ 상승 추세장 → RSI 과매도 매수 (= 본 프로젝트, 검증 완료)
├─ 하락 추세장 → 관망 또는 추세추종 (미구현)
└─ 횡보장      → RSI 역추세 변형
```

본 프로젝트는 이 구조를 **대체당하는 것이 아니라, 국면 판단 레이어 하위에 편입될 모듈**이다. 상승장용 조각은 이미 검증됐고, 추세장용 조각이 비어 있다.

### 8.2 현재 수동 검증 중인 진입 규칙

- 일봉 20/60 이동평균선이 역배열 → 정배열로 전환되며 **간격이 벌어지는 것을 확인한 뒤** 진입
- 단순 교차 시점이 아닌 '벌어짐'을 보는 이유: 교차 후 재역전되는 가짜 신호(whipsaw) 차단
- 포지션 규모를 국면에 연동: 정배열 확인 시 크게, 그 전에는 관망 또는 전체 자금 10% 이하

이 규칙은 현재 실전에서 눈으로 검증 중이며, 코드화는 이후 단계.

### 8.3 후속 프로젝트에서 달라져야 할 것

| 항목 | 본 프로젝트 | 후속 |
|------|------------|------|
| 백테스트 | 생략 (수동 매매로 검증) | **필수** — 수동 검증 이력이 없는 새 전략이므로 |
| Robustness 검증 | 없음 | Walk-Forward, Monte Carlo 등 |
| 포지션 사이징 | 없음 | 변동성 기반(ATR) 또는 국면 연동 |
| 청산 | 수동 | 추세추종은 청산이 수익을 만들므로 규칙화 필요 |

### 8.4 재사용 가능한 자산

- `auth.py` — 토스 OAuth2 토큰 관리 (그대로 재사용)
- 1분봉 → 다중 타임프레임 리샘플링 로직
- Wilder RSI 벡터화 구현
- stateless 시그널 함수 + FSM 분리 패턴
- 3레이어 분리 설계 사상 (신호 / 필터 / 진입)
- config 분리 구조

---

## 부록: 참고 자료

### 오픈소스 프레임워크

| 프로젝트 | 참고 포인트 |
|---------|------------|
| Freqtrade | 봇 아키텍처 — 폴링 루프 + 텔레그램 + 백테스트 통합 구조 |
| Backtrader | Strategy / Indicator / Broker 클래스 분리 패턴 |
| pysystemtrade (Rob Carver) | 개인이 실제 자금을 운용하는 시스템의 완성 형태 |
| vectorbt | 벡터화 백테스트, 파라미터 스윕 |
| CCXT | 다양한 브로커 API를 통일 인터페이스로 감싸는 패턴 |
| QuantConnect/LEAN | 프로덕션 트레이딩 시스템의 폴더 구조 |

### 개념

- **Hysteresis (이력현상)** — 진입/이탈 임계값을 다르게 두어 경계 깜빡임 방지. 제어공학에서 유래
- **Repainting** — 봉이 마감되기 전 신호가 나타났다 사라지는 현상. 백테스트와 실시간의 괴리 원인
- **Volatility Decay** — 레버리지 ETF가 횡보 구간에서 원금이 잠식되는 현상
- **Whipsaw** — 신호가 발생한 직후 반대로 뒤집히는 가짜 신호

---

*이 문서는 프로젝트 기획부터 완성까지의 전 과정과 설계 근거를 기록한 것으로, 후속 프로젝트의 출발점 자료로 사용된다.*
