import type { Seat } from "./types";

export const calculateTotal = (seats: Pick<Seat, "price">[]) =>
  seats.reduce((total, seat) => total + seat.price, 0);
