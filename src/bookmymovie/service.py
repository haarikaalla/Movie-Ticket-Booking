from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime, timedelta

from .database import Database


class SeatUnavailable(RuntimeError):
    pass


class BookingService:
    """Transactional seat inventory with expiring holds and idempotent checkout."""

    def __init__(self, database: Database, hold_minutes: int = 5):
        self.database = database
        self.hold_minutes = hold_minutes

    def create_movie(self, title: str, duration_minutes: int) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO movies(title, duration_minutes) VALUES (?, ?)",
                (title.strip(), duration_minutes),
            )
            return int(cursor.lastrowid)

    def create_show(self, movie_id: int, starts_at: datetime, auditorium: str, seat_count: int) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO shows(movie_id, starts_at, auditorium, seat_count) VALUES (?, ?, ?, ?)",
                (movie_id, starts_at.astimezone(UTC).isoformat(), auditorium, seat_count),
            )
            return int(cursor.lastrowid)

    def _expire_holds(self, connection: sqlite3.Connection, now: datetime) -> None:
        expired = connection.execute(
            "SELECT id FROM holds WHERE status = 'active' AND expires_at <= ?",
            (now.isoformat(),),
        ).fetchall()
        for row in expired:
            connection.execute("DELETE FROM hold_seats WHERE hold_id = ?", (row["id"],))
            connection.execute("UPDATE holds SET status = 'expired' WHERE id = ?", (row["id"],))

    def hold_seats(self, show_id: int, customer_id: str, seat_numbers: list[int]) -> dict:
        seats = sorted(set(seat_numbers))
        if not customer_id.strip() or not seats:
            raise ValueError("customer_id and at least one seat are required")

        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self.hold_minutes)
        hold_id = str(uuid.uuid4())
        with self.database.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._expire_holds(connection, now)
                show = connection.execute(
                    "SELECT seat_count FROM shows WHERE id = ?", (show_id,)
                ).fetchone()
                if show is None:
                    raise ValueError("show does not exist")
                if seats[0] < 1 or seats[-1] > show["seat_count"]:
                    raise ValueError("seat number is outside the auditorium")
                connection.execute(
                    "INSERT INTO holds(id, show_id, customer_id, expires_at, status) VALUES (?, ?, ?, ?, 'active')",
                    (hold_id, show_id, customer_id, expires_at.isoformat()),
                )
                connection.executemany(
                    "INSERT INTO hold_seats(hold_id, show_id, seat_number) VALUES (?, ?, ?)",
                    [(hold_id, show_id, seat) for seat in seats],
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise SeatUnavailable("one or more seats are already held or booked") from exc
            except Exception:
                connection.rollback()
                raise
        return {"hold_id": hold_id, "show_id": show_id, "seats": seats, "expires_at": expires_at.isoformat()}

    def confirm(self, hold_id: str, idempotency_key: str) -> dict:
        now = datetime.now(UTC)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT * FROM bookings WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if previous:
                connection.commit()
                return dict(previous)
            self._expire_holds(connection, now)
            hold = connection.execute("SELECT * FROM holds WHERE id = ?", (hold_id,)).fetchone()
            if hold is None or hold["status"] != "active":
                connection.rollback()
                raise SeatUnavailable("hold is missing or expired")
            booking_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO bookings(id, hold_id, idempotency_key, customer_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (booking_id, hold_id, idempotency_key, hold["customer_id"], now.isoformat()),
            )
            connection.execute("UPDATE holds SET status = 'confirmed' WHERE id = ?", (hold_id,))
            connection.commit()
            return {
                "id": booking_id,
                "hold_id": hold_id,
                "idempotency_key": idempotency_key,
                "customer_id": hold["customer_id"],
                "created_at": now.isoformat(),
            }

    def availability(self, show_id: int) -> list[int]:
        now = datetime.now(UTC)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._expire_holds(connection, now)
            show = connection.execute("SELECT seat_count FROM shows WHERE id = ?", (show_id,)).fetchone()
            if show is None:
                connection.rollback()
                raise ValueError("show does not exist")
            unavailable = {
                row["seat_number"]
                for row in connection.execute(
                    "SELECT seat_number FROM hold_seats WHERE show_id = ?", (show_id,)
                )
            }
            connection.commit()
        return [seat for seat in range(1, show["seat_count"] + 1) if seat not in unavailable]
