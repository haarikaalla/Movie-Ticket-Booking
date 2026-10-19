from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS movies (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  duration_minutes INTEGER NOT NULL CHECK(duration_minutes > 0),
  synopsis TEXT NOT NULL DEFAULT '',
  genre TEXT NOT NULL DEFAULT 'Drama',
  language TEXT NOT NULL DEFAULT 'English',
  certificate TEXT NOT NULL DEFAULT 'U/A',
  rating REAL NOT NULL DEFAULT 0 CHECK(rating >= 0 AND rating <= 10),
  poster_gradient TEXT NOT NULL DEFAULT 'violet'
);
CREATE TABLE IF NOT EXISTS shows (
  id INTEGER PRIMARY KEY,
  movie_id INTEGER NOT NULL REFERENCES movies(id),
  starts_at TEXT NOT NULL,
  auditorium TEXT NOT NULL,
  seat_count INTEGER NOT NULL CHECK(seat_count > 0),
  seat_columns INTEGER NOT NULL DEFAULT 8 CHECK(seat_columns > 0),
  city TEXT NOT NULL DEFAULT 'Bengaluru',
  theatre TEXT NOT NULL DEFAULT 'Astra Cinemas',
  format TEXT NOT NULL DEFAULT '2D',
  base_price INTEGER NOT NULL DEFAULT 220 CHECK(base_price > 0)
);
CREATE TABLE IF NOT EXISTS holds (
  id TEXT PRIMARY KEY,
  show_id INTEGER NOT NULL REFERENCES shows(id),
  customer_id TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('active', 'confirmed', 'expired'))
);
CREATE TABLE IF NOT EXISTS hold_seats (
  hold_id TEXT NOT NULL REFERENCES holds(id),
  show_id INTEGER NOT NULL REFERENCES shows(id),
  seat_number INTEGER NOT NULL,
  PRIMARY KEY (hold_id, seat_number),
  UNIQUE (show_id, seat_number)
);
CREATE TABLE IF NOT EXISTS bookings (
  id TEXT PRIMARY KEY,
  hold_id TEXT NOT NULL UNIQUE REFERENCES holds(id),
  idempotency_key TEXT NOT NULL UNIQUE,
  customer_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  amount INTEGER NOT NULL DEFAULT 0,
  payment_method TEXT NOT NULL DEFAULT 'upi',
  payment_reference TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'confirmed' CHECK(status IN ('confirmed', 'cancelled', 'refunded'))
);
CREATE TABLE IF NOT EXISTS booking_events (
  id INTEGER PRIMARY KEY,
  booking_id TEXT NOT NULL REFERENCES bookings(id),
  event_type TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  metadata TEXT NOT NULL DEFAULT '{}'
);
"""

MIGRATIONS: dict[str, dict[str, str]] = {
    "movies": {
        "synopsis": "TEXT NOT NULL DEFAULT ''",
        "genre": "TEXT NOT NULL DEFAULT 'Drama'",
        "language": "TEXT NOT NULL DEFAULT 'English'",
        "certificate": "TEXT NOT NULL DEFAULT 'U/A'",
        "rating": "REAL NOT NULL DEFAULT 0",
        "poster_gradient": "TEXT NOT NULL DEFAULT 'violet'",
    },
    "shows": {
        "seat_columns": "INTEGER NOT NULL DEFAULT 8",
        "city": "TEXT NOT NULL DEFAULT 'Bengaluru'",
        "theatre": "TEXT NOT NULL DEFAULT 'Astra Cinemas'",
        "format": "TEXT NOT NULL DEFAULT '2D'",
        "base_price": "INTEGER NOT NULL DEFAULT 220",
    },
    "bookings": {
        "amount": "INTEGER NOT NULL DEFAULT 0",
        "payment_method": "TEXT NOT NULL DEFAULT 'upi'",
        "payment_reference": "TEXT NOT NULL DEFAULT ''",
        "status": "TEXT NOT NULL DEFAULT 'confirmed'",
    },
}


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            for table, columns in MIGRATIONS.items():
                existing = {
                    row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
                }
                for column, definition in columns.items():
                    if column not in existing:
                        connection.execute(
                            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                        )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_shows_city_starts_at ON shows(city, starts_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_holds_expiry ON holds(status, expires_at)"
            )

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()
