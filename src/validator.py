from pathlib import Path

import pandas as pd

try:                                
    import pandera.pandas as pa
except ImportError:               
    import pandera as pa

PROJECT_DIR = Path(__file__).resolve().parent.parent
CONSUMED_CSV_PATH = PROJECT_DIR / "data" / "consumed.csv"
VALIDATED_CSV_PATH = PROJECT_DIR / "data" / "validated.csv"
INVALID_CSV_PATH = PROJECT_DIR / "data" / "invalid_records.csv"

ALLOWED_STATUSES = ["Ended", "Running", "To Be Determined", "In Development"]
TODAY = pd.Timestamp.today().normalize()


schema = pa.DataFrameSchema(
    columns={
        # Rule 1: unique identifier, required, integer
        "show_id": pa.Column(int, nullable=False, unique=True, coerce=True),
        # Rule 2: required text field, not empty
        "name": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        # Rule 3: allowed categorical values
        "status": pa.Column(str, pa.Check.isin(ALLOWED_STATUSES), nullable=False),
        # Rule 4: numerical range (TVMaze rating is 0-10), missing allowed
        "rating": pa.Column(float, pa.Check.in_range(0, 10), nullable=True, coerce=True),
        # Rule 5: numerical boundaries for episode length in minutes, missing allowed
        "runtime": pa.Column(float, [pa.Check.gt(0), pa.Check.le(300)], nullable=True, coerce=True),
        # Rule 6: popularity weight is 0-100
        "weight": pa.Column(float, pa.Check.in_range(0, 100), nullable=True, coerce=True),
        # Rule 7: date/time validation - a valid date and not in the future
        "premiered": pa.Column("datetime64[ns]", pa.Check.le(TODAY), nullable=True, coerce=True),
        "ended": pa.Column("datetime64[ns]", nullable=True, coerce=True),
    },
    # Rule 8: custom cross-column condition-show cannot end before it premiered
    checks=pa.Check(
        lambda df: df["ended"].isna() | df["premiered"].isna() | (df["ended"] >= df["premiered"]),
        element_wise=False,
        error="ended must be on or after premiered",
    ),
    strict=False,     
)


def add_test_records(df):
    """Add deliberately invalid records, clearly marked with is_test=True."""
    test_records = pd.DataFrame([
        {"show_id": -1, "name": "TEST rating out of range", "status": "Ended",
         "rating": 15.0, "runtime": 60, "weight": 50, "premiered": "2015-01-01", "ended": "2016-01-01"},
        {"show_id": -2, "name": "TEST negative runtime", "status": "Running",
         "rating": 7.0, "runtime": -30, "weight": 50, "premiered": "2018-05-01", "ended": None},
        {"show_id": -3, "name": "TEST unknown status", "status": "Cancelled??",
         "rating": 6.0, "runtime": 45, "weight": 50, "premiered": "2020-03-01", "ended": None},
        {"show_id": -4, "name": "TEST ended before premiered", "status": "Ended",
         "rating": 8.0, "runtime": 30, "weight": 50, "premiered": "2021-06-01", "ended": "2019-01-01"},
    ])
    df = df.copy()
    df["is_test"] = False
    test_records["is_test"] = True
    return pd.concat([df, test_records], ignore_index=True)


def validate(df):
    """Return (valid_df, invalid_df, failure_cases)."""
    try:
        checked = schema.validate(df, lazy=True)          # lazy=True -> collect ALL errors, not only the first
        return checked, df.iloc[0:0], pd.DataFrame()
    except pa.errors.SchemaErrors as errors:
        failures = errors.failure_cases
        bad_index = failures["index"].dropna().astype(int).unique()

      
        is_row_check = failures["schema_context"] == "DataFrameSchema"
        reasons = (failures.dropna(subset=["index"])
                   .assign(index=lambda f: f["index"].astype(int),
                           reason=lambda f: f["column"].where(~is_row_check, "row").fillna("row")
                                            + ": " + f["check"].astype(str))
                   .groupby("index")["reason"]
                   .agg(lambda r: "; ".join(sorted(set(r)))))

        invalid = df.loc[bad_index].copy()
        invalid["validation_errors"] = reasons.reindex(invalid.index)
        valid = schema.validate(df.drop(index=bad_index), lazy=True)  
        return valid, invalid, failures


def run():
    received = pd.read_csv(CONSUMED_CSV_PATH)
    print(f"Received from Kafka: {len(received)} records")

    data = add_test_records(received)
    print(f"Added {int(data['is_test'].sum())} deliberately invalid test records")

    valid, invalid, failures = validate(data)

    detected_tests = int(invalid["is_test"].sum()) if len(invalid) else 0
    print(f"Valid records:   {len(valid)}")
    print(f"Invalid records: {len(invalid)}  (test records detected: {detected_tests} of "
          f"{int(data['is_test'].sum())}, real invalid: {len(invalid) - detected_tests})")
    if len(invalid):
        print("\nInvalid records and errors:")
        print(invalid[["show_id", "name", "validation_errors"]].to_string(index=False))

   
    invalid.to_csv(INVALID_CSV_PATH, index=False, encoding="utf-8")
    valid = valid[~valid["is_test"]].drop(columns="is_test")
    valid.to_csv(VALIDATED_CSV_PATH, index=False, encoding="utf-8")
    print(f"\nSaved {len(valid)} valid real records -> {VALIDATED_CSV_PATH.relative_to(PROJECT_DIR)}")
    return valid


if __name__ == "__main__":
    run()
