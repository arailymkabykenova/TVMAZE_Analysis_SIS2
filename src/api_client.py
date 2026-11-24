import json
import time
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://api.tvmaze.com/shows"
PAGES_TO_COLLECT = 2          # 2 pages = 500 shows 
TIMEOUT_SECONDS = 10
MAX_RETRIES = 3

PROJECT_DIR = Path(__file__).resolve().parent.parent  
DATA_DIR = PROJECT_DIR / "data"
RAW_JSON_PATH = DATA_DIR / "raw_data.json"
RAW_CSV_PATH = DATA_DIR / "raw_data.csv"


def fetch_page(page):
    """Request one page of shows. Returns a list of dicts, or [] if the page does not exist."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(BASE_URL, params={"page": page}, timeout=TIMEOUT_SECONDS)

            if response.status_code == 404:          
                print(f"Page {page}: no more data (404)")
                return []
            if response.status_code == 429:          # too many requests -> wait and retry
                raise requests.HTTPError("429 Too Many Requests")

            response.raise_for_status()              
            shows = response.json()
            print(f"Page {page}: received {len(shows)} shows")
            return shows

        except (requests.RequestException, ValueError) as error:   # network error, bad status, bad JSON
            print(f"Page {page}, attempt {attempt}/{MAX_RETRIES} failed: {error}")
            if attempt == MAX_RETRIES:
                raise                                 
            time.sleep(2 ** attempt)                  


def flatten_show(show):
    """Turn one nested show dict into a flat dict with the columns we need."""
    network = show.get("network") or {}              
    web_channel = show.get("webChannel") or {}
    country = network.get("country") or web_channel.get("country") or {}
    rating = show.get("rating") or {}
    schedule = show.get("schedule") or {}

    return {
        "show_id": show.get("id"),
        "name": show.get("name"),
        "type": show.get("type"),
        "language": show.get("language"),
        "genres": "|".join(show.get("genres") or []),   # list -> "Drama|Thriller" cause SQLite has no list type
        "status": show.get("status"),
        "runtime": show.get("runtime"),
        "average_runtime": show.get("averageRuntime"),
        "premiered": show.get("premiered"),
        "ended": show.get("ended"),
        "rating": rating.get("average"),
        "weight": show.get("weight"),
        "network": network.get("name"),
        "web_channel": web_channel.get("name"),
        "country": country.get("name"),
        "schedule_time": schedule.get("time"),
        "schedule_days": "|".join(schedule.get("days") or []),
        "imdb_id": (show.get("externals") or {}).get("imdb"),
        "summary": show.get("summary"),                 #contains HTML tags-clean later
    }


def collect_shows(pages=PAGES_TO_COLLECT):
    """Collect several pages and return the raw list of show dicts."""
    all_shows = []
    for page in range(pages):
        shows = fetch_page(page)
        if not shows:
            break
        all_shows.extend(shows)
        time.sleep(0.5)                              
    return all_shows


def run():
    DATA_DIR.mkdir(exist_ok=True)

    raw_shows = collect_shows()
    if not raw_shows:
        raise RuntimeError("No data collected from the API")

    #original response exactly as received
    with open(RAW_JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(raw_shows, file, ensure_ascii=False, indent=2)

    #flat table for the next pipeline steps
    df = pd.DataFrame([flatten_show(show) for show in raw_shows])
    df.to_csv(RAW_CSV_PATH, index=False, encoding="utf-8")

    print(f"Collected {len(df)} records -> {RAW_CSV_PATH.relative_to(PROJECT_DIR)}")
    return df


if __name__ == "__main__":
    run()
