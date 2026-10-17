from datetime import UTC, datetime, timedelta

import pytest

from bookmymovie import BookingService, SeatUnavailable
from bookmymovie.database import Database


@pytest.fixture
def service(tmp_path):
    database = Database(tmp_path / "booking.db")
    database.initialize()
    service = BookingService(database, hold_minutes=5)
    movie = service.create_movie("Interstellar", 169)
    service.show_id = service.create_show(movie, datetime.now(UTC) + timedelta(days=1), "Screen 1", 8)
    return service


def test_hold_removes_seats_from_inventory(service):
    hold = service.hold_seats(service.show_id, "customer-1", [2, 3])
    assert hold["seats"] == [2, 3]
    assert service.availability(service.show_id) == [1, 4, 5, 6, 7, 8]


def test_double_booking_is_rejected(service):
    service.hold_seats(service.show_id, "customer-1", [2])
    with pytest.raises(SeatUnavailable):
        service.hold_seats(service.show_id, "customer-2", [2])


def test_confirmation_is_idempotent(service):
    hold = service.hold_seats(service.show_id, "customer-1", [1])
    first = service.confirm(hold["hold_id"], "payment-attempt-123")
    retry = service.confirm(hold["hold_id"], "payment-attempt-123")
    assert first["id"] == retry["id"]


def test_rejects_invalid_seat(service):
    with pytest.raises(ValueError):
        service.hold_seats(service.show_id, "customer-1", [99])
