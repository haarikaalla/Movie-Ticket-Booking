import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { confirmBooking, createHold, getCatalogue, getSeatMap, releaseHold } from "./api";
import { calculateTotal } from "./pricing";
import type { Booking, Hold, Movie, Seat, SeatMap, Show } from "./types";

type View = "discover" | "seats" | "checkout" | "success";

const money = (value: number) => new Intl.NumberFormat("en-IN", {
  style: "currency", currency: "INR", maximumFractionDigits: 0,
}).format(value);

const time = (value: string) => new Intl.DateTimeFormat("en-IN", {
  hour: "numeric", minute: "2-digit",
}).format(new Date(value));

const date = (value: string) => new Intl.DateTimeFormat("en-IN", {
  weekday: "short", day: "numeric", month: "short",
}).format(new Date(value));

function Mark() {
  return <span className="mark" aria-hidden="true"><i /><i /><i /></span>;
}

function App() {
  const [view, setView] = useState<View>("discover");
  const [city, setCity] = useState("Bengaluru");
  const [query, setQuery] = useState("");
  const [cities, setCities] = useState<string[]>([]);
  const [movies, setMovies] = useState<Movie[]>([]);
  const [selectedMovie, setSelectedMovie] = useState<Movie | null>(null);
  const [selectedShow, setSelectedShow] = useState<Show | null>(null);
  const [seatMap, setSeatMap] = useState<SeatMap | null>(null);
  const [selectedSeats, setSelectedSeats] = useState<Seat[]>([]);
  const [email, setEmail] = useState("guest@example.com");
  const [hold, setHold] = useState<Hold | null>(null);
  const [booking, setBooking] = useState<Booking | null>(null);
  const [paymentMethod, setPaymentMethod] = useState("upi");
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    const timer = window.setTimeout(() => {
      getCatalogue(city, query)
        .then((data) => { setCities(data.cities); setMovies(data.movies); setError(""); })
        .catch((reason: Error) => setError(reason.message))
        .finally(() => setLoading(false));
    }, query ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [city, query]);

  useEffect(() => {
    if (!hold) return;
    const update = () => setSecondsLeft(Math.max(0, Math.ceil((new Date(hold.expires_at).getTime() - Date.now()) / 1000)));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [hold]);

  useEffect(() => {
    if (!selectedShow || view !== "seats") return;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.port === "5173" ? `${window.location.hostname}:8000` : window.location.host;
    const socket = new WebSocket(`${protocol}//${host}/v1/shows/${selectedShow.id}/events`);
    socket.onmessage = (message) => {
      const event = JSON.parse(message.data) as { type: string };
      if (event.type === "inventory.changed") {
        getSeatMap(selectedShow.id).then(setSeatMap).catch(() => undefined);
      }
    };
    return () => socket.close();
  }, [selectedShow, view]);

  const total = useMemo(() => calculateTotal(selectedSeats), [selectedSeats]);

  const chooseShow = async (movie: Movie, show: Show) => {
    setLoading(true);
    try {
      const data = await getSeatMap(show.id);
      setSelectedMovie(movie);
      setSelectedShow(show);
      setSeatMap(data);
      setSelectedSeats([]);
      setError("");
      setView("seats");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const toggleSeat = (seat: Seat) => {
    if (seat.status !== "available") return;
    setSelectedSeats((current) => {
      const exists = current.some((item) => item.number === seat.number);
      if (exists) return current.filter((item) => item.number !== seat.number);
      if (current.length >= 10) { setError("You can select up to 10 seats per booking."); return current; }
      setError("");
      return [...current, seat];
    });
  };

  const startCheckout = async () => {
    if (!selectedShow || selectedSeats.length === 0) return;
    if (!email.includes("@")) { setError("Enter a valid email for your ticket."); return; }
    setLoading(true);
    try {
      const reservation = await createHold(selectedShow.id, email, selectedSeats.map((seat) => seat.number));
      setHold(reservation);
      setView("checkout");
      setError("");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (reason) {
      setError((reason as Error).message);
      setSeatMap(await getSeatMap(selectedShow.id));
    } finally {
      setLoading(false);
    }
  };

  const abandonCheckout = async () => {
    if (hold) await releaseHold(hold.hold_id).catch(() => undefined);
    setHold(null);
    setView("seats");
    if (selectedShow) setSeatMap(await getSeatMap(selectedShow.id));
  };

  const pay = async () => {
    if (!hold) return;
    if (secondsLeft <= 0) { setError("Your seat hold expired. Please select the seats again."); return; }
    setLoading(true);
    try {
      const result = await confirmBooking(hold.hold_id, paymentMethod);
      setBooking(result);
      setView("success");
      setError("");
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setView("discover"); setSelectedMovie(null); setSelectedShow(null); setSeatMap(null);
    setSelectedSeats([]); setHold(null); setBooking(null); setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand" onClick={reset} aria-label="BookMyMovie home"><Mark /> <span>BOOKMYMOVIE</span></button>
        <nav><a href="#films">Films</a><a href="#experience">Experience</a><a href="/docs" target="_blank">API</a></nav>
        <div className="header-actions">
          <label className="city-picker"><span>⌖</span><select value={city} onChange={(event) => setCity(event.target.value)}>{(cities.length ? cities : [city]).map((item) => <option key={item}>{item}</option>)}</select></label>
          <div className="avatar">HA</div>
        </div>
      </header>

      {error && <div className="toast" role="alert"><span>{error}</span><button onClick={() => setError("")}>×</button></div>}
      {loading && <div className="progress" />}

      {view === "discover" && (
        <main>
          <section className="hero">
            <div className="hero-copy">
              <p className="eyebrow">CURATED FOR TONIGHT</p>
              <h1>Find your<br /><em>next story.</em></h1>
              <p>Great films. Beautiful screens. Seats that are yours the moment you choose them.</p>
              <div className="search"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by film or genre" /><kbd>⌘ K</kbd></div>
            </div>
            <div className="hero-art" aria-hidden="true">
              <div className="orb orb-one" /><div className="orb orb-two" />
              <div className="ticket-card"><span>TONIGHT</span><strong>THE LAST<br />ALGORITHM</strong><small>21:30 · IMAX</small><div className="ticket-code">|||| ||| |||| ||</div></div>
            </div>
          </section>

          <section className="film-section" id="films">
            <div className="section-heading"><div><p className="eyebrow">NOW SHOWING</p><h2>Stories worth leaving home for</h2></div><span>{movies.length} curated films</span></div>
            <div className="movie-grid">
              {movies.map((movie, index) => (
                <article className="movie-card" key={movie.id} style={{ "--delay": `${index * 70}ms` } as CSSProperties}>
                  <div className={`poster ${movie.poster_gradient}`}>
                    <div className="poster-grain" /><span className="rating">★ {movie.rating.toFixed(1)}</span>
                    <div className="poster-title"><small>A BOOKMYMOVIE PREMIERE</small><strong>{movie.title}</strong></div>
                  </div>
                  <div className="movie-info">
                    <div className="movie-meta"><span>{movie.genre}</span><span>{movie.duration_minutes} min</span><span>{movie.certificate}</span></div>
                    <p>{movie.synopsis}</p>
                    <div className="showtimes">
                      {movie.shows.map((show) => <button key={show.id} onClick={() => chooseShow(movie, show)}><strong>{time(show.starts_at)}</strong><small>{show.format} · {money(show.from_price)}</small></button>)}
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="promise" id="experience">
            <p className="eyebrow">DESIGNED FOR CONFIDENCE</p><h2>The calmest way to book a night out.</h2>
            <div className="promise-grid"><div><b>01</b><h3>Seats held for you</h3><p>Your selection is protected during checkout, even when demand is high.</p></div><div><b>02</b><h3>Safe to retry</h3><p>Payment retries never create duplicate tickets or double charges.</p></div><div><b>03</b><h3>Live availability</h3><p>The seat map updates as other guests make their choices.</p></div></div>
          </section>
        </main>
      )}

      {view === "seats" && seatMap && selectedMovie && selectedShow && (
        <main className="booking-page">
          <button className="back" onClick={() => setView("discover")}>← Back to films</button>
          <div className="booking-title"><div><p className="eyebrow">CHOOSE YOUR VIEW</p><h1>{selectedMovie.title}</h1><p>{selectedShow.theatre} · {selectedShow.auditorium} · {date(selectedShow.starts_at)}, {time(selectedShow.starts_at)}</p></div><span className="live-pill"><i /> LIVE INVENTORY</span></div>
          <div className="seat-layout">
            <section className="auditorium">
              <div className="screen"><span>SCREEN</span></div>
              <div className="seat-grid" style={{ gridTemplateColumns: `repeat(${seatMap.layout.columns}, 1fr)` }}>
                {seatMap.seats.map((seat) => {
                  const selected = selectedSeats.some((item) => item.number === seat.number);
                  return <button key={seat.number} className={`seat ${seat.status} ${selected ? "selected" : ""}`} disabled={seat.status !== "available"} onClick={() => toggleSeat(seat)} title={`${seat.label} · ${seat.tier} · ${money(seat.price)}`}><span>{seat.label}</span></button>;
                })}
              </div>
              <div className="legend"><span><i className="available" />Available</span><span><i className="selected" />Selected</span><span><i className="held" />On hold</span><span><i className="booked" />Booked</span></div>
            </section>
            <aside className="summary-card">
              <p className="eyebrow">YOUR SELECTION</p><h2>{selectedSeats.length ? `${selectedSeats.length} seat${selectedSeats.length > 1 ? "s" : ""}` : "Choose your seats"}</h2>
              <div className="selected-list">{selectedSeats.length ? selectedSeats.map((seat) => <div key={seat.number}><span><b>{seat.label}</b><small>{seat.tier}</small></span><strong>{money(seat.price)}</strong></div>) : <p>Select up to 10 seats from the live map.</p>}</div>
              <label className="email-field"><span>Ticket email</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></label>
              <div className="total"><span>Total</span><strong>{money(total)}</strong></div>
              <button className="primary" disabled={!selectedSeats.length || loading} onClick={startCheckout}>Hold seats & continue <span>→</span></button>
              <small className="secure-note">⌁ Seats are protected for 5 minutes at checkout</small>
            </aside>
          </div>
        </main>
      )}

      {view === "checkout" && hold && selectedMovie && selectedShow && (
        <main className="checkout-page">
          <button className="back" onClick={abandonCheckout}>← Change seats</button>
          <div className="checkout-grid">
            <section className="payment-panel"><p className="eyebrow">SECURE CHECKOUT</p><h1>Complete your booking</h1><p className="muted">Choose a payment experience for this portfolio demo. No real funds are collected.</p>
              <div className="hold-timer"><span>Seats reserved for you</span><strong>{String(Math.floor(secondsLeft / 60)).padStart(2, "0")}:{String(secondsLeft % 60).padStart(2, "0")}</strong></div>
              <div className="payment-options">{[["upi", "UPI", "Instant confirmation"], ["card", "Card", "Credit or debit"], ["wallet", "Wallet", "Fast and convenient"]].map(([id, label, note]) => <button key={id} className={paymentMethod === id ? "active" : ""} onClick={() => setPaymentMethod(id)}><span className="radio" /><span><b>{label}</b><small>{note}</small></span></button>)}</div>
              <button className="primary pay-button" disabled={loading || secondsLeft <= 0} onClick={pay}>Confirm & pay {money(hold.amount)} <span>→</span></button><p className="demo-note">Demo payment · idempotency protected · encrypted transport ready</p>
            </section>
            <aside className="ticket-summary"><div className={`mini-poster ${selectedMovie.poster_gradient}`}><Mark /></div><div><p className="eyebrow">ORDER SUMMARY</p><h2>{selectedMovie.title}</h2><p>{date(selectedShow.starts_at)} · {time(selectedShow.starts_at)}</p><p>{selectedShow.theatre}<br />{selectedShow.auditorium} · {selectedShow.format}</p></div><hr /><div className="ticket-seats"><span>Seats</span><strong>{hold.seats.map((seat) => seat.label).join(", ")}</strong></div><div className="ticket-seats"><span>Tickets</span><strong>{money(hold.amount)}</strong></div><div className="ticket-seats total"><span>Total</span><strong>{money(hold.amount)}</strong></div></aside>
          </div>
        </main>
      )}

      {view === "success" && booking && (
        <main className="success-page"><div className="success-icon">✓</div><p className="eyebrow">YOU'RE ALL SET</p><h1>Your story starts here.</h1><p>A confirmation has been prepared for <strong>{email}</strong>.</p><div className="digital-ticket"><div className="ticket-main"><Mark /><span className="rating">CONFIRMED</span><h2>{booking.movie_title}</h2><p>{date(booking.starts_at)} · {time(booking.starts_at)} · {booking.format}</p><div className="ticket-data"><span><small>CINEMA</small>{booking.theatre}</span><span><small>SCREEN</small>{booking.auditorium}</span><span><small>SEATS</small>{booking.seats.map((seat) => seat.label).join(", ")}</span></div></div><div className="ticket-stub"><span>BOOKING</span><strong>{booking.id.slice(0, 8).toUpperCase()}</strong><div className="qr">▦</div><small>{booking.payment_reference}</small></div></div><button className="primary home-button" onClick={reset}>Explore more films</button></main>
      )}

      <footer><div className="brand"><Mark /><span>BOOKMYMOVIE</span></div><p>Built for reliable, joyful cinema booking.</p><span>© 2026</span></footer>
    </div>
  );
}

export default App;
