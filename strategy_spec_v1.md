# RSI Detector — Strategy Specification

**Version**: 0.1 (draft)
**Status**: 코드 작성 전 검토 단계
**Scope**: 매수 알림봇 전용 (매도는 수동)

---

## 1. 프로젝트 목표

토스증권 Open API를 데이터 소스로 사용하여, 특정 RSI 조건이 만족되는 종목에 대해 **매수 신호 알림**을 텔레그램으로 발송하는 봇.

- 실제 주문 실행은 **포함하지 않음** (`POST /api/v1/orders` 사용 금지)
- 매도 시점 판단은 **사용자 수동**
- 모의 포지션(dict)을 통한 **paper trading 수익률 추적**은 포함

---

## 2. 시스템 아키텍처 — 3 레이어 분리

전략은 세 개의 독립된 레이어로 분리해서 구현한다. 각 레이어는 입력 타임프레임과 조건이 다르며, 같은 함수로 처리하지 않는다.

| 레이어 | 역할 | 타임프레임 | 출력 |
|--------|------|------------|------|
| **Signal** | watch list 진입/이탈 판단 | 30분봉 | watch list 갱신 |
| **Filter** | 거시 환경 게이트 | 30분봉 / 5분봉 (NASDAQ) | 통과/차단 |
| **Entry** | 실제 매수 알림 타이밍 | 5분봉 | 텔레그램 알림 |

---

## 3. 데이터 파이프라인

### 3.1 데이터 소스

토스증권 Open API.

- 인증: OAuth2 client_credentials grant (`POST /oauth2/token`)
- 캔들: `GET /api/v1/candles`
- 사용 가능 interval: **`1m`, `1d` 뿐**
- 1회 호출당 최대 200봉, `before` 파라미터로 페이지네이션

### 3.2 리샘플링 전략

토스가 5m/30m을 직접 주지 않으므로 1분봉을 받아 직접 리샘플링한다.

```
1m raw → resample('5min')  → 5분봉 (Entry layer 입력)
1m raw → resample('30min') → 30분봉 (Signal layer 입력)
```

집계 규칙: `open=first, high=max, low=min, close=last, volume=sum`

### 3.3 히스토리 깊이

각 레이어에서 필요한 최소 봉 수 (RSI(14) 안정화 + lookback 여유 포함):

- 30분봉: 최소 50봉 → 1분봉 약 1500개 → API 호출 8회 이상 페이지네이션
- 5분봉: 최소 50봉 → 1분봉 약 250개 → API 호출 2회

**TBD**: 봇 시작 시 한 번에 전체 히스토리 로드 vs 운영 중 증분 로드. 후자가 자연스럽지만 첫 봇 부팅 시 워밍업 기간 필요.

### 3.4 폴링 주기

**1분** 주기로 모든 watch 후보 + watch list 종목 + NASDAQ을 갱신.

- 1분이 토스의 최소 봉 단위이므로 그보다 자주 호출해도 새 데이터 없음
- watch list 크기 × 1분당 호출 수가 토스 rate limit을 넘지 않도록 모니터링 필요
- **TBD**: rate limit 실제 수치 (토스 개발자 문서 확인 필요)

---

## 4. 상태 머신

```
      [IDLE]
        │
        │ Signal 진입 조건
        ▼
      [WATCH]  ──────── Signal 이탈 조건 ─────► [IDLE]
        │
        │ Entry 조건 (텔레그램 알림 발송)
        ▼
    (수동 매수)
        │
        │ Paper trading dict에 가상 포지션 기록
        ▼
  [PAPER_HELD]  ──── Paper exit 조건 ─────► (수익률 기록)
```

**중요**:
- IN_POSITION 상태는 실제로 존재하지 않음 (실제 매수/매도는 사용자 수동)
- PAPER_HELD는 수익률 추적 전용. 알림 발송 없음
- 종목별로 독립적인 상태 관리 (dict: `{symbol: state}`)

**Repainting 정책**: watch list 진입/이탈은 봉 마감 대기 없이 **실시간(1분 폴링)** 으로 판단. 깜빡거려도 실제 손해 없음.

---

## 5. 시그널 정의

### 5.1 Signal Layer — WATCH 진입 조건 (IDLE → WATCH)

다음 **세 조건 모두** 만족 시 진입:

1. 30분봉 RSI(14)가 과거에 30 상향 돌파 발생 (이후로 watch 상태 유효)
2. 30분봉 RSI(14)가 35 상향 돌파
3. NASDAQ 30분봉 20MA 기울기 > 0

### 5.2 Signal Layer — WATCH 이탈 조건 (WATCH → IDLE)

다음 중 **하나라도** 만족 시 이탈:

- **Case A**: 30분봉 RSI(14) **30 하향 돌파** (← hysteresis: 진입 35, 이탈 30)
- **Case B**: NASDAQ 30분봉 20MA 기울기 < 0
- **Case C (TBD)**: 진입 후 N봉 이상 entry 조건 미발생 시 자동 제거. **운영하면서 조건 추가하기로 보류**

### 5.3 Entry Layer — 매수 알림 조건 (WATCH 상태에서)

WATCH 상태에 있는 종목에 대해 매 1분 폴링마다 평가. 다음 **네 조건 모두** 만족 시 텔레그램 알림 발송:

1. 5분봉 RSI(14) 35 상향 돌파
2. 5분봉 현재가가 최근 7봉 고점 돌파
3. 현재 5분봉 거래량 > 최근 20봉 평균 거래량
4. NASDAQ 5분봉 기울기 > 0

