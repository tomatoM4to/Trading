from typing import Literal

from pydantic import BaseModel

ProductCode = Literal["01", "03", "08", "22", "29"]


class KisEnvironment(BaseModel):
    """ProductCode에 따라 필요한 인증 정보, 토큰, URL을 담는 환경 객체"""

    my_app: str
    my_sec: str
    my_acct: str
    my_prod: ProductCode
    my_htsid: str
    my_token: str
    my_url: str
    my_url_ws: str


class KisTokenResponse(BaseModel):
    """토큰 발급 API 응답 모델"""

    access_token: str
    access_token_token_expired: str


class KisConfig(BaseModel):
    """kis_devlp.yaml 파일의 내용을 담는 시스템 설정값"""

    my_app: str
    my_sec: str
    paper_app: str | None = None
    paper_sec: str | None = None
    my_htsid: str
    my_acct_stock: str
    my_acct_future: str | None = None
    my_paper_stock: str | None = None
    my_paper_future: str | None = None
    my_prod: ProductCode
    prod: str
    ops: str
    vps: str
    vops: str
    my_token: str
    my_agent: str

    def _require(self, key: str, value: str | None) -> str:
        if value is None or value == "":
            raise ValueError(f"kis_devlp.yaml required key is missing or empty: {key}")
        return value

    def app_credentials(self) -> tuple[str, str]:
        return self._require("my_app", self.my_app), self._require(
            "my_sec", self.my_sec
        )

    def select_account(self, product: ProductCode) -> str:
        account_by_product = {
            "01": self.my_acct_stock,
            "03": self.my_acct_future,
            "08": self.my_acct_future,
            "22": self.my_acct_stock,
            "29": self.my_acct_stock,
        }
        my_acct = account_by_product.get(product)
        return self._require(f"account for product={product}", my_acct)

    def api_url(self) -> str:
        return self._require("prod", self.prod)

    def ws_url(self) -> str:
        return self.ops or ""

    def to_environment(self, product: ProductCode, token_key: str) -> KisEnvironment:
        my_app, my_sec = self.app_credentials()
        return KisEnvironment(
            my_app=my_app,
            my_sec=my_sec,
            my_acct=self.select_account(product),
            my_prod=product,
            my_htsid=self.my_htsid,
            my_token=token_key,
            my_url=self.api_url(),
            my_url_ws=self.ws_url(),
        )
