from __future__ import annotations

import json
import math
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta

from .database import Database


class SeatUnavailable(RuntimeError):
    pass


class BookingNotFound(RuntimeError):
    pass


class BookingService:
    """Transactional catalogue, seat inventory, checkout, and booking domain service."""

    def __init__(self, database: Database, hold_minutes: int = 5):
        self.database = database
        self.hold_minutes = hold_minutes

    def create_movie(
        self,
        title: str,
        duration_minutes: int,
        *,
        synopsis: str = "",
        genre: str = "Drama",
        language: str = "English",
        certificate: str = "U/A",
        rating: float = 0,
        poster_gradient: str = "violet",
    ) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO movies(
                    title, duration_minutes, synopsis, genre, language,
                    certificate, rating, poster_gradient
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title.strip(), duration_minutes, synopsis.strip(), genre, language,
                    certificate, rating, poster_gradient,
                ),
            )
            return int(cursor.lastrowid)

    def create_show(
        self,
        movie_id: int,
        starts_at: datetime,
        auditorium: str,
        seat_count: int,
        *,
        city: str = "Bengaluru",
        theatre: str = "Astra Cinemas",
        show_format: str = "2D",
        base_price: int = 220,
        seat_columns: int = 8,
    ) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO shows(
                    movie_id, starts_at, auditorium, seat_count, seat_columns,
                    city, theatre, format, base_price
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    movie_id, starts_at.astimezone(UTC).isoformat(), auditorium.strip(),
                    seat_count, seat_columns, city.strip(), theatre.strip(), show_format, base_price,
                ),
            )
            return int(cursor.lastrowid)

    def seed_demo_catalogue(self) -> None:
        with self.database.connect() as connection:
            if connection.execute("SELECT COUNT(*) FROM movies").fetchone()[0]:
                return

        movies = [
            {
                "title": "Beyond the Red Sky",
                "duration_minutes": 142,
                "synopsis": "A rescue crew crosses an unstable Martian canyon to recover a lost research team.",
                "genre": "Sci-Fi · Adventure",
                "language": "English",
                "certificate": "U/A 13+",
                "rating": 8.7,
                "poster_gradient": "ember",
            },
            {
                "title": "Monsoon Letters",
                "duration_minutes": 128,
                "synopsis": "Two lives reconnect through letters delivered across a rain-soaked Bengaluru.",
                "genre": "Drama · Romance",
                "language": "Hindi",
                "certificate": "U",
                "rating": 8.3,
                "poster_gradient": "ocean",
            },
            {
                "title": "The Last Algorithm",
                "duration_minutes": 154,
                "synopsis": "A systems engineer races to contain an intelligence that can predict every choice.",
                "genre": "Tech Thriller",
                "language": "English",
                "certificate": "U/A 16+",
                "rating": 9.1,
                "poster_gradient": "electric",
            },
            {
                "title": "Namma 2049",
                "duration_minutes": 136,
                "synopsis": "A warm, hopeful story about rebuilding community in tomorrow's Bengaluru.",
                "genre": "Comedy · Drama",
                "language": "Kannada",
                "certificate": "U",
                "rating": 8.5,
                "poster_gradient": "sunset",
            },
        ]
        movie_ids = [self.create_movie(**movie) for movie in movies]
        start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
        theatres = ["Astra Orion", "Cinewave Indiranagar", "Nova Forum"]
        for movie_index, movie_id in enumerate(movie_ids):
            for show_index, hour_offset in enumerate((movie_index, movie_index + 4, movie_index + 8)):
                self.create_show(
                    movie_id,
                    start + timedelta(hours=hour_offset),
                    f"Screen {show_index + 1}",
                    48,
                    city="Bengaluru",
                    theatre=theatres[show_index],
                    show_format="IMAX" if show_index == 1 else "2D",
                    base_price=220 + (show_index * 40),
                )

    def catalogue(self, city: str | None = None, query: str | None = None) -> dict:
        filters: list[str] = []
        params: list[str] = []
        if city:
            filters.append("s.city = ?")
            params.append(city)
        if query:
            filters.append("(LOWER(m.title) LIKE ? OR LOWER(m.genre) LIKE ?)")
            needle = f"%{query.lower()}%"
            params.extend([needle, needle])
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        sql = f"""
            SELECT m.*, s.id AS show_id, s.starts_at, s.auditorium, s.city,
                   s.theatre, s.format, s.base_price
            FROM movies m JOIN shows s ON s.movie_id = m.id
            {where}
            ORDER BY m.rating DESC, s.starts_at
        """
        with self.database.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
            cities = [row[0] for row in connection.execute("SELECT DISTINCT city FROM shows ORDER BY city")]

        movies: dict[int, dict] = {}
        for row in rows:
            movie = movies.setdefault(
                row["id"],
                {
                    "id": row["id"], "title": row["title"],
                    "duration_minutes": row["duration_minutes"], "synopsis": row["synopsis"],
                    "genre": row["genre"], "language": row["language"],
                    "certificate": row["certificate"], "rating": row["rating"],
                    "poster_gradient": row["poster_gradient"], "shows": [],
                },
            )
            movie["shows"].append(
                {
                    "id": row["show_id"], "starts_at": row["starts_at"],
                    "auditorium": row["auditorium"], "city": row["city"],
                    "theatre": row["theatre"], "format": row["format"],
                    "from_price": row["base_price"],
                }
            )
        return {"cities": cities, "movies": list(movies.values())}

    def _expire_holds(self, connection: sqlite3.Connection, now: datetime) -> list[int]:
        expired = connection.execute(
            "SELECT id, show_id FROM holds WHERE status = 'active' AND expires_at <= ?",
            (now.isoformat(),),
        ).fetchall()
        for row in expired:
            connection.execute("DELETE FROM hold_seats WHERE hold_id = ?", (row["id"],))
            connection.execute("UPDATE holds SET status = 'expired' WHERE id = ?", (row["id"],))
        return sorted({int(row["show_id"]) for row in expired})

    @staticmethod
    def _seat_details(seat_number: int, seat_count: int, columns: int, base_price: int) -> dict:
        row_index = (seat_number - 1) // columns
        row_count = math.ceil(seat_count / columns)
        column = ((seat_number - 1) % columns) + 1
        row = chr(ord("A") + row_index)
        if row_index == row_count - 1:
            tier, premium = "Recliner", 120
        elif row_index >= max(2, row_count // 2):
            tier, premium = "Prime", 60
        else:
            tier, premium = "Classic", 0
        return {
            "number": seat_number, "label": f"{row}{column}", "row": row,
            "column": column, "tier": tier, "price": base_price + premium,
        }

    def seat_map(self, show_id: int) -> dict:
        now = datetime.now(UTC)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._expire_holds(connection, now)
            show = connection.execute(
                """
                SELECT s.*, m.title, m.duration_minutes, m.certificate
                FROM shows s JOIN movies m ON m.id = s.movie_id WHERE s.id = ?
                """,
                (show_id,),
            ).fetchone()
            if show is None:
                connection.rollback()
                raise ValueError("show does not exist")
            occupied = {
                row["seat_number"]: row["status"]
                for row in connection.execute(
                    """
                    SELECT hs.seat_number, h.status
                    FROM hold_seats hs JOIN holds h ON h.id = hs.hold_id
                    WHERE hs.show_id = ?
                    """,
                    (show_id,),
                )
            }
            connection.commit()

        seats = []
        for number in range(1, show["seat_count"] + 1):
            seat = self._seat_details(number, show["seat_count"], show["seat_columns"], show["base_price"])
            status = occupied.get(number)
            seat["status"] = "booked" if status == "confirmed" else "held" if status else "available"
            seats.append(seat)
        return {
            "show": {
                "id": show["id"], "movie_title": show["title"],
                "duration_minutes": show["duration_minutes"], "certificate": show["certificate"],
                "starts_at": show["starts_at"], "auditorium": show["auditorium"],
                "city": show["city"], "theatre": show["theatre"], "format": show["format"],
            },
            "layout": {"columns": show["seat_columns"], "seat_count": show["seat_count"]},
            "seats": seats,
        }

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
                show = connection.execute("SELECT * FROM shows WHERE id = ?", (show_id,)).fetchone()
                if show is None:
                    raise ValueError("show does not exist")
                if seats[0] < 1 or seats[-1] > show["seat_count"]:
                    raise ValueError("seat number is outside the auditorium")
                connection.execute(
                    "INSERT INTO holds(id, show_id, customer_id, expires_at, status) VALUES (?, ?, ?, ?, 'active')",
                    (hold_id, show_id, customer_id.strip(), expires_at.isoformat()),
                )
                connection.executemany(
                    "INSERT INTO hold_seats(hold_id, show_id, seat_number) VALUES (?, ?, ?)",
                    [(hold_id, show_id, seat) for seat in seats],
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise SeatUnavailable("one or more seats were just selected by another customer") from exc
            except Exception:
                connection.rollback()
                raise

        details = [
            self._seat_details(seat, show["seat_count"], show["seat_columns"], show["base_price"])
            for seat in seats
        ]
        return {
            "hold_id": hold_id, "show_id": show_id, "seats": details,
            "amount": sum(seat["price"] for seat in details),
            "expires_at": expires_at.isoformat(), "status": "active",
        }

    def get_hold(self, hold_id: str) -> dict:
        now = datetime.now(UTC)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._expire_holds(connection, now)
            hold = connection.execute(
                """
                SELECT h.*, s.seat_count, s.seat_columns, s.base_price,
                       s.starts_at, s.theatre, s.auditorium, m.title
                FROM holds h JOIN shows s ON s.id = h.show_id
                JOIN movies m ON m.id = s.movie_id WHERE h.id = ?
                """,
                (hold_id,),
            ).fetchone()
            if hold is None:
                connection.rollback()
                raise BookingNotFound("hold does not exist")
            numbers = [
                row[0] for row in connection.execute(
                    "SELECT seat_number FROM hold_seats WHERE hold_id = ? ORDER BY seat_number", (hold_id,)
                )
            ]
            connection.commit()
        seats = [
            self._seat_details(number, hold["seat_count"], hold["seat_columns"], hold["base_price"])
            for number in numbers
        ]
        return {
            "hold_id": hold["id"], "show_id": hold["show_id"],
            "customer_id": hold["customer_id"], "status": hold["status"],
            "expires_at": hold["expires_at"], "movie_title": hold["title"],
            "theatre": hold["theatre"], "auditorium": hold["auditorium"],
            "starts_at": hold["starts_at"], "seats": seats,
            "amount": sum(seat["price"] for seat in seats),
        }

    def release_hold(self, hold_id: str) -> dict:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            hold = connection.execute("SELECT * FROM holds WHERE id = ?", (hold_id,)).fetchone()
            if hold is None:
                connection.rollback()
                raise BookingNotFound("hold does not exist")
            if hold["status"] == "active":
                connection.execute("DELETE FROM hold_seats WHERE hold_id = ?", (hold_id,))
                connection.execute("UPDATE holds SET status = 'expired' WHERE id = ?", (hold_id,))
            connection.commit()
        return {"hold_id": hold_id, "show_id": hold["show_id"], "status": "released"}

    def confirm(self, hold_id: str, idempotency_key: str, payment_method: str = "upi") -> dict:
        now = datetime.now(UTC)
        if not idempotency_key.strip():
            raise ValueError("idempotency key is required")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT * FROM bookings WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if previous:
                if previous["hold_id"] != hold_id:
                    connection.rollback()
                    raise SeatUnavailable("idempotency key is already associated with another checkout")
                result = self._booking_result(connection, previous)
                connection.commit()
                return result
            self._expire_holds(connection, now)
            hold = connection.execute("SELECT * FROM holds WHERE id = ?", (hold_id,)).fetchone()
            if hold is None or hold["status"] != "active":
                connection.rollback()
                raise SeatUnavailable("hold is missing or expired")
            show = connection.execute("SELECT * FROM shows WHERE id = ?", (hold["show_id"],)).fetchone()
            numbers = [
                row[0] for row in connection.execute(
                    "SELECT seat_number FROM hold_seats WHERE hold_id = ? ORDER BY seat_number", (hold_id,)
                )
            ]
            amount = sum(
                self._seat_details(number, show["seat_count"], show["seat_columns"], show["base_price"])["price"]
                for number in numbers
            )
            booking_id = str(uuid.uuid4())
            payment_reference = f"PAY-{uuid.uuid4().hex[:12].upper()}"
            connection.execute(
                """
                INSERT INTO bookings(
                    id, hold_id, idempotency_key, customer_id, created_at,
                    amount, payment_method, payment_reference, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'confirmed')
                """,
                (
                    booking_id, hold_id, idempotency_key, hold["customer_id"], now.isoformat(),
                    amount, payment_method, payment_reference,
                ),
            )
            connection.execute("UPDATE holds SET status = 'confirmed' WHERE id = ?", (hold_id,))
            connection.execute(
                "INSERT INTO booking_events(booking_id, event_type, occurred_at, metadata) VALUES (?, 'confirmed', ?, ?)",
                (booking_id, now.isoformat(), json.dumps({"amount": amount, "method": payment_method})),
            )
            booking = connection.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
            result = self._booking_result(connection, booking)
            connection.commit()
            return result

    def _booking_result(self, connection: sqlite3.Connection, booking: sqlite3.Row) -> dict:
        context = connection.execute(
            """
            SELECT h.show_id, s.starts_at, s.theatre, s.auditorium, s.format,
                   s.seat_count, s.seat_columns, s.base_price, m.title
            FROM holds h JOIN shows s ON s.id = h.show_id
            JOIN movies m ON m.id = s.movie_id WHERE h.id = ?
            """,
            (booking["hold_id"],),
        ).fetchone()
        numbers = [
            row[0] for row in connection.execute(
                "SELECT seat_number FROM hold_seats WHERE hold_id = ? ORDER BY seat_number", (booking["hold_id"],)
            )
        ]
        seats = [
            self._seat_details(number, context["seat_count"], context["seat_columns"], context["base_price"])
            for number in numbers
        ]
        return {
            "id": booking["id"], "hold_id": booking["hold_id"],
            "customer_id": booking["customer_id"], "created_at": booking["created_at"],
            "status": booking["status"], "amount": booking["amount"],
            "payment_method": booking["payment_method"],
            "payment_reference": booking["payment_reference"],
            "movie_title": context["title"], "show_id": context["show_id"],
            "starts_at": context["starts_at"], "theatre": context["theatre"],
            "auditorium": context["auditorium"], "format": context["format"], "seats": seats,
        }

    def get_booking(self, booking_id: str) -> dict:
        with self.database.connect() as connection:
            booking = connection.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
            if booking is None:
                raise BookingNotFound("booking does not exist")
            return self._booking_result(connection, booking)

    def availability(self, show_id: int) -> list[int]:
        seat_map = self.seat_map(show_id)
        return [seat["number"] for seat in seat_map["seats"] if seat["status"] == "available"]
