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
  -> src/cleaner.py -> data/clean.csv
  -> src/loader.py -> data/output.db
  -> src/analysis.py -> figures/*.png
```

## Software requirements
- Python 3.10 or newer
- Docker Desktop (runs the Kafka broker)
- Internet access for the TVMaze API

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
python3 src/cleaner.py        # 5. cleaning and transformation            (Fariza)
python3 src/loader.py         # 6. load to SQLite twice + SQL verification  (Fariza)
python3 src/analysis.py       # 7. statistics and figures                 (Fariza)
```
Or run everything at once: `python3 main.py` 

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

## Database generation and verification
TO DO (Fariza): `loader.py`, table schema, idempotency test, SQL queries.

## Analysis results and figures
TO DO (Fariza): `analysis.py`, list of figures in `figures/`.

## Project structure
```
main.py              runs all stages in order                      
src/api_client.py    API collection with retries and error handling 
src/producer.py      Kafka producer, JSON serialization             
src/consumer.py      Kafka consumer, JSON deserialization, stop rule  
src/validator.py     Pandera schema (8 rules) and test records        
src/cleaner.py       cleaning and transformation                 
src/loader.py        SQLite storage and idempotency                
src/analysis.py      EDA and visualizations                           
docs/data_dictionary.md
report/project_report.pdf
```