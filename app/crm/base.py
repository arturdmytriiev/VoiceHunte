from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime as DateTime
from typing import Any

from pydantic import BaseModel, Field


class ReservationCreate(BaseModel):
    name: str
    datetime: DateTime
    people: int = Field(..., ge=1)
    phone: str | None = None
    notes: str | None = None


class ReservationUpdate(BaseModel):
    name: str | None = None
    datetime: DateTime | None = None
    people: int | None = Field(default=None, ge=1)
    phone: str | None = None
    notes: str | None = None


class ReservationRecord(BaseModel):
    reservation_id: int
    name: str
    datetime: DateTime
    people: int
    phone: str | None = None
    notes: str | None = None
    status: str


class CustomerPreferences(BaseModel):
    customer_key: str
    preferences: dict[str, Any]


class CustomerPreferencesRecord(BaseModel):
    customer_key: str
    preferences: dict[str, Any]
    updated_at: DateTime


class CRMAdapter(ABC):
    @abstractmethod
    def create_reservation(self, payload: ReservationCreate) -> ReservationRecord:
        raise NotImplementedError

    @abstractmethod
    def update_reservation(
        self, reservation_id: int, payload: ReservationUpdate
    ) -> ReservationRecord:
        raise NotImplementedError

    @abstractmethod
    def cancel_reservation(self, reservation_id: int) -> ReservationRecord:
        raise NotImplementedError

    @abstractmethod
    def save_preferences(
        self, payload: CustomerPreferences
    ) -> CustomerPreferencesRecord:
        raise NotImplementedError
