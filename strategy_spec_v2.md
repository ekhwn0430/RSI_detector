# RSI Detector — Strategy Specification

**Version**: 0.2
**Status**: 코드 작성 단계 진입 준비 완료
**Scope**: 매수 알림봇 전용 (매도는 수동)

---

## 1. 프로젝트 목표

토스증권 Open API를 데이터 소스로 사용하여, 특정 RSI 조건이 만족되는 종목에 대해 **매수 신호 알림**을 텔레그램으로 발송하는 봇.

- 실제 주문 실행은 **포함하지 않음** (`POST /api/v1/orders` 사용 금지)
- 매도 시점 판단은 **사용자 수동**
- 모의 포지션(dict)을 통한 **paper trading 수익률 추적** 포함

---

## 2. 시스템 아키텍처 — 3 레이어 분리

| 레이어 | 역할 | 타임프레임 | 평가 시점 | Repainting |
|--------|------|------------|-----------|------------|
| **Signal** | watch list 진입/이탈 판단 | 30분봉 | 매 1분 폴링 (실시간) | 허용 |
| **Filter** | NASDAQ 거시 환경 게이트 | 30분봉 / 5분봉 | 각 레이어 평가 시 동시 | — |
| **Entry** | 매수 알림 트리거 | 5분봉 | **5분봉 마감 시에만** | 불허 |

**비대칭의 근거**: Signal 레이어는 깜빡거려도 실제 손해가 없으므로(watch list 진입/이탈은 돈을 안 검) 실시간 평가. Entry 레이어는 실제 매수 트리거이므로 봉 마감 후 확정 신호만 수용 (위꼬리 가짜돌파 방지).

---

## 3. 데이터 파이프라인

### 3.1 데이터 소스

토스증권 Open API.

- 인증: OAuth2 client_credentials grant (`POST /oauth2/token`)
- 캔들: `GET /api/v1/candles`
- 사용 가능 interval: **`1m`, `1d`** 뿐
- 1회 호출당 최대 200봉, `before` 파라미터로 페이지네이션

### 3.2 리샘플링 전략

1분봉을 받아 직접 리샘플링한다.

```
1m raw → resample('5min')  → 5분봉 (Entry layer 입력)
1m raw → resample('30min') → 30분봉 (Signal layer 입력)
```

집계 규칙: `open=first, high=max, low=min, close=last, volume=sum`

### 3.3 폴링 주기

**1분** 주기로 모든 watch 후보 + watch list 종목 + NASDAQ 갱신.

---

## 4. 상태 머신

```
       [IDLE]
         │
         │ Signal 진입 조건
         ▼
       [WATCH]  ──────── Signal 이탈 조건 ─────► [IDLE]
         │
         │ Entry 조건 (텔레그램 알림 발송, 1회만)
         ▼
       [ALERTED]
         │
         │ Signal 이탈 조건과 동일
         ▼
       [IDLE]  (다시 처음부터)
```

### 종목별 state 관리

종목별로 다음 정보를 dict로 관리:

```python
{
  symbol: {
    'state': 'IDLE' | 'WATCH' | 'ALERTED',
    'rsi_30_crossed_up': bool,     # 30분봉 RSI 30 상향 돌파 이력 (영구 플래그)
    'entered_at': timestamp,        # WATCH 진입 시각
    'alerted_at': timestamp | None, # 알림 발송 시각
  }
}
```

**Paper trading dict는 별도**로 관리. ALERTED 시점에 가상 매수 기록, paper exit 조건 만족 시 수익률 계산.

---

## 5. 시그널 정의

### 5.1 Signal Layer — WATCH 진입 (IDLE → WATCH)

다음 **모두** 만족 시 진입:

1. `state.rsi_30_crossed_up == True` (과거 어느 시점에 30 상향 돌파 이력 있음 — 영구 플래그)
2. 30분봉 RSI(14) 35 상향 돌파: `prev_rsi <= 35 AND curr_rsi > 35`
3. NASDAQ 30분봉 20MA 기울기 > 0

**`rsi_30_crossed_up` 플래그 갱신 규칙**: 매 30분봉 평가 시 `prev_rsi <= 30 AND curr_rsi > 30` 만족하면 True로 셋. WATCH 이탈 시점에 다시 False로 리셋.

### 5.2 Signal Layer — WATCH 이탈 (WATCH/ALERTED → IDLE)

다음 중 **하나라도** 만족 시 이탈:

