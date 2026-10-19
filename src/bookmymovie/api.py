from __future__ import annotations

import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .database import Database
from .service import BookingNotFound, BookingService, SeatUnavailable


class HoldRequest(BaseModel):
    show_id: int = Field(gt=0)
    customer_id: str = Field(min_length=3, max_length=100)
    seat_numbers: list[int] = Field(min_length=1, max_length=10)


class ConfirmRequest(BaseModel):
    hold_id: str = Field(min_length=8, max_length=100)
    payment_method: str = Field(default="upi", pattern="^(upi|card|wallet)$")


class SeatEventHub:
    def __init__(self) -> None:
        self.connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, show_id: int, socket: WebSocket) -> None:
        await socket.accept()
        self.connections[show_id].add(socket)

    def disconnect(self, show_id: int, socket: WebSocket) -> None:
        self.connections[show_id].discard(socket)

    async def publish(self, show_id: int, event: str) -> None:
        stale: list[WebSocket] = []
        payload = {"type": event, "show_id": show_id, "at": datetime.now(UTC).isoformat()}
        for socket in self.connections[show_id]:
            try:
                await socket.send_json(payload)
            except RuntimeError:
                stale.append(socket)
        for socket in stale:
            self.disconnect(show_id, socket)


def create_app(database_path: str | Path | None = None, *, seed_demo: bool = True) -> FastAPI:
    database = Database(database_path or os.environ.get("BOOKING_DB", "bookings.db"))
    database.initialize()
    service = BookingService(database)
    if seed_demo:
        service.seed_demo_catalogue()
    hub = SeatEventHub()

    app = FastAPI(
        title="BookMyMovie Platform API",
        version="2.0.0",
        description="Concurrency-safe catalogue, live seat inventory, checkout, and booking API.",
    )
    app.state.service = service
    app.state.hub = hub
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["operations"])
    def health():
        return {"status": "ok", "version": "2.0.0", "time": datetime.now(UTC).isoformat()}

    @app.get("/v1/catalogue", tags=["catalogue"])
    def catalogue(
        city: str | None = Query(default=None, max_length=80),
        query: str | None = Query(default=None, max_length=100),
    ):
        return service.catalogue(city=city, query=query)

    @app.get("/v1/shows/{show_id}/seats", tags=["inventory"])
    def seats(show_id: int):
        try:
            return service.seat_map(show_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v1/shows/{show_id}/availability", tags=["inventory"])
    def availability(show_id: int):
        try:
            return {"show_id": show_id, "available_seats": service.availability(show_id)}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.websocket("/v1/shows/{show_id}/events")
    async def show_events(socket: WebSocket, show_id: int):
        await hub.connect(show_id, socket)
        try:
            await socket.send_json({"type": "connected", "show_id": show_id})
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            hub.disconnect(show_id, socket)

    @app.post("/v1/holds", status_code=201, tags=["checkout"])
    async def create_hold(payload: HoldRequest):
        try:
            result = service.hold_seats(payload.show_id, payload.customer_id, payload.seat_numbers)
            await hub.publish(payload.show_id, "inventory.changed")
            return result
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SeatUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/holds/{hold_id}", tags=["checkout"])
    def get_hold(hold_id: str):
        try:
            return service.get_hold(hold_id)
        except BookingNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/v1/holds/{hold_id}", tags=["checkout"])
    async def release_hold(hold_id: str):
        try:
            result = service.release_hold(hold_id)
            await hub.publish(result["show_id"], "inventory.changed")
            return result
        except BookingNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/bookings", status_code=201, tags=["checkout"])
    async def confirm_booking(
        payload: ConfirmRequest,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=120),
    ):
        try:
            result = service.confirm(payload.hold_id, idempotency_key, payload.payment_method)
            await hub.publish(result["show_id"], "inventory.changed")
            return result
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SeatUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/bookings/{booking_id}", tags=["bookings"])
    def get_booking(booking_id: str):
        try:
            return service.get_booking(booking_id)
        except BookingNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    static_dir = Path(__file__).parent / "static"
    if (static_dir / "index.html").exists():
        assets = static_dir / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/", include_in_schema=False)
        def frontend_index():
            return FileResponse(static_dir / "index.html")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend_fallback(path: str):
            requested = static_dir / path
            if requested.is_file() and static_dir in requested.resolve().parents:
                return FileResponse(requested)
            return FileResponse(static_dir / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def api_root():
            return {"name": "BookMyMovie", "docs": "/docs", "frontend": "run npm dev in frontend/"}

    return app


app = create_app()
