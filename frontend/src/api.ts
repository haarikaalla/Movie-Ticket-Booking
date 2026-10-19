import type { Booking, Hold, SeatMap } from "./types";

const parse = async <T>(request: Promise<Response>): Promise<T> => {
  const response = await request;
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Something went wrong" }));
    throw new Error(body.detail ?? "Something went wrong");
  }
  return response.json() as Promise<T>;
};

export const getCatalogue = (city: string, query = "") =>
  parse<{ cities: string[]; movies: import("./types").Movie[] }>(
    fetch(`/v1/catalogue?city=${encodeURIComponent(city)}&query=${encodeURIComponent(query)}`),
  );

export const getSeatMap = (showId: number) =>
  parse<SeatMap>(fetch(`/v1/shows/${showId}/seats`));

export const createHold = (showId: number, customerId: string, seatNumbers: number[]) =>
  parse<Hold>(
    fetch("/v1/holds", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ show_id: showId, customer_id: customerId, seat_numbers: seatNumbers }),
    }),
  );

export const releaseHold = (holdId: string) =>
  parse<{ status: string }>(fetch(`/v1/holds/${holdId}`, { method: "DELETE" }));

export const confirmBooking = (holdId: string, paymentMethod: string) =>
  parse<Booking>(
    fetch("/v1/bookings", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify({ hold_id: holdId, payment_method: paymentMethod }),
    }),
  );
