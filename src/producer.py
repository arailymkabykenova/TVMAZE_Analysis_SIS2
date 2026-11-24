import json
import os
import sys
from pathlib import Path

import pandas as pd
from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import KafkaError, NoBrokersAvailable, TopicAlreadyExistsError

BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "tvmaze-shows")
NUM_PARTITIONS = 3
REPLICATION_FACTOR = 1           

PROJECT_DIR = Path(__file__).resolve().parent.parent
RAW_CSV_PATH = PROJECT_DIR / "data" / "raw_data.csv"


def create_topic_if_missing():
    """Create the topic once. If it already exists, do nothing."""
    admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP_SERVERS, client_id="tvmaze-admin")
    try:
        admin.create_topics([NewTopic(name=TOPIC,
                                      num_partitions=NUM_PARTITIONS,
                                      replication_factor=REPLICATION_FACTOR)])
        print(f"Topic '{TOPIC}' created ({NUM_PARTITIONS} partitions)")
    except TopicAlreadyExistsError:
        print(f"Topic '{TOPIC}' already exists")
    finally:
        admin.close()


def load_records():
    """Read raw records and turn them into a list of dicts. NaN -> None (JSON null)."""
    df = pd.read_csv(RAW_CSV_PATH)
    df = df.astype(object).where(df.notna(), None)   
    return df.to_dict(orient="records")


def build_producer():
    return KafkaProducer(
        bootstrap_servers=BOOTSTRAP_SERVERS,
        key_serializer=lambda key: str(key).encode("utf-8"),                     
        value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"), 
        acks="all",        
        retries=3,       
    )


def run():
    records = load_records()
    print(f"Loaded {len(records)} records from {RAW_CSV_PATH.relative_to(PROJECT_DIR)}")

    try:
        create_topic_if_missing()
        producer = build_producer()
    except NoBrokersAvailable:
        print(f"ERROR: Kafka broker is not reachable at {BOOTSTRAP_SERVERS}. "
              f"Start it with: docker start kafka  (or see README)")
        sys.exit(1)

    published, failed = 0, 0
    for record in records:
        try:
            future = producer.send(TOPIC, key=record["show_id"], value=record)
            metadata = future.get(timeout=10)          # wait for the broker's acknowledgement (ACK)
            published += 1
            if published <= 3:                         # show where the first messages landed
                print(f"  sent show_id={record['show_id']} -> partition {metadata.partition}, "
                      f"offset {metadata.offset}")
        except KafkaError as error:
            failed += 1
            print(f"  FAILED show_id={record.get('show_id')}: {error}")

    producer.flush()
    producer.close()

    print(f"Producer finished: published={published}, failed={failed}")
    return published


if __name__ == "__main__":
    run()
