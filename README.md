# SIS2 - TVMaze Streaming & Validation Pipeline (Kafka + Pandera + SQLite)

## Project overview
The pipeline collects TV show data from the public TVMaze API, streams it through a real Apache Kafka
broker in JSON format, validates it with Pandera, cleans it with pandas/NumPy, stores it in SQLite and
performs exploratory data analysis.

**Research question:** what makes a TV show successful? Ratings by genre, platform (TV network vs
streaming), premiere decade and popularity.

```
TVMaze API -> src/api_client.py -> data/raw_data.json (original) + data/raw_data.csv
  -> src/producer.py -> Kafka topic "tvmaze-shows" -> src/consumer.py -> data/consumed.csv
  -> src/validator.py (Pandera) -> data/validated.csv (+ data/invalid_records.csv)
  -> src/cleaner.py -> data/clean.csv (+ data/genre_stats.csv, data/genre_decade_pivot.csv)
  -> src/loader.py -> data/output.db
  -> src/analysis.py -> figures/*.png
```

## Software requirements
- Python 3.10 or newer (tested with Python 3.10.11)
- Docker Desktop (runs the Kafka broker)
- Internet access for the TVMaze API (only for `--collect`, see below)

Versions installed by `requirements.txt` during testing (macOS, Apple Silicon):
pandas 2.3.3, numpy 2.2.6, pandera 0.36.0, kafka-python 2.3.3, matplotlib 3.10.9, seaborn 0.13.2, requests 2.34.2.
The Kafka image used is `apache/kafka:latest`.

## Installation
```bash
git clone https://github.com/arailymkabykenova/TVMAZE_Analysis_SIS2.git
cd TVMAZE_Analysis_SIS2
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
`kafka-python` version 2.3.3

## API configuration
- Endpoint: `GET https://api.tvmaze.com/shows?page=N`
- Parameter: `page` (0, 1, ...). Page N contains shows with IDs from N*250 to N*250+249.
- No API key or credentials are needed. The script collects pages 0 and 1 (`PAGES_TO_COLLECT` in
  `src/api_client.py`).

## Kafka broker setup and startup
```bash
docker run -d --name kafka -p 9092:9092 apache/kafka:latest   # first time: downloads and starts Kafka (KRaft mode)
docker start kafka                                              # next times
docker ps                                                       # the kafka container must be "Up"
```
The broker is available at `localhost:9092`.

## Kafka topic configuration
The topic `tvmaze-shows` (3 partitions, replication factor 1) is created automatically by
`src/producer.py`. Optional environment variables:

| Variable | Default |
|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` |
| `KAFKA_TOPIC` | `tvmaze-shows` |

## Execution order
Run the stages in this order (Kafka must be running):
```bash
python3 src/api_client.py     # 1. collect shows from the API
python3 src/producer.py       # 2. publish every record to Kafka as JSON
python3 src/consumer.py       # 3. consume the records (stops after 10 s without new messages)
python3 src/validator.py      # 4. Pandera validation + 4 deliberately invalid test records
python3 src/cleaner.py        # 5. cleaning and transformation
python3 src/loader.py         # 6. load to SQLite twice + SQL verification
python3 src/analysis.py       # 7. statistics and figures
```
Or run everything at once from the project folder: `python3 main.py`
(uses the saved data snapshot, see "Running the whole pipeline" below).

## Expected outputs (stages 1-4)
| Command | Expected result |
|---|---|
| `api_client.py` | `Collected 485 records`; files `data/raw_data.json`, `data/raw_data.csv` |
| `producer.py` | topic created or already exists; `published=485, failed=0` |
| `consumer.py` | `consumed=485, bad_messages=0`; file `data/consumed.csv` |
| `validator.py` | `Valid records: 485`, `Invalid records: 4 (test records detected: 4 of 4, real invalid: 0)`; files `data/validated.csv`, `data/invalid_records.csv` |

The consumer group `tvmaze-pipeline` remembers its offset: running `consumer.py` again without running
`producer.py` reads 0 new messages, which is expected. To read the topic from the beginning again,
delete the topic:
```bash
docker exec kafka /opt/kafka/bin/kafka-topics.sh --delete --topic tvmaze-shows --bootstrap-server localhost:9092
```

## Verifying successful execution (stages 1-4)
```bash
# topics in the broker (expected: tvmaze-shows and __consumer_offsets)
docker exec kafka /opt/kafka/bin/kafka-topics.sh --list --bootstrap-server localhost:9092
# first 3 JSON messages stored in the topic
docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh --topic tvmaze-shows --from-beginning --max-messages 3 --bootstrap-server localhost:9092
```
`data/invalid_records.csv` lists every rejected record with the broken validation rule.

## Cleaning (stage 5)
`src/cleaner.py` reads `data/validated.csv` and writes `data/clean.csv`. Main steps:
- drops the show without a premiere date (show_id 410);
- removes duplicates by `show_id` and by name + premiere date (none were found);
- converts dates and numbers to the right types;
- removes HTML tags from `summary`;
- fills empty `runtime` from `average_runtime`, then from the median runtime of the same show type;
- keeps empty `rating` on purpose and adds `has_rating`;
- creates `platform` (TV, Streaming, Both), `premiere_year`, `decade`, `log_weight`, `rating_zscore`;
- writes two summary files: `data/genre_stats.csv` (GroupBy by genre) and `data/genre_decade_pivot.csv` (pivot by genre and decade).

Expected output: `Rows: 485` at the start, `Rows left: 484` after dropping show 410, `Rows saved: 484 -> clean.csv` at the end.

Column meanings are in `docs/data_dictionary.md`.

## Database generation and verification (stage 6)
`src/loader.py` reads `data/clean.csv` and writes table `shows` to the SQLite file `data/output.db`.
The file is created when the script runs. It is not stored in git (see `.gitignore`).

**Table schema:** 24 columns, same as `clean.csv`. `show_id` is the PRIMARY KEY. `name` and `status` are required.
`runtime` must be greater than 0. `rating` must be between 0 and 10 or empty.

**How loading works:**
- `CREATE TABLE IF NOT EXISTS` creates the table only the first time.
- UPSERT (`INSERT ... ON CONFLICT(show_id) DO UPDATE`) inserts a new show, or updates it if `show_id` already exists.
  This is why running the loader again does not create duplicate rows.
- Empty values are stored as `NULL`. Dates are stored as text in `YYYY-MM-DD` format.
- The script loads the same data twice and checks that the number of rows, the number of distinct IDs and the sum of ratings do not change.

**Expected output:**
```
Rows to load: 484
Rows in database: 484          (after first load)
Rows in database: 484          (after second load)
OK: no duplicates, nothing changed
Processed: 484, stored: 484, match
```

**Verification:**
```bash
# first columns of the table, show_id must have pk = 1
python3 -c "import sqlite3; c = sqlite3.connect('data/output.db'); print(c.execute('PRAGMA table_info(shows)').fetchall()[:3])"

