import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
CLEAN_CSV_PATH = DATA_DIR / "clean.csv"
DB_PATH = DATA_DIR / "output.db"

COLUMNS = [
    "show_id", "name", "type", "language", "genres", "status", "runtime",
    "premiered", "ended", "rating", "weight", "network", "web_channel",
    "country", "schedule_time", "schedule_days", "imdb_id", "summary",
    "has_rating", "platform", "premiere_year", "decade", "log_weight", "rating_zscore",
]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS shows (
    show_id        INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    type           TEXT,
    language       TEXT,
    genres         TEXT,
    status         TEXT NOT NULL,
    runtime        REAL CHECK (runtime > 0),
    premiered      TEXT,
    ended          TEXT,
    rating         REAL CHECK (rating IS NULL OR rating BETWEEN 0 AND 10),
    weight         REAL,
    network        TEXT,
    web_channel    TEXT,
    country        TEXT,
    schedule_time  TEXT,
    schedule_days  TEXT,
    imdb_id        TEXT,
    summary        TEXT,
    has_rating     INTEGER,
    platform       TEXT,
    premiere_year  INTEGER,
    decade         INTEGER,
    log_weight     REAL,
    rating_zscore  REAL
)
"""

# upsert : insert a new show, or update it if show_id already exists
PLACEHOLDERS = ", ".join("?" for _ in COLUMNS)
UPDATE_LIST = ", ".join(f"{column} = excluded.{column}" for column in COLUMNS if column != "show_id")
COLUMN_LIST = ", ".join(COLUMNS)
UPSERT_SQL = (f"INSERT INTO shows ({COLUMN_LIST}) VALUES ({PLACEHOLDERS}) "
              f"ON CONFLICT(show_id) DO UPDATE SET {UPDATE_LIST}")


def step(number, title):
    print(f"\n=== STEP {number}: {title} ===")


def prepare_rows(df):
    df = df[COLUMNS].copy()
    # SQLite has no date type, so dates are stored as text
    for column in ["premiered", "ended"]:
        df[column] = pd.to_datetime(df[column]).dt.strftime("%Y-%m-%d")
    # NaN is not a valid SQL value, NULL is
    df = df.astype(object).where(df.notna(), None)
    return list(df.itertuples(index=False, name=None))


def load(df):
    rows = prepare_rows(df)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        # commits if everything worked, rolls back if an error happened
        with conn:
            conn.execute(CREATE_TABLE_SQL)
            conn.executemany(UPSERT_SQL, rows)


def table_state():
    # numbers that must stay the same after loading the same data again
    with closing(sqlite3.connect(DB_PATH)) as conn:
        return conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT show_id), ROUND(SUM(rating), 2) FROM shows"
        ).fetchone()


def run_query(title, sql):
    print(f"\n{title}:")
    with closing(sqlite3.connect(DB_PATH)) as conn:
        print(pd.read_sql_query(sql, conn).to_string(index=False))


def run():
    step(1, "Read clean data")
    df = pd.read_csv(CLEAN_CSV_PATH)
    print(f"Rows to load: {len(df)}")

    step(2, "First load")
    load(df)
    first = table_state()
    print(f"Rows in database: {first[0]}")

    step(3, "Second load, same data")
    load(df)
    second = table_state()
    print(f"Rows in database: {second[0]}")

    step(4, "Idempotency check")
    print(f"after first load:  rows={first[0]}, distinct ids={first[1]}, sum of ratings={first[2]}")
    print(f"after second load: rows={second[0]}, distinct ids={second[1]}, sum of ratings={second[2]}")
    print("OK: no duplicates, nothing changed" if first == second else "CHANGED: check the data")

    step(5, "Compare processed and stored")
    print(f"Processed: {len(df)}, stored: {second[0]}, "
          f"{'match' if len(df) == second[0] else 'DIFFERENT'}")

    step(6, "SQL verification")
    run_query("Duplicate show_id (must be empty)",
              "SELECT show_id, COUNT(*) AS n FROM shows GROUP BY show_id HAVING COUNT(*) > 1")
    run_query("Average rating by platform",
              "SELECT platform, COUNT(*) AS shows, ROUND(AVG(rating), 2) AS avg_rating "
              "FROM shows GROUP BY platform ORDER BY avg_rating DESC")
    run_query("Top 5 rated shows",
              "SELECT name, rating, premiere_year, platform FROM shows "
              "WHERE rating IS NOT NULL ORDER BY rating DESC, weight DESC LIMIT 5")

    return second[0]


if __name__ == "__main__":
    run()