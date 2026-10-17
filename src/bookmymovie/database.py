from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS movies (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  duration_minutes INTEGER NOT NULL CHECK(duration_minutes > 0)
);
CREATE TABLE IF NOT EXISTS shows (
  id INTEGER PRIMARY KEY,
  movie_id INTEGER NOT NULL REFERENCES movies(id),
  starts_at TEXT NOT NULL,
  auditorium TEXT NOT NULL,
  seat_count INTEGER NOT NULL CHECK(seat_count > 0)
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
  created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()
