import logging

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

_BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def send_message(text: str) -> None:
    """텔레그램 봇으로 메시지를 발송한다.

    .env에 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 가 비어 있으면 경고만 남기고 건너뜀.
    발송 실패(네트워크 오류, 잘못된 chat_id 등)는 예외를 올리지 않고 로그만 남긴다.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("텔레그램 설정 미완료(BOT_TOKEN 또는 CHAT_ID 없음) — 발송 건너뜀")
        return

    url = f"{_BASE_URL}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",   # <b>굵게</b> 같은 기본 HTML 태그 사용 가능
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.debug(f"텔레그램 발송 완료: {text[:40]}…")
    except requests.HTTPError as exc:
        logger.error(f"텔레그램 HTTP 오류: {exc.response.status_code} {exc.response.text}")
    except Exception as exc:
        logger.error(f"텔레그램 발송 실패: {exc}")
