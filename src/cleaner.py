from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
VALIDATED_CSV_PATH = DATA_DIR / "validated.csv"
CLEAN_CSV_PATH = DATA_DIR / "clean.csv"
GENRE_STATS_PATH = DATA_DIR / "genre_stats.csv"
PIVOT_PATH = DATA_DIR / "genre_decade_pivot.csv"

NUMERIC_COLUMNS = ["rating", "runtime", "average_runtime", "weight"]
TEXT_COLUMNS = ["name", "type", "language", "status", "network", "web_channel", "country"]


def step(number, title):
    print(f"\n=== STEP {number}: {title} ===")


def report_missing(df, title):
    missing = df.isna().sum()
    missing = missing[missing > 0]
    print(f"{title}:")
    print(missing.to_string() if len(missing) else "  no missing values")


def load_validated():
    step(1, "Load validated records")
    df = pd.read_csv(VALIDATED_CSV_PATH)
    print(f"Rows: {len(df)}")
    return df


def drop_no_premiere(df):
    step(2, "Drop records without premiere date")
    # without a premiere date the show cannot be placed in a decade
    missing = df[df["premiered"].isna()]
    print(f"Dropped show_id: {missing['show_id'].tolist()}")
    df = df.dropna(subset=["premiered"])
    print(f"Rows left: {len(df)}")
    return df


def remove_duplicates(df):
    step(3, "Remove duplicates")
    by_id = df.duplicated(subset=["show_id"]).sum()
    by_content = df.duplicated(subset=["name", "premiered"]).sum()
    df = df.drop_duplicates(subset=["show_id"]).drop_duplicates(subset=["name", "premiered"])
    print(f"Duplicates by show_id: {by_id}, by name + premiered: {by_content}")
    print(f"Rows left: {len(df)}")
    return df


def convert_types(df):
    step(4, "Convert types")
    # errors="coerce": bad values become NaN / NaT instead of an error
    df["premiered"] = pd.to_datetime(df["premiered"], errors="coerce")
    df["ended"] = pd.to_datetime(df["ended"], errors="coerce")
    for column in NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df["show_id"] = df["show_id"].astype(int)
    print(df[["premiered", "ended"]].dtypes.to_string())
    print(f"Empty ended (still running or unknown): {df['ended'].isna().sum()}")
    return df


def clean_text(df):
    step(5, "Clean text")
    for column in TEXT_COLUMNS:
        df[column] = df[column].str.strip()

    print(f"Summaries with HTML before: {df['summary'].str.contains('<', regex=False).sum()}")
    # replace tags with a space so words from neighbouring tags do not stick together
    df["summary"] = (df["summary"]
                     .str.replace(r"<[^>]+>", " ", regex=True)
                     .str.replace(r"\s+", " ", regex=True)
                     .str.strip())
    print(f"Summaries with HTML after: {df['summary'].str.contains('<', regex=False).sum()}")

    # genres stay as "Drama|Thriller" here; the split happens later for groupby
    df["genres"] = df["genres"].fillna("").str.strip().replace("", "Unknown")
    return df


def fill_runtime(df):
    step(6, "Fill missing runtime")
    before = df["runtime"].isna().sum()
    # first choice: the show's own average runtime from TVMaze
    df["runtime"] = df["runtime"].fillna(df["average_runtime"])
    after_average = df["runtime"].isna().sum()
    # second choice: typical runtime of the same show type
    df["runtime"] = df["runtime"].fillna(df.groupby("type")["runtime"].transform("median"))
    print(f"Missing runtime: before={before}, after average_runtime={after_average}, "
          f"after median={df['runtime'].isna().sum()}")
    return df.drop(columns=["average_runtime"])


def add_rating_flag(df):
    step(7, "Keep rating empty, add has_rating flag")
    # a made-up rating would distort averages, so we only add a flag
    df["has_rating"] = df["rating"].notna().astype(int)
    print(f"Shows with rating: {df['has_rating'].sum()} of {len(df)}")
    return df


def add_platform(df):
    step(8, "Platform: TV / Streaming / Both")
    has_tv = df["network"].notna()
    has_streaming = df["web_channel"].notna()
    df["platform"] = np.select(
        [has_tv & has_streaming, has_tv, has_streaming],
        ["Both", "TV", "Streaming"],
        default="Unknown",
    )
    df["platform"] = df["platform"].astype("category")
    print(df["platform"].value_counts().to_string())
    return df


def add_time_features(df):
    step(9, "Premiere year and decade")
    df["premiere_year"] = df["premiered"].dt.year.astype(int)
    df["decade"] = (np.floor(df["premiere_year"] / 10) * 10).astype(int)
    print(df["decade"].value_counts().sort_index().to_string())
    return df


def add_numeric_features(df):
    step(10, "NumPy features: log weight and rating z-score")
    # log1p makes the popularity scale less skewed
    df["log_weight"] = np.round(np.log1p(df["weight"]), 3)
    rating = df["rating"].to_numpy(dtype=float)
    # nan-safe functions ignore shows without rating
    df["rating_zscore"] = np.round((rating - np.nanmean(rating)) / np.nanstd(rating), 2)
    print(f"Mean rating: {np.nanmean(rating):.2f}, std: {np.nanstd(rating):.2f}")
    return df


def filter_recent_hits(df):
    step(11, "Filter: running shows from 2010, rating >= 8")
    # demonstration of a filter with several conditions; result is printed, not saved
    hits = df[(df["rating"] >= 8) & (df["premiere_year"] >= 2010) & (df["status"] == "Running")]
    print(f"Matching shows: {len(hits)}")
    print(hits[["name", "rating", "premiere_year"]].to_string(index=False))


def genre_stats(df):
    step(12, "GroupBy genre")
    # one row per show and genre, so a show with two genres counts in both
    by_genre = df.assign(genre=df["genres"].str.split("|")).explode("genre")
    stats = (by_genre.groupby("genre")
             .agg(shows=("show_id", "count"),
                  avg_rating=("rating", "mean"),
                  median_runtime=("runtime", "median"))
             .round(2)
             .sort_values("shows", ascending=False))
    stats.to_csv(GENRE_STATS_PATH, encoding="utf-8")
    print(stats.head(8).to_string())
    return by_genre, stats


def genre_decade_pivot(by_genre, stats):
    step(13, "Pivot: average rating by genre and decade")
    top_genres = stats.drop(index="Unknown", errors="ignore").head(8).index
    pivot = (by_genre[by_genre["genre"].isin(top_genres)]
             .pivot_table(index="genre", columns="decade", values="rating", aggfunc="mean")
             .round(2))
    pivot.to_csv(PIVOT_PATH, encoding="utf-8")
    print(pivot.to_string())


def save_clean(df):
    step(14, "Save clean data")
    df.to_csv(CLEAN_CSV_PATH, index=False, encoding="utf-8")
    print(f"Rows saved: {len(df)} -> {CLEAN_CSV_PATH.name}")


def run():
    df = load_validated()
    df = drop_no_premiere(df)
    df = remove_duplicates(df)
    df = convert_types(df)
    df = clean_text(df)
    report_missing(df, "Missing values before filling runtime")
    df = fill_runtime(df)
    df = add_rating_flag(df)
    df = add_platform(df)
    df = add_time_features(df)
    df = add_numeric_features(df)
    report_missing(df, "Missing values after cleaning (rating, ended, network, web_channel stay empty on purpose)")
    filter_recent_hits(df)
    by_genre, stats = genre_stats(df)
    genre_decade_pivot(by_genre, stats)
    save_clean(df)
    return df


if __name__ == "__main__":
    run()