export type Show = {
  id: number;
  starts_at: string;
  auditorium: string;
  city: string;
  theatre: string;
  format: string;
  from_price: number;
};

export type Movie = {
  id: number;
  title: string;
  duration_minutes: number;
  synopsis: string;
  genre: string;
  language: string;
  certificate: string;
  rating: number;
  poster_gradient: string;
  shows: Show[];
};

export type Seat = {
  number: number;
  label: string;
  row: string;
  column: number;
  tier: "Classic" | "Prime" | "Recliner";
  price: number;
  status: "available" | "held" | "booked";
};

export type SeatMap = {
  show: {
    id: number;
    movie_title: string;
    duration_minutes: number;
    certificate: string;
    starts_at: string;
    auditorium: string;
    city: string;
    theatre: string;
    format: string;
  };
  layout: { columns: number; seat_count: number };
  seats: Seat[];
};

export type Hold = {
  hold_id: string;
  show_id: number;
  seats: Seat[];
  amount: number;
  expires_at: string;
  status: string;
};

export type Booking = {
  id: string;
  status: string;
  amount: number;
  payment_reference: string;
  movie_title: string;
  starts_at: string;
  theatre: string;
  auditorium: string;
  format: string;
  seats: Seat[];
};
