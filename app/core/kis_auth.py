import copy
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import requests
import yaml
from schemas.core import (
    KisConfig,
    KisEnvironment,
    KisTokenResponse,
    ProductCode,
)

logger = logging.getLogger(__name__)

# config_root = ~/Software-Engineering
config_root = Path(__file__).resolve().parent.parent.parent


with open(os.path.join(config_root, "kis_devlp.yaml"), encoding="utf-8") as f:
    _kis_cfg: KisConfig = KisConfig.model_validate(yaml.safe_load(f))


"""
_kis_env: 토큰, 앱키, 스크릿키, 계좌번호, 접속 URL 등
_is_paper: 모의투자, 실전투자 구분, 기본값 False(실전투자)
_smart_sleep = 최소 대기 시간
"""
_kis_env: KisEnvironment | None = None
_token_expiry: datetime | None = None
_base_headers = {
    "Content-Type": "application/json",
    "Accept": "text/plain",
    "charset": "UTF-8",
    "User-Agent": _kis_cfg.my_agent,
}


def get_base_header():
    """_kis_env 설정값 기반, API 호출에 필요한 기본 header 값 반환"""
    return copy.deepcopy(_base_headers)


class KisAuthError(RuntimeError):
    pass


def auth(product: ProductCode = _kis_cfg.my_prod, force: bool = False) -> None:
    """
    - access_token 발급 및 파일 캐싱
    - _kis_env, _base_headers 갱신

    Args:
        product: 계좌상품코드 2자리 (예: 01/03/08/22/29)
        force: 파일 캐시를 무시하고 강제로 재발급 받을지 여부
    """

    def _get_token_path(now: datetime | None = None) -> Path:
        current = now or datetime.today()
        return config_root / f"KIS{current.strftime('%Y%m%d')}"

    def _read_token() -> tuple[str, datetime] | None:
        token_path = _get_token_path()
        if not token_path.is_file():
            return None

        try:
            with open(token_path, encoding="UTF-8") as f:
                tkg_tmp = yaml.load(f, Loader=yaml.FullLoader)
        except (OSError, yaml.YAMLError) as e:
            logger.debug("Failed to read or parse token file: %s", type(e).__name__)
            return None

        if not isinstance(tkg_tmp, dict):
            return None

        valid_date_val = tkg_tmp.get("valid-date")
        if not valid_date_val:
            return None

        if isinstance(valid_date_val, str):
            try:
                exp_dt = datetime.strptime(valid_date_val, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None
        elif isinstance(valid_date_val, datetime):
            exp_dt = valid_date_val
        else:
            return None

        now_dt = datetime.today()

        if exp_dt > now_dt:
            token = tkg_tmp.get("token")
            if isinstance(token, str) and token.strip():
                logger.info("Using cached token from %s", token_path.name)
                return token, exp_dt
        return None

    appkey, appsecret = _kis_cfg.app_credentials()

    saved_token = _read_token()

    if saved_token is None or force:
        p = {
            "grant_type": "client_credentials",
            "appkey": appkey,
            "appsecret": appsecret,
        }
        token_url = f"{_kis_cfg.api_url()}/oauth2/tokenP"
        try:
            res = requests.post(
                token_url,
                data=json.dumps(p),
                headers=copy.deepcopy(_base_headers),
                timeout=30,
            )
        except requests.RequestException:
            raise KisAuthError("KIS authentication request failed") from None
        if res.status_code != 200:
            raise KisAuthError(f"KIS authentication failed (HTTP {res.status_code})")

        try:
            token_response = KisTokenResponse.model_validate(res.json())
            my_tk = token_response.access_token
            my_exp = token_response.access_token_token_expired
            valid_date = datetime.strptime(my_exp, "%Y-%m-%d %H:%M:%S")
            if not my_tk.strip() or valid_date <= datetime.today():
                raise ValueError
        except ValueError:
            raise KisAuthError("Invalid KIS authentication response") from None

        token_path = _get_token_path()
        try:
            token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(token_path, "w", encoding="utf-8") as f:
                f.write(f"token: {my_tk}\n")
                f.write(f"valid-date: {valid_date.strftime('%Y-%m-%d %H:%M:%S')}\n")
        except OSError:
            raise KisAuthError("Failed to save KIS token cache") from None
        logger.sched("New token acquired and saved to %s", token_path.name)
    else:
        # 기존 토큰 사용
        my_tk, valid_date = saved_token

    # _kis_env 갱신
    global _kis_env, _token_expiry
    _kis_env = _kis_cfg.to_environment(product=product, token_key=my_tk)
    _token_expiry = valid_date

    _base_headers["authorization"] = f"Bearer {my_tk}"
    _base_headers["appkey"] = _kis_env.my_app if _kis_env else ""
    _base_headers["appsecret"] = _kis_env.my_sec if _kis_env else ""


def get_kis_cfg() -> KisConfig:
    return _kis_cfg


def get_kis_env() -> KisEnvironment:
    if _kis_env is None:
        raise KisAuthError("KIS authentication is not initialized")
    if _token_expiry is not None and _token_expiry <= datetime.today():
        raise KisAuthError("KIS authentication token has expired")
    return _kis_env
