import asyncio
import logging

import requests
from core import kis_auth as ka

logger = logging.getLogger(__name__)

_SENSITIVE_LOG_KEYS = {
    "authorization",
    "appkey",
    "appsecret",
    "token",
    "access_token",
}


def redact_headers(headers: dict) -> dict:
    """Return a log-safe copy without KIS credentials."""
    return {
        key: "***" if str(key).lower() in _SENSITIVE_LOG_KEYS else value
        for key, value in headers.items()
    }


class DotDict(dict):
    """
    dict의 키를 속성처럼 접근할 수 있게 해주는 래퍼 클래스.
    중첩된 dict와 list 내부의 dict까지 모두 재귀적으로 래핑합니다.
    존재하지 않는 속성에 접근 시 ""(빈 문자열)을 반환하여 getattr 호환성을 유지합니다.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, value in self.items():
            self[key] = self._wrap(value)

    def _wrap(self, value):
        if isinstance(value, dict):
            return DotDict(value)
        elif isinstance(value, list):
            return [self._wrap(v) for v in value]
        return value

    def __getattr__(self, name):
        return self.get(name, "")

    def __setattr__(self, name, value):
        self[name] = self._wrap(value)

    def __delattr__(self, name):
        if name in self:
            del self[name]
        else:
            raise AttributeError(f"No such attribute: {name}")


class APIResp:
    def __init__(self, resp: requests.Response):
        self._resp = resp
        self._rescode = resp.status_code
        self._is_success = self._rescode == 200

        self._header = DotDict()
        self._body = DotDict()
        self._err_code = str(self._rescode)
        self._err_message = resp.text

        if self._is_success:
            try:
                # 헤더 파싱 (소문자 키만 추출)
                self._header = DotDict(
                    {k: v for k, v in resp.headers.items() if k.islower()}
                )

                # 바디 파싱
                self._body = DotDict(resp.json())

                self._err_code = self._body.msg_cd
                self._err_message = self._body.msg1
            except Exception as e:
                self._is_success = False
                self._err_message = f"JSON Parse Error: {e}"

    def get_res_code(self):
        return self._rescode

    def get_header(self):
        return self._header

    def get_body(self):
        return self._body

    def get_response(self):
        return self._resp

    def is_ok(self):
        if not self._is_success:
            return False
        return self._body.rt_cd == "0"

    def get_error_code(self):
        return self._err_code

    def get_error_message(self):
        return self._err_message

    def print_all(self):
        if not self._is_success:
            logger.error("=== ERROR RESPONSE ===")
            logger.error(
                "Status Code: %s | Message: %s", self._rescode, self._err_message
            )
            return

        logger.debug("<Header>")
        for k, v in self._header.items():
            logger.debug("\t-%s: %s", k, v)
        logger.debug("<Body>")
        for k, v in self._body.items():
            if isinstance(v, list):
                logger.debug("\t-%s: list(len=%d)", k, len(v))
            else:
                logger.debug("\t-%s: %s", k, v)

    def print_error(self, url: str = ""):
        logger.error(
            "Error Code: %s | rt_cd: %s | msg_cd: %s | msg1: %s | URL: %s",
            self._rescode,
            self._body.rt_cd or "N/A",
            self._err_code,
            self._err_message,
            url,
        )


# -------------------------------------------------------------------------
# 비동기 큐(Queue) 기반 KIS API 초당 20건 제한 제어 시스템
# -------------------------------------------------------------------------
_kis_queue: asyncio.PriorityQueue | None = None
_kis_worker_task: asyncio.Task | None = None
_kis_task_counter: int = 0


async def start_q_worker():
    """
    FastAPI Lifespan이나 앱 초기화 시점에 호출되는 워커 실행 함수.
    """
    global _kis_queue, _kis_worker_task

    async def request_consumer():
        """
        큐에서 이벤트를 꺼내 비동기(쓰레드풀)로 API를 요청하고,
        무조건 0.05초 대기하여 Rate Limit을 방어합니다.
        """
        while True:
            try:
                item = await _kis_queue.get()
                priority, _counter, payload = item
                future, request_kwargs = payload

                try:
                    # 동기 requests가 이벤트 루프를 블로킹하지 않도록 분리 실행
                    res = await asyncio.to_thread(_do_fetch, **request_kwargs)
                    if not future.done():
                        future.set_result(res)
                except Exception as e:
                    if not future.done():
                        future.set_exception(e)
                finally:
                    _kis_queue.task_done()

                # 2026.04 KIS 공식 가이드 반영: 동시 호출 시 100ms ~ 150ms 텀 권장
                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                getattr(logger, "sched", logger.info)(
                    "[KIS Async Worker] Worker task cancelled."
                )
                break
            except Exception as e:
                logger.error(
                    "[KIS Async Worker] Unexpected error in consumer loop: %s", e
                )

    if _kis_worker_task is None or _kis_worker_task.done():
        if _kis_queue is None:
            _kis_queue = asyncio.PriorityQueue()
        _kis_worker_task = asyncio.create_task(request_consumer())
        getattr(logger, "sched", logger.info)(
            "[KIS Async Worker] Started background worker (Target: %s req/sec)",
            1 / 0.1,
        )


async def stop_q_worker():
    """앱 종료 시 백그라운드 워커를 안전하게 종료합니다."""
    global _kis_queue, _kis_worker_task
    if _kis_worker_task is not None:
        _kis_worker_task.cancel()
        try:
            await _kis_worker_task
        except asyncio.CancelledError:
            pass
        _kis_worker_task = None
        _kis_queue = None
        getattr(logger, "sched", logger.info)(
            "[KIS Async Worker] Worker task stopped safely."
        )


def _do_fetch(
    api_url: str,
    ptr_id: str,
    tr_cont: str,
    params: dict,
    append_headers: dict = None,
    post_flag: bool = False,
) -> APIResp:
    """백그라운드 워커에서 실제 통신을 수행하는 동기 함수"""
    url = f"{ka.get_kis_env().my_url}{api_url}"
    headers = ka.get_base_header()

    tr_id = ptr_id
    headers.update({"tr_id": tr_id, "custtype": "P", "tr_cont": tr_cont})

    if append_headers:
        headers.update(append_headers)

    logger.debug(
        "< Sending Info >\nURL: %s, TR: %s\n<header>\n%s\n<body>\n%s",
        url,
        tr_id,
        redact_headers(headers),
        params,
    )

    if post_flag:
        res = requests.post(url, headers=headers, json=params, timeout=10)
    else:
        res = requests.get(url, headers=headers, params=params, timeout=10)

    ar = APIResp(res)

    if not ar.is_ok():
        logger.error("Error Code : %s | %s", res.status_code, res.text)
    elif logger.isEnabledFor(logging.DEBUG):
        ar.print_all()

    return ar


async def async_kis_fetch(
    api_url: str,
    ptr_id: str,
    tr_cont: str,
    params: dict,
    append_headers: dict = None,
    post_flag: bool = False,
    priority: int = 5,
) -> APIResp:
    """
    라우터/서비스 계층에서 호출할 비동기(async) API.
    요청 정보와 약속 어음(Future)을 Queue에 넣고 대기합니다.
    """
    global _kis_queue, _kis_task_counter
    if _kis_queue is None:
        await start_q_worker()

    loop = asyncio.get_running_loop()
    future = loop.create_future()
    request_kwargs = {
        "api_url": api_url,
        "ptr_id": ptr_id,
        "tr_cont": tr_cont,
        "params": params,
        "append_headers": append_headers,
        "post_flag": post_flag,
    }

    _kis_task_counter += 1
    # 큐 탑승 (priority가 낮을수록 우선 처리)
    await _kis_queue.put((priority, _kis_task_counter, (future, request_kwargs)))

    # 응답이 도착할 때까지 비동기 대기
    return await future
