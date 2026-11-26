import sqlite3
from contextlib import closing
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "data" / "output.db"
FIG_DIR = PROJECT_DIR / "figures"
MIN_SHOWS = 10 


def step(number, title):
    print(f"\n=== STEP {number}: {title} ===")


def load_data():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        return pd.read_sql_query("SELECT * FROM shows", conn)


def describe(df):
    step(1, "Describe data")
    print(f"Shape: {df.shape[0]} rows, {df.shape[1]} columns")

    print("\nColumn types:")
    print(df.dtypes.to_string())

    print("\nNumeric statistics:")
    print(df[["rating", "runtime", "weight", "premiere_year"]].describe().round(2).to_string())

    for column in ["status", "platform", "type", "language"]:
        print(f"\n{column}:")
        print(df[column].value_counts().to_string())


def group_tables(df):
    step(2, "Group by status and platform")
    by_status = df.groupby("status").agg(shows=("show_id", "count"), avg_rating=("rating", "mean")).round(2)
    by_platform = df.groupby("platform").agg(shows=("show_id", "count"), avg_rating=("rating", "mean")).round(2)

    print(by_status.to_string())
    print()
    print(by_platform.to_string())


def plot_genres(df):
    step(3, "Plot 1: average rating by genre")
    # one row per show and genre
    genres = df.assign(genre=df["genres"].str.split("|")).explode("genre")
    genres = genres[genres["genre"] != "Unknown"]

    table = (genres.groupby("genre")
             .agg(shows=("show_id", "count"), avg_rating=("rating", "mean"))
             .round(2))
    table = table[table["shows"] >= MIN_SHOWS].sort_values("avg_rating", ascending=False)
    print(table.to_string())

    fig, ax = plt.subplots(figsize=(10, 7))
    sns.barplot(x=table["avg_rating"], y=table.index, color="steelblue", ax=ax)
    ax.set_title(f"Average rating by genre (genres with at least {MIN_SHOWS} shows)")
    ax.set_xlabel("Average rating (0-10)")
    ax.set_ylabel("Genre")
    ax.set_xlim(left=table["avg_rating"].min() - 0.5)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "1_rating_by_genre.png", dpi=150)
    plt.close(fig)


def plot_platform_boxplot(df):
    step(4, "Plot 2: rating by platform and status")
    rated = df.dropna(subset=["rating"])  # no rating -> nothing to draw

    fig, ax = plt.subplots(figsize=(8, 6))
    sns.boxplot(data=rated, x="platform", y="rating", hue="status", ax=ax)
    ax.set_title("Rating by platform and show status")
    ax.set_xlabel("Platform")
    ax.set_ylabel("Rating (0-10)")
    ax.legend(title="Status")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "2_rating_by_platform.png", dpi=150)
    plt.close(fig)


def plot_decades(df):
    step(5, "Plot 3: number of shows and rating by decade")
    by_decade = (df.dropna(subset=["decade"])
                 .groupby("decade")
                 .agg(shows=("show_id", "count"), avg_rating=("rating", "mean"))
                 .round(2))
    print(by_decade.to_string())

    x = by_decade.index.astype(int).astype(str)
    fig, ax1 = plt.subplots(figsize=(10, 6))
    ax1.bar(x, by_decade["shows"], color="lightgray", label="Number of shows")
    ax1.set_xlabel("Premiere decade")
    ax1.set_ylabel("Number of shows")

    # second axis for the rating line
    ax2 = ax1.twinx()
    ax2.plot(x, by_decade["avg_rating"], marker="o", color="crimson", label="Average rating")
    ax2.set_ylabel("Average rating")

    ax1.set_title("Number of shows and average rating by premiere decade")
    bars, bar_labels = ax1.get_legend_handles_labels()
    line, line_labels = ax2.get_legend_handles_labels()
    ax1.legend(bars + line, bar_labels + line_labels, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "3_trend_by_decade.png", dpi=150)
    plt.close(fig)


def run():
    FIG_DIR.mkdir(exist_ok=True)
    df = load_data()
    describe(df)
    group_tables(df)
    plot_genres(df)
    plot_platform_boxplot(df)
    plot_decades(df)
    print(f"\nSaved 3 figures to {FIG_DIR.name}/")


if __name__ == "__main__":
    run()