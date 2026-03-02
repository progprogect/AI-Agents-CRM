"""CRM stage models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.utils.datetime_utils import to_utc_iso_string, utc_now


class CRMStage(BaseModel):
    """CRM pipeline stage."""

    id: str = Field(..., description="Unique stage identifier (UUID)")
    name: str = Field(..., description="Stage display name")
    color: str = Field(..., description="Hex color code, e.g. #3B82F6")
    position: int = Field(..., description="Order position (0-based)")
    is_default: bool = Field(default=False, description="System stage — cannot be deleted")
    created_at: datetime = Field(default_factory=utc_now)

    class Config:
        json_encoders = {datetime: lambda v: to_utc_iso_string(v) if v else None}


class CreateCRMStageRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str = Field(default="#BEBAB7", pattern=r"^#[0-9A-Fa-f]{6}$")


class UpdateCRMStageRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    position: Optional[int] = Field(None, ge=0)
