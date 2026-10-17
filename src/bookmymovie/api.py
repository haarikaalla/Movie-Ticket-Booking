import os
from datetime import UTC, datetime

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .database import Database
from .service import BookingService, SeatUnavailable


class HoldRequest(BaseModel):
    show_id: int
    customer_id: str = Field(min_length=1, max_length=100)
    seat_numbers: list[int] = Field(min_length=1, max_length=10)


class ConfirmRequest(BaseModel):
    hold_id: str


database = Database(os.environ.get("BOOKING_DB", "bookings.db"))
database.initialize()
service = BookingService(database)
app = FastAPI(title="BookMyMovie Inventory API", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}


@app.get("/v1/shows/{show_id}/availability")
def availability(show_id: int):
    try:
        return {"show_id": show_id, "available_seats": service.availability(show_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/v1/holds", status_code=201)
def create_hold(payload: HoldRequest):
    try:
        return service.hold_seats(payload.show_id, payload.customer_id, payload.seat_numbers)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SeatUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/bookings", status_code=201)
def confirm_booking(payload: ConfirmRequest, idempotency_key: str = Header(alias="Idempotency-Key")):
    try:
        return service.confirm(payload.hold_id, idempotency_key)
    except SeatUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
