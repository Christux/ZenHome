"""Business validation models for ZenHome."""

from typing import Literal

from pydantic import BaseModel, Field


class ItemCreate(BaseModel):
    """Payload used to create a new item in the system."""

    title: str = Field(min_length=1, max_length=250)
    content: str | None = None
    type_code: Literal["NOTE", "CHECKLIST", "TASK"] = "NOTE"
    status_code: Literal["TODO", "IN_PROGRESS", "DONE", "CANCELLED"] = "TODO"


class ItemStatusUpdate(BaseModel):
    """Payload used to update an item's status."""

    status_code: Literal["TODO", "IN_PROGRESS", "DONE", "CANCELLED"]


class ItemUpdate(BaseModel):
    """Payload used to edit the mutable fields of an item."""

    title: str | None = Field(default=None, min_length=1, max_length=250)
    content: str | None = None


class ChecklistInput(BaseModel):
    """Payload used to create or update a checklist row."""

    label: str = Field(min_length=1, max_length=250)
    position: int | None = Field(default=None, ge=0)
    is_checked: bool | None = None


class RuleInput(BaseModel):
    """Payload used to define a recurrence rule."""

    recurrence_type_code: str
    label: str = Field(min_length=1, max_length=100)
    expression: str = Field(min_length=1, max_length=100)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    month_of_year: int | None = Field(default=None, ge=1, le=12)
    weekdays: list[int] = []


class ScheduleInput(BaseModel):
    """Payload used to create an occurrence schedule."""

    start_at: str = Field(min_length=1)
    end_at: str | None = None
    recurrence_rule_id: int | None = None
    is_active: bool = True


class NotificationConfigInput(BaseModel):
    """Payload used to define a notification configuration."""

    label: str | None = Field(default=None, max_length=100)
    offset_minutes: int = 0
    is_enabled: bool = True


class StatusInput(BaseModel):
    """Payload used to update the state of a business entity."""

    code: str
    error_message: str | None = None
