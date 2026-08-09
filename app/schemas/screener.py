from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class FilterNode(BaseModel):
    """AST 트리의 단일 필터 노드 (프론트엔드의 블록에 대응)"""

    id: str = Field(description="필터 블록의 고유 ID (프론트엔드 UX 연동용)")
    type: str = Field(description="필터 타입 (예: ma_alignment, volume_surge 등)")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="필터별 세부 파라미터 (예: {'lines': ['ma_daily_5', 'ma_daily_20'], 'duration': 3})",
    )


class ScreenerRequest(BaseModel):
    """다중 필터와 연산자를 포함하는 스크리너 요청 스키마"""

    filters: list[FilterNode] = Field(description="순차적으로 실행할 필터들의 목록")
    operations: list[Literal["AND", "OR"]] = Field(
        default_factory=list,
        description="필터들 사이에 적용될 논리 연산자 목록 (길이는 필터 수 - 1)",
    )

    @model_validator(mode="after")
    def validate_operations_length(self):
        if not self.filters:
            raise ValueError("최소 1개 이상의 필터가 필요합니다.")

        expected_ops = len(self.filters) - 1
        if len(self.operations) != expected_ops:
            raise ValueError(
                f"필터가 {len(self.filters)}개이므로 연산자는 {expected_ops}개여야 합니다. (현재 {len(self.operations)}개)"
            )

        return self


class ScreenerResultItem(BaseModel):
    """스크리너 결과 단일 항목"""

    ticker: str = Field(description="종목 코드")
    name: str = Field(description="종목 이름")
    market: str | None = Field(default=None, description="시장 (KOSPI/KOSDAQ)")
    market_cap: float | None = Field(default=None, description="시가총액")
    close: float | None = Field(default=None, description="현재가")
    amount: float | None = Field(default=None, description="당일 누적 거래대금")
    change_rate: float | None = Field(default=None, description="전일 대비 등락률(%)")
    filter_values: dict[str, float] = Field(
        default_factory=dict, description="각 필터별 조건 부합 강도를 나타내는 추출 값"
    )


class ScreenerResponse(BaseModel):
    """스크리너 결과 응답 스키마"""

    items: list[ScreenerResultItem] = Field(description="조건을 만족하는 종목 목록")
    count: int = Field(description="조건을 만족하는 종목 수")
