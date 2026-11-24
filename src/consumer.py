
import json
import os
import sys
from pathlib import Path

import pandas as pd
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "tvmaze-shows")
GROUP_ID = "tvmaze-pipeline"          
IDLE_TIMEOUT_MS = 10_000              

PROJECT_DIR = Path(__file__).resolve().parent.parent
CONSUMED_CSV_PATH = PROJECT_DIR / "data" / "consumed.csv"


def build_consumer():
    return KafkaConsumer(
        TOPIC,
        bootstrap_servers=BOOTSTRAP_SERVERS,
        group_id=GROUP_ID,
        auto_offset_reset="earliest",      
        enable_auto_commit=False,           
        consumer_timeout_ms=IDLE_TIMEOUT_MS,
    )


def run(max_messages=None):
    try:
        consumer = build_consumer()
    except NoBrokersAvailable:
        print(f"ERROR: Kafka broker is not reachable at {BOOTSTRAP_SERVERS}. "
              f"Start it with: docker start kafka  (or see README)")
        sys.exit(1)

    records, bad_messages = [], 0
    print(f"Listening to topic '{TOPIC}' (stops after {IDLE_TIMEOUT_MS // 1000}s without messages)...")

    for message in consumer:                         
        try:
            record = json.loads(message.value.decode("utf-8"))  
            records.append(record)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            bad_messages += 1
            print(f"  skipped bad message at partition {message.partition}, "
                  f"offset {message.offset}: {error}")

        if max_messages and len(records) >= max_messages:
            break

    if records:
        pd.DataFrame(records).to_csv(CONSUMED_CSV_PATH, index=False, encoding="utf-8")
        consumer.commit()                          
        print(f"Saved -> {CONSUMED_CSV_PATH.relative_to(PROJECT_DIR)}")
    consumer.close()

    print(f"Consumer finished: consumed={len(records)}, bad_messages={bad_messages}")
    return len(records)


if __name__ == "__main__":
    run()
