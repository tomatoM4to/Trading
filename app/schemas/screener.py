from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class FilterNode(BaseModel):
    """개별 필터 조건을 정의하는 노드"""

    type: str = Field(description="필터 종류 (예: 'ma_alignment', 'ma_cross', 'convergence')")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="필터별 파라미터 (예: {'lines': ['ma_daily_5', 'ma_daily_20'], 'duration': 3})",
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

class ScreenerResponse(BaseModel):
    """스크리너 결과 응답 스키마"""
    items: list[ScreenerResultItem] = Field(description="조건을 만족하는 종목 목록")
    count: int = Field(description="조건을 만족하는 종목 수")