**알림 중복 방지**: 동일 종목에 대해 한 번 알림 발송 후 일정 쿨다운 적용. **TBD**: 쿨다운 길이 또는 "WATCH 재진입 전까지 알림 안 함" 규칙.

### 5.4 Paper Trading Exit (시뮬레이션 전용)

수익률 추적을 위해 paper position을 청산하는 조건. **알림 발송 없음, 내부 기록만**.

다음 중 **하나라도** 만족 시 청산:

- 5분봉 RSI(14) 35 하향 돌파
- 5분봉 종가가 최근 7봉 저점 이탈

**TBD**: 진입가는 알림 시점의 5분봉 종가 vs 다음 봉 시가? (슬리피지 모델)

---

## 6. Configuration (매직 넘버 통합)

모든 임계값/기간은 한 곳에 모아 관리한다 (yaml/json/dataclass 등):

```yaml
signal_layer:
  timeframe: 30m
  rsi_period: 14
  rsi_entry_low: 30      # 30 상향 돌파 발생 이력 필요
  rsi_entry_high: 35     # 35 상향 돌파 시 진입
  rsi_exit_low: 30       # 30 하향 돌파 시 이탈 (hysteresis)
  lookback_bars: 6       # "이전에 30 돌파했는지" 확인할 윈도우 (TBD: 의미 재정의 필요)

filter_layer:
  index_ticker: QQQ      # 또는 NASDAQ 직접 (TBD: 정확한 심볼)
  signal_ma_period: 20
  signal_ma_timeframe: 30m
  entry_ma_timeframe: 5m

entry_layer:
  timeframe: 5m
  rsi_period: 14
  rsi_threshold: 35
  breakout_bars: 7
  volume_ma_bars: 20

paper_trading:
  exit_rsi_threshold: 35
  exit_breakdown_bars: 7

polling:
  interval_seconds: 60

api:
  base_url: https://openapi.tossinvest.com
  token_refresh_buffer_seconds: 300  # 만료 5분 전 갱신
```

---

## 7. 미해결 / 검토 필요 (TBD 목록)

코드 작성 시작 전에 결정하거나, 적어도 "보류"라고 의식적으로 표시할 항목들.

### 7.1 정의의 모호함

- [ ] **"상승 돌파"의 정확한 부등호 위치**: `prev_rsi <= 30 AND curr_rsi > 30` 인지, `prev_rsi < 30 AND curr_rsi >= 30` 인지. (디테일하지만 신호 수가 바뀜)
- [ ] **"최근 7봉 고점"의 범위**: 현재 봉 포함인지 미포함인지
- [ ] **"현재 거래량"의 정의**: 진행 중인 5분봉의 누적 거래량(불완전) vs 직전 완료된 봉의 거래량
- [ ] **NASDAQ 심볼**: 토스에서 `QQQ`, `^IXIC`, `^NDX` 중 어떤 게 조회 가능한지 확인 필요

### 7.2 구조적 결정

- [ ] **기존 `detector.py`의 레이어 귀속**: 현재 함수는 lookback=6 + 30/35 조건. 너 머릿속엔 5분봉 entry 레이어용이었지만, readme의 30/35 조건은 signal 레이어 거. 이 함수를 signal 레이어로 재배치할지, 폐기하고 두 함수로 새로 짤지 결정 필요.
- [ ] **lookback_bars=6의 의미 재정의**: signal 레이어(30m)에 들어가면 "최근 3시간 내 30 돌파"가 되고, entry 레이어로 가면 "최근 30분 내" 가 됨. 둘 다 해석은 되지만 의도가 뭔지 명시 필요.
- [ ] **Case C 타임아웃**: 현재 "운영하면서 결정" 으로 보류. 메모로 남겨두고 paper trading 단계에서 횡보 종목 발생 시 재검토.

### 7.3 운영 관련

- [ ] **알림 쿨다운 정책**: 동일 종목 반복 알림 방지 규칙
- [ ] **봇 부팅 시 워밍업**: 히스토리 일괄 로드 vs 점진적 누적
- [ ] **토큰 만료/갱신 실패 시 동작**: 재시도 / 알림 / 정지?
- [ ] **rate limit 초과 시 동작**: 백오프 / 대기 / 알림?

### 7.4 검증

- [ ] **백테스트 하네스**: 알림봇 전용으로 단순화 가능. 과거 1분봉을 시간순으로 흘리면서 위 상태 머신을 그대로 돌리고, 각 알림 시점과 paper trading 수익률을 기록.
- [ ] **신호 품질 메트릭**: 알림 개수, 알림 후 N분 수익률, MDD 등

---

## 8. 다음 단계

1. **이 spec의 TBD 항목을 가능한 만큼 채운다** (§7)
2. **OAuth2 토큰 발급 + 캐싱/갱신 모듈** 작성
3. **데이터 어댑터** (`get_candles(symbol, interval, count)`) 작성. 1분봉 받아서 리샘플 + 페이지네이션 처리
4. **레이어별 시그널 함수**: `detect_watch_entry`, `detect_watch_exit`, `detect_buy_alert`, `detect_paper_exit`
5. **FSM 코어** + 종목별 상태 dict
6. **백테스트 하네스** (위 함수들을 그대로 재사용)
7. **폴링 루프 + 텔레그램 통합**