- 30분봉 RSI(14) **30 하향 돌파**: `prev_rsi >= 30 AND curr_rsi < 30` (hysteresis)
- NASDAQ 30분봉 20MA 기울기 < 0

이탈 시 state 초기화 (플래그 리셋 포함).

### 5.3 Entry Layer — 매수 알림 (WATCH → ALERTED, 1회만)

**5분봉 마감 시점에만 평가**. 다음 **모두** 만족 시 텔레그램 알림 발송:

1. 5분봉 RSI(14) 35 상향 돌파: `prev_rsi <= 35 AND curr_rsi > 35`
2. 마감된 5분봉의 `close` > **직전 7봉의 max(high)** (현재 봉 미포함)
3. 마감된 5분봉의 `volume` > **직전 20봉 volume 평균** (현재 봉 미포함, `.shift(1)`)
4. NASDAQ 5분봉 20MA 기울기 > 0

알림 발송 후 state를 `ALERTED`로 전환. 같은 종목 재알림은 **WATCH로 재진입(IDLE → WATCH)** 해야 가능.

### 5.4 Paper Trading Exit (시뮬레이션 전용, 알림 없음)

수익률 추적 목적으로 내부 dict에서만 청산 처리. 다음 중 하나라도 만족 시:

- 5분봉 RSI(14) 35 하향 돌파: `prev_rsi >= 35 AND curr_rsi < 35`
- 5분봉 종가 < **직전 7봉의 min(low)** (현재 봉 미포함)

진입가/청산가 정의는 **TBD (§7.3)**.

---

## 6. Configuration

```yaml
signal_layer:
  timeframe: 30m
  rsi_period: 14
  rsi_entry_low: 30      # 30 상향 돌파 → rsi_30_crossed_up = True
  rsi_entry_high: 35     # 35 상향 돌파 → WATCH 진입
  rsi_exit_low: 30       # 30 하향 돌파 → IDLE (hysteresis)

filter_layer:
  index_symbol: TBD       # 토스에서 조회 가능한 NASDAQ 심볼 확인 필요
  ma_period: 20           # Signal과 Entry 양쪽 모두 20MA
  signal_timeframe: 30m
  entry_timeframe: 5m

entry_layer:
  timeframe: 5m
  rsi_period: 14
  rsi_threshold: 35
  breakout_bars: 7
  volume_ma_bars: 20
  evaluation: bar_close   # 봉 마감 시에만 평가

paper_trading:
  exit_rsi_threshold: 35
  exit_breakdown_bars: 7

polling:
  interval_seconds: 60

api:
  base_url: https://openapi.tossinvest.com
  token_refresh_buffer_seconds: 300
```

---

## 7. 미해결 항목

### 7.1 코드 작성 시 자연스럽게 결정될 항목

- 봇 부팅 시 히스토리 워밍업 방식 (일괄 vs 점진)
- 토큰 만료/갱신 실패 시 동작 정책
- Rate limit 초과 시 백오프 전략

### 7.2 운영 단계에서 데이터 보고 결정

- **Case C (WATCH 타임아웃)**: 진입 후 오랫동안 entry 조건 미발생 시 자동 제거 룰. paper trading 돌려보면서 횡보 종목 발생 패턴 보고 정함.
- **rate limit 실제 수치**: 토스 발급 후 문서 확인.

### 7.3 코드 작성 직전에 결정

- **NASDAQ 심볼**: 토스에서 어떤 ticker로 조회되는지 (`QQQ` / `^IXIC` / `^NDX` 등)
- **Paper trading 진입가/청산가 정의**: 알림 발생 봉의 close vs 다음 봉 open (슬리피지 모델)

---

## 8. 구현 순서

1. **OAuth2 토큰 발급 + 캐싱/자동 갱신 모듈**
2. **데이터 어댑터**: `get_candles(symbol, interval, count)` — 1분봉 받아 리샘플 + 페이지네이션
3. **레이어별 시그널 함수**:
   - `detect_watch_entry(df_30m, nasdaq_30m, state) -> bool`
   - `detect_watch_exit(df_30m, nasdaq_30m) -> bool`
   - `detect_buy_alert(df_5m, nasdaq_5m) -> bool`
   - `detect_paper_exit(df_5m) -> bool`
4. **FSM 코어** + 종목별 state dict
5. **백테스트 하네스** (위 함수들 그대로 재사용)
6. **폴링 루프 + 텔레그램 통합**

기존 `detector.py`의 `check_rsi_signal`은 폐기.
