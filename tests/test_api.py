from fastapi.testclient import TestClient

from bookmymovie.api import create_app


def test_complete_customer_journey(tmp_path):
    app = create_app(tmp_path / "api.db")
    client = TestClient(app)

    catalogue = client.get("/v1/catalogue?city=Bengaluru")
    assert catalogue.status_code == 200
    movie = catalogue.json()["movies"][0]
    show_id = movie["shows"][0]["id"]

    seats = client.get(f"/v1/shows/{show_id}/seats")
    assert seats.status_code == 200
    assert len(seats.json()["seats"]) == 48

    hold = client.post(
        "/v1/holds",
        json={"show_id": show_id, "customer_id": "viewer@example.com", "seat_numbers": [1, 2]},
    )
    assert hold.status_code == 201
    assert hold.json()["amount"] > 0

    booking = client.post(
        "/v1/bookings",
        headers={"Idempotency-Key": "checkout-attempt-1001"},
        json={"hold_id": hold.json()["hold_id"], "payment_method": "upi"},
    )
    assert booking.status_code == 201
    assert booking.json()["status"] == "confirmed"
    assert [seat["label"] for seat in booking.json()["seats"]] == ["A1", "A2"]

    lookup = client.get(f"/v1/bookings/{booking.json()['id']}")
    assert lookup.status_code == 200
    assert lookup.json()["payment_reference"].startswith("PAY-")


def test_conflicting_hold_returns_409(tmp_path):
    client = TestClient(create_app(tmp_path / "conflict.db"))
    show_id = client.get("/v1/catalogue").json()["movies"][0]["shows"][0]["id"]
    payload = {"show_id": show_id, "customer_id": "one@example.com", "seat_numbers": [7]}

    assert client.post("/v1/holds", json=payload).status_code == 201
    payload["customer_id"] = "two@example.com"
    response = client.post("/v1/holds", json=payload)

    assert response.status_code == 409
    assert "another customer" in response.json()["detail"]


def test_health_and_missing_resources(tmp_path):
    client = TestClient(create_app(tmp_path / "health.db", seed_demo=False))

    assert client.get("/health").json()["version"] == "2.0.0"
    assert client.get("/v1/shows/999/seats").status_code == 404
    assert client.get("/v1/bookings/missing").status_code == 404
