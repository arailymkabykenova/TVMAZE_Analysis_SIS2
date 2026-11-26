import sys

import pandas as pd

from src import analysis, api_client, cleaner, consumer, loader, producer, validator


def section(number, title):
    print("=" * 60)
    print(f"{number}. {title}")


def main():
    # --collect pulls fresh data from TVMaze and changes the snapshot
    collect = "--collect" in sys.argv

    if collect:
        section(1, "Collect from API")
        collected = len(api_client.run())
    else:
        section(1, "Collect from API (skipped, using saved snapshot)")
        collected = len(pd.read_csv(api_client.RAW_CSV_PATH))

    section(2, "Kafka producer")
    published = producer.run()

    section(3, "Kafka consumer")
    consumed = consumer.run(max_messages=published)

    section(4, "Validation (Pandera)")
    valid = len(validator.run())

    section(5, "Cleaning and transformation")
    cleaned = len(cleaner.run())

    section(6, "Load to SQLite")
    stored = loader.run()

    section(7, "Analysis")
    analysis.run()

    print("=" * 60)
    print("PIPELINE SUMMARY")
    print(f"Collected (snapshot):    {collected}")
    print(f"Published to Kafka:      {published}")
    print(f"Consumed from Kafka:     {consumed}")
    print(f"Valid after validation:  {valid}")
    print(f"After cleaning:          {cleaned}  (dropped: {valid - cleaned})")
    print(f"Stored in SQLite:        {stored}")


if __name__ == "__main__":
    main()