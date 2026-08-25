"""The committee's output contract.

T7: "Verdict carries action, price range, conviction 1-10, rationale."
DESK_DESIGN §1 W2's observed example: `HOLD / ACCUMULATE $191–196 · conviction 7/10`.

Validated with pydantic rather than trusted, because this is an LLM's output
and the failure mode is a confident, well-formatted, out-of-range number.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class Action(StrEnum):
    ACCUMULATE = "ACCUMULATE"
    HOLD = "HOLD"
    TRIM = "TRIM"
    EXIT = "EXIT"
    AVOID = "AVOID"


class Verdict(BaseModel):
    """One committee decision.

    NOTE what this does NOT carry: an order, a quantity, or a venue. D5 —
    no code path places a broker order — is structural, and the verdict schema
    is where that would first leak in.
    """

    ticker: str
    action: Action
    price_low: float | None = None
    price_high: float | None = None
    conviction: int = Field(ge=1, le=10, description="1-10, per T7")
    rationale: str = Field(min_length=1)

    @field_validator("ticker")
    @classmethod
    def _upper(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("ticker must not be empty")
        return cleaned

    @model_validator(mode="after")
    def _range_is_ordered(self) -> Verdict:
        low, high = self.price_low, self.price_high
        if low is not None and high is not None and low > high:
            raise ValueError(f"price range is inverted: {low} > {high}")
        if (low is None) != (high is None):
            raise ValueError("price range needs both bounds or neither")
        for bound in (low, high):
            if bound is not None and bound <= 0:
                raise ValueError(f"price bound must be positive, got {bound}")
        return self

    def render(self) -> str:
        band = ""
        if self.price_low is not None and self.price_high is not None:
            band = f" ${self.price_low:g}–{self.price_high:g}"
        return f"{self.action.value}{band} · conviction {self.conviction}/10"
