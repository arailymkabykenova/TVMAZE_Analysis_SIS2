# Data Dictionary

## About the data

- **Source:** TVMaze API, endpoint `https://api.tvmaze.com/shows`, pages 0 and 1.
- **One row = one TV show.**
- **Snapshot:** the data was collected once and saved in `data/`. The pipeline uses this saved snapshot, so results do not change between runs.
- **Rows:** 485 collected, 484 after cleaning. One show (ID 410, "Rival Survival") was dropped because it has no premiere date.

## Files

| File | What it is |
|---|---|
| `data/clean.csv` | Cleaned data, 484 rows, 24 columns. Input for the database. |
| `data/output.db`, table `shows` | Same 24 columns and the same rows as `clean.csv`. `show_id` is the primary key. |
| `data/genre_stats.csv` | Number of shows, average rating and median runtime for each genre. |
| `data/genre_decade_pivot.csv` | Average rating for the 8 most common genres, by decade. |

## Columns

Columns are in the same order as in `clean.csv`.

| Column | Type | Meaning | Source | Empty values and how we handle them |
|---|---|---|---|---|
| show_id | integer | Unique show ID | TVMaze | None. Primary key in the database. |
| name | text | Show title | TVMaze | None |
| type | text | Kind of show, for example Scripted, Reality, Animation | TVMaze | None |
| language | text | Main language of the show | TVMaze | None |
| genres | text | Genres separated by `\|`, for example `Drama\|Thriller` | TVMaze | 18 shows have no genre. They are set to `Unknown`. |
| status | text | `Ended`, `Running` or `To Be Determined` | TVMaze | None |
| runtime | real | Episode length in minutes | TVMaze | 33 were empty. All 33 were filled with the show's average runtime from TVMaze. |
| premiered | date (text) | First air date, format `YYYY-MM-DD` | TVMaze | None. The show without this date was dropped. |
| ended | date (text) | Last air date, format `YYYY-MM-DD` | TVMaze | 43 are empty. These shows are still running or have status `To Be Determined`. We keep them empty on purpose. |
| rating | real | Average user rating from 0 to 10 | TVMaze | 20 are empty because the show has no rating. We do not fill them, because a made-up rating would change the averages. |
| weight | real | TVMaze popularity score from 0 to 100 | TVMaze | None |
| network | text | TV channel the show airs on | TVMaze | 30 are empty. These shows are on streaming only. |
| web_channel | text | Streaming service the show is on | TVMaze | 447 are empty. These shows are on TV only. |
| country | text | Country of the network or streaming service | TVMaze | 20 were empty. They are set to `Unknown`. |
| schedule_time | text | Air time, for example `22:00` | TVMaze | 45 are empty. This column is not used in the analysis. |
| schedule_days | text | Air days separated by `\|` | TVMaze | 19 are empty. This column is not used in the analysis. |
| imdb_id | text | IMDb ID of the show | TVMaze | 2 are empty. This column is not used in the analysis. |
| summary | text | Short plot description. HTML tags are removed and extra spaces are cleaned. | TVMaze | None |
| has_rating | integer | `1` if the show has a rating, `0` if not | Created | None |
| platform | text | `TV` (only network), `Streaming` (only web channel) or `Both` | Created from `network` and `web_channel` | None. Each show has at least one platform. |
| premiere_year | integer | Year of `premiered` | Created | None |
| decade | integer | Start of the premiere decade, for example `2010` for 2010–2019 | Created | None |
| log_weight | real | `log(1 + weight)`, rounded to 3 decimals. It makes the weight scale less skewed. | Created with NumPy | None |
| rating_zscore | real | How far the rating is from the average, in standard deviations, rounded to 2 decimals. Mean and standard deviation are computed over shows with a rating. | Created with NumPy | 20 are empty, because these shows have no rating. |

The column `average_runtime` is not in this file. It was used to fill `runtime` and then removed.

## Output tables

### genre_stats.csv

| Column | Meaning |
|---|---|
| genre | Genre name |
| shows | Number of shows with this genre |
| avg_rating | Average rating of these shows |
| median_runtime | Median episode length of these shows |

One show can have several genres, so the sum of `shows` is bigger than 484.

### genre_decade_pivot.csv

- Rows: the 8 genres with the most shows (`Unknown` is not included).
- Columns: decades from 1960 to 2010.
- Values: average rating of shows in that genre and decade.
- Empty cell: no show of this genre in this decade.

## Notes

- The rating is a user average from TVMaze. It is not a professional critic score.
- Some decades have very few shows. There are 3 shows from the 1960s, 2 from the 1970s and 7 from the 1980s. Averages for these decades are not reliable.
- Dates are stored as text in `YYYY-MM-DD` format, both in `clean.csv` and in the database.