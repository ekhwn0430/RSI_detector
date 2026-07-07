# RSI 알림봇

토스증권 Open API 기반 다중 타임프레임 RSI 매수 신호 텔레그램 알림봇.  
**매수 알림만 제공하며, 실제 주문 실행은 하지 않습니다.**

---

## 전략 개요

3-레이어 FSM(유한 상태 머신) 구조로 신호를 필터링합니다.

| 레이어 | 역할 | 타임프레임 |
|--------|------|-----------|
| Signal | 종목 관찰 리스트 진입/이탈 | 30분봉 |
| Filter | NASDAQ 20MA 기울기 게이트 | 30분봉 + 5분봉 |
| Entry  | 매수 알림 트리거 (봉 마감 시에만) | 5분봉 |

### 상태 전이

```
IDLE ──[Signal 진입]──► WATCH ──[Entry 조건]──► ALERTED
▲                         │
└──────[Signal 이탈]──────┘
```

### Signal 레이어 — WATCH 진입 조건 (3가지 모두)
1. 30분봉 RSI(14)가 과거 30을 상향 돌파한 이력 있음
2. 30분봉 RSI(14): `prev ≤ 35 AND curr > 35`
3. NASDAQ 30분봉 20MA 기울기 > 0

### Entry 레이어 — 매수 알림 조건 (4가지 모두, 봉 마감 시에만)
1. 5분봉 RSI(14): `prev ≤ 35 AND curr > 35`
2. 5분봉 종가 > 직전 7봉 최고가
3. 5분봉 거래량 > 직전 20봉 평균 거래량
4. NASDAQ 5분봉 20MA 기울기 > 0

---

## 파일 구조

```
RSI_detector/
├── config.py          # 모든 설정값 (임계값, 폴링 간격, WATCHLIST 등)
├── auth.py            # Toss OAuth2 토큰 발급 및 자동 갱신
├── data_loader.py     # Toss API 1분봉 조회 + 5m/30m 리샘플링
├── indicators.py      # Wilder RSI, 단순이동평균, 기울기
├── detector.py        # 신호 판단 함수 (stateless)
├── fsm.py             # 종목별 상태 머신
├── backtest.py        # 과거 데이터 백테스트 하네스
├── telegram.py        # 텔레그램 메시지 발송
├── main.py            # 라이브 폴링 루프 (진입점)
└── requirements.txt   # 의존 패키지
```

---

## 설치 및 설정

### 1. 패키지 설치

```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정

프로젝트 루트에 `.env` 파일을 생성합니다.

```
TOSS_CLIENT_ID=발급받은_client_id
TOSS_CLIENT_SECRET=발급받은_client_secret
TELEGRAM_BOT_TOKEN=봇_토큰
TELEGRAM_CHAT_ID=숫자_chat_id
```

- Toss 자격증명: [토스증권 Open API](https://openapi.tossinvest.com) 에서 발급
- Toss 개발자 포털에서 실행 서버의 외부 IP를 허용 목록에 추가 필요
- 텔레그램 봇: `@BotFather`에서 `/newbot`으로 생성
- Chat ID: 봇에 메시지 발송 후 `get_chat_id.py` 실행으로 확인

### 3. 감시 종목 설정

`config.py`에서 `WATCHLIST`에 종목 심볼을 추가합니다.

```python
WATCHLIST: list[str] = ["SOXL"]   # 국내주: 6자리 숫자, 미국주: 영문 티커
```

---

## 실행

```bash
python main.py
```

터미널에 실시간 상태 테이블이 표시되며, 매수 조건 충족 시 텔레그램으로 알림이 발송됩니다.

```
RSI 알림봇  |  현재 시각: 2026-07-07 09:00:00  |  마지막 폴링: 09:00:00
┌──────────┬────────────┬────────────┬────────────┬────────────────────┐
│   심볼   │  FSM 상태  │ RSI30 돌파 │  최근 종가 │     알림 시각      │
├──────────┼────────────┼────────────┼────────────┼────────────────────┤
│   SOXL   │    IDLE    │     X      │     194.08 │         -          │
└──────────┴────────────┴────────────┴────────────┴────────────────────┘
                          다음 폴링까지 58초
```

종료: `Ctrl+C`

---

## 주요 설정값 (`config.py`)

| 항목 | 기본값 | 설명 |
|------|--------|------|
| `POLL_INTERVAL_SEC` | 60 | 폴링 간격(초) |
| `NASDAQ_SYMBOL` | `"QQQ"` | NASDAQ 필터 ETF 심볼 |
| `RSI_PERIOD` | 14 | RSI 계산 기간 |
| `SIGNAL_RSI_ENTRY_LEVEL` | 35 | WATCH 진입 RSI 임계값 |
| `SIGNAL_RSI_EXIT_LEVEL` | 30 | WATCH 이탈 RSI 임계값 (hysteresis) |
| `ENTRY_BREAKOUT_BARS` | 7 | 고가 돌파 확인 봉 수 |
| `ENTRY_VOLUME_MA_BARS` | 20 | 거래량 이동평균 봉 수 |

---

## 데이터 흐름

```
Toss API (1분봉)
    ↓ 페이지네이션 조회
data_loader.py  →  pandas resample  →  5분봉 / 30분봉
    ↓
indicators.py   →  RSI(14), 20MA, slope
    ↓
detector.py     →  신호 판단 함수 (stateless bool 반환)
    ↓
fsm.py          →  종목별 IDLE / WATCH / ALERTED 상태 관리
    ↓
telegram.py     →  매수 알림 발송
```

---

## 백테스트

```python
from data_loader import get_candles
from backtest import run_backtest

df_1m        = get_candles("SOXL", "1m", 2000)
df_1m_nasdaq = get_candles("QQQ",  "1m", 2000)
trades = run_backtest("SOXL", df_1m, df_1m_nasdaq)

for t in trades:
    print(t)
```

---

## 주의사항

- 본 봇은 **매수 알림 전용**이며 실제 주문을 실행하지 않습니다.
- `.env` 파일에 실제 API 키가 포함되어 있으므로 절대 공개 저장소에 업로드하지 마세요.
- Toss API는 `1m`, `1d` 봉만 제공합니다. `5m`, `30m` 봉은 `1m`을 리샘플링하여 생성합니다.
- 봇 재시작 시 FSM 상태가 초기화되어 IDLE부터 다시 시작합니다.
