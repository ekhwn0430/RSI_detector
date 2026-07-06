import time
import logging
import requests
from threading import Lock

from config import (
    TOSS_BASE_URL,
    TOSS_CLIENT_ID,
    TOSS_CLIENT_SECRET,
    TOKEN_REFRESH_BUFFER_SEC,
)

logger = logging.getLogger(__name__)


class TossAuth:
    """토스 OAuth2 access token 관리.

    - 처음 호출 시 토큰 발급
    - 만료 임박(5분 전) 시 자동 갱신
    - 외부에서 401 받으면 force_refresh()로 강제 갱신 가능
    """

    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret

        self._access_token: str | None = None
        self._expires_at: float = 0.0  # Unix timestamp (초)

        # 멀티스레드 환경 대비 (나중에 폴링 루프가 별도 스레드면 필요)
        self._lock = Lock()

    def get_token(self) -> str:
        """유효한 access token을 반환. 필요시 자동 갱신."""
        with self._lock:
            if self._needs_refresh():
                self._fetch_new_token()
            return self._access_token

    def force_refresh(self) -> str:
        """강제로 새 토큰 발급. 401 받았을 때 호출."""
        with self._lock:
            self._fetch_new_token()
            return self._access_token

    def _needs_refresh(self) -> bool:
        """토큰이 없거나, 만료가 buffer 시간 이내로 임박했는지."""
        if self._access_token is None:
            return True
        return time.time() >= (self._expires_at - TOKEN_REFRESH_BUFFER_SEC)

    def _fetch_new_token(self) -> None:
        """실제 /oauth2/token 호출."""
        url = f"{TOSS_BASE_URL}/oauth2/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret
        }
        # Content-Type은 requests가 data= 쓰면 자동으로
        # application/x-www-form-urlencoded 로 붙여줌

        logger.info("토스 access token 발급 요청")
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()  # 4xx/5xx 면 예외

        payload = response.json()
        # OAuth2 표준 응답: { access_token, token_type, expires_in, ... }
        self._access_token = payload["access_token"]
        expires_in = payload["expires_in"]  # 초 단위
        self._expires_at = time.time() + expires_in

        logger.info(f"토큰 발급 완료. {expires_in}초 후 만료")


# 모듈 전역 싱글톤 — 다른 파일에서 그냥 import 해서 쓰면 됨
auth = TossAuth(TOSS_CLIENT_ID, TOSS_CLIENT_SECRET)