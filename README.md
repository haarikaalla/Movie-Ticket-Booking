# BookMyMovie — concurrency-safe booking service

The original learning notebook has been rebuilt as a modern inventory service.
The new core uses transactional seat holds, expiration, idempotent confirmation,
strict validation and a versioned FastAPI surface. This addresses the central
failure mode in ticketing systems: two customers attempting to reserve the same
seat at the same time.

## Run

```bash
python -m pip install -e '.[dev]'
uvicorn bookmymovie.api:app --reload
pytest
```

Open `/docs` for the generated OpenAPI console. The database layer uses SQLite
for a zero-infrastructure demo and `BEGIN IMMEDIATE` transactions for serialized
inventory changes. Production evolution should replace it with PostgreSQL while
preserving the service contract, then add payment webhooks, pricing, refunds and
an outbox for reliable events.

## Legacy assignment
# Problem Statement- Python Program to creating one short application called as BookMy Movie.
1) If we run the code 1st thing which must appear is the name of your application as "BookMyMovie".
2) Create few Functions to perform particular characteristics of the application.
3) t_movie():This method is used to select the movie.You can choose any four recent movies from real world like Brahmastra,etc..
4) theater():This method is used to select the screen .As we visit to some theatre we can see multiple screen available you have to give user choice for selecting the screen number
5) timing(a):This method is used to select timing for movies.After selecting the movie user want to watch we have to give user choice to select timing slots,you can pick any timing slot according to your experiance of movie timings.
6) movie(theatre):This method is used to select movies accordingly to the theatre.
