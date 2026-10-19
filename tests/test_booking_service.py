from datetime import UTC, datetime, timedelta

import pytest

from bookmymovie import BookingService, SeatUnavailable
from bookmymovie.database import Database


@pytest.fixture
def service(tmp_path):
    database = Database(tmp_path / "booking.db")
    database.initialize()
    service = BookingService(database, hold_minutes=5)
    movie = service.create_movie(
        "Interstellar", 169, genre="Science Fiction", rating=8.9, poster_gradient="electric"
    )
    service.show_id = service.create_show(
        movie,
        datetime.now(UTC) + timedelta(days=1),
        "Screen 1",
        24,
        base_price=200,
        seat_columns=8,
    )
    return service


def test_catalogue_groups_showtimes_under_movies(service):
    catalogue = service.catalogue(city="Bengaluru")

    assert catalogue["cities"] == ["Bengaluru"]
    assert catalogue["movies"][0]["title"] == "Interstellar"
    assert catalogue["movies"][0]["shows"][0]["id"] == service.show_id


def test_seat_map_exposes_labels_tiers_and_prices(service):
    seat_map = service.seat_map(service.show_id)

    assert seat_map["layout"] == {"columns": 8, "seat_count": 24}
    assert seat_map["seats"][0] | {"status": "available"} == {
        "number": 1,
        "label": "A1",
        "row": "A",
        "column": 1,
        "tier": "Classic",
        "price": 200,
        "status": "available",
    }
    assert seat_map["seats"][-1]["tier"] == "Recliner"
    assert seat_map["seats"][-1]["price"] == 320


def test_hold_removes_seats_from_inventory(service):
    hold = service.hold_seats(service.show_id, "customer@example.com", [2, 3])

    assert [seat["number"] for seat in hold["seats"]] == [2, 3]
    assert 2 not in service.availability(service.show_id)
    assert service.seat_map(service.show_id)["seats"][1]["status"] == "held"


def test_double_booking_is_rejected(service):
    service.hold_seats(service.show_id, "first@example.com", [2])

    with pytest.raises(SeatUnavailable):
        service.hold_seats(service.show_id, "second@example.com", [2])


def test_confirmation_is_idempotent_and_marks_seat_booked(service):
    hold = service.hold_seats(service.show_id, "customer@example.com", [1])
    first = service.confirm(hold["hold_id"], "payment-attempt-123", "card")
    retry = service.confirm(hold["hold_id"], "payment-attempt-123", "card")

    assert first == retry
    assert first["payment_method"] == "card"
    assert first["amount"] == 200
    assert service.seat_map(service.show_id)["seats"][0]["status"] == "booked"


def test_idempotency_key_cannot_confirm_another_hold(service):
    first = service.hold_seats(service.show_id, "first@example.com", [1])
    second = service.hold_seats(service.show_id, "second@example.com", [2])
    service.confirm(first["hold_id"], "shared-payment-key")

    with pytest.raises(SeatUnavailable):
        service.confirm(second["hold_id"], "shared-payment-key")


def test_releasing_hold_returns_inventory(service):
    hold = service.hold_seats(service.show_id, "customer@example.com", [4])

    service.release_hold(hold["hold_id"])

    assert 4 in service.availability(service.show_id)
    assert service.get_hold(hold["hold_id"])["status"] == "expired"


def test_rejects_invalid_seat(service):
    with pytest.raises(ValueError):
        service.hold_seats(service.show_id, "customer@example.com", [99])