# row count
python3 -c "import sqlite3; c = sqlite3.connect('data/output.db'); print(c.execute('SELECT COUNT(*) FROM shows').fetchone())"
```
The loader also prints SQL checks: an empty list of duplicate `show_id` values, average rating by platform
(TV 447 shows, average 7.52; Streaming 30, 7.48; Both 7, 7.45) and the top 5 rated shows.

## Analysis results and figures (stage 7)
`src/analysis.py` reads table `shows` from `data/output.db`, so run `loader.py` first.
It prints descriptive statistics and group tables, then saves three figures to `figures/`:

| File | What it shows |
|---|---|
| `figures/1_rating_by_genre.png` | Average rating by genre. Only genres with at least 10 shows; `Unknown` is excluded. |
| `figures/2_rating_by_platform.png` | Rating distribution (boxplot) by platform (TV, Streaming, Both), split by show status. |
| `figures/3_trend_by_decade.png` | Number of shows (bars) and average rating (line) by premiere decade. |

Main numbers from the run: 484 rows and 24 columns; rating filled for 464 shows; status Ended 441,
Running 38, To Be Determined 5. Average rating by genre goes from 7.30 (Comedy) to 7.85 (Mystery).
Shows per decade: 1960s 3, 1970s 2, 1980s 7, 1990s 29, 2000s 119, 2010s 324.

## Running the whole pipeline
```bash
python3 main.py
```
By default `main.py` does **not** call the TVMaze API. It uses the saved snapshot in `data/raw_data.csv`.
This keeps the numbers the same on every run.

To download fresh data from the API:
```bash
python3 main.py --collect
```
This changes `data/raw_data.*`, so the numbers in the report may change too. Use it only if you want to update the snapshot.

**Clean run** (recommended before a demo): delete the Kafka topic first, so old messages are not read again:
```bash
docker exec kafka /opt/kafka/bin/kafka-topics.sh --delete --topic tvmaze-shows --bootstrap-server localhost:9092
python3 main.py
```

**Expected summary at the end of `main.py`:**
```
Collected (snapshot):    485
Published to Kafka:      485
Consumed from Kafka:     485
Valid after validation:  485
After cleaning:          484  (dropped: 1)
Stored in SQLite:        484
```

## Project structure
```
main.py              runs all stages in order
src/api_client.py    API collection with retries and error handling
src/producer.py      Kafka producer, JSON serialization
src/consumer.py      Kafka consumer, JSON deserialization, stop rule
src/validator.py     Pandera schema (8 rules) and test records
src/cleaner.py       cleaning and transformation (groupby, pivot)
src/loader.py        SQLite storage, primary key, UPSERT, idempotency check
src/analysis.py      EDA and visualizations
data/                snapshot and results (output.db is created locally, not committed)
figures/             three PNG figures from analysis.py
docs/data_dictionary.md   description of every column
report/project_report.pdf
```
