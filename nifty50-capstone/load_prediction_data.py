"""Keep future_prediction_data.csv topped up so the daily prediction job can run.

    python load_prediction_data.py                 # fill through this week's sessions
    python load_prediction_data.py --through 2026-10-15
    python load_prediction_data.py --rebuild       # discard and regenerate

*** THE FEATURE VALUES PRODUCED HERE ARE RANDOM PLACEHOLDERS, NOT MARKET DATA. ***

Any prediction made from them is meaningless as a forecast - they exist only so the
pipeline can be exercised end to end. Replace generate_row() with a real market-data
fetch before treating a single output as a genuine signal.

Rows are generated only for dates missing from the CSV, so the job is idempotent:
running it twice in a day adds nothing the second time. Each date's values are seeded
from the date itself, so a given date always gets the same numbers no matter when it
is generated or whether the file is rebuilt from scratch.
"""

import argparse
from datetime import date, datetime

import numpy as np
import pandas as pd

import paths
from trading_calendar import is_weekend, week_window

# The designated input folder, resolved from this file's location - see paths.py.
CSV_PATH = paths.FEATURE_CSV

# Feature name -> (low, high) for the placeholder uniform draw. Order defines
# column order in the CSV and must match the model's expected features.
FEATURE_RANGES = {
    'Prev_Day_DowJones_Returns':   (-1.0, 1.0),
    'Prev_Day_Nasdaq_Returns':     (-1.0, 1.0),
    'Prev_Day_HangSeng_Returns':   (-1.0, 1.0),
    'Prev_Day_Nikkei225_Returns':  (-1.0, 1.0),
    'Prev_Day_DAX_Returns':        (-1.0, 1.0),
    'Prev_Day_VIX_Returns':        (-0.1, 0.1),    # VIX moves in smaller steps
    'Prev_Day_Nifty50_HL_Ratio':   (0.98, 1.02),   # a ratio, so it hugs 1
    'Prev_Day_DowJones_HL_Ratio':  (0.98, 1.02),
}

COLUMNS = ['Date'] + list(FEATURE_RANGES)

# How far back to seed history when the CSV does not exist yet (business days).
DEFAULT_LOOKBACK = 30


def generate_row(day):
    """Placeholder feature row for one session, deterministic in `day`."""
    rng = np.random.default_rng(day.toordinal())
    row = {'Date': pd.Timestamp(day)}
    row.update({name: rng.uniform(low, high) for name, (low, high) in FEATURE_RANGES.items()})
    return row


def load_existing(csv_path):
    """Existing CSV as a dataframe, or an empty one if it is absent/unreadable."""
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        return pd.DataFrame(columns=COLUMNS)
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    df['Date'] = pd.to_datetime(df['Date']).dt.normalize()
    return df


def ensure_data(csv_path=CSV_PATH, through=None, lookback=DEFAULT_LOOKBACK,
                rebuild=False, fill='random'):
    """Make sure `csv_path` holds a row for every business day up to `through`.

    fill='random' draws fresh placeholder values for each missing session.
    fill='ffill'  carries the most recent existing row forward onto every missing
                  session - what you want over a weekend, when no new market data
                  has arrived since Friday's close. Falls back to 'random' if the
                  file is empty, since there is then nothing to carry forward.

    Returns the full dataframe. Only missing dates are generated; existing rows are
    never overwritten, so any real data already in the file survives.
    """
    paths.ensure_dirs()
    through = pd.Timestamp(through or date.today()).normalize()
    existing = pd.DataFrame(columns=COLUMNS) if rebuild else load_existing(csv_path)

    if existing.empty:
        start = through - pd.tseries.offsets.BDay(lookback)
    else:
        start = existing['Date'].max() + pd.Timedelta(days=1)

    required = pd.bdate_range(start=start, end=through)
    missing = sorted(set(required) - set(existing['Date']))

    if not missing:
        latest = existing['Date'].max()
        print(f"Data already covers through {through:%Y-%m-%d} (file ends {latest:%Y-%m-%d}) - nothing to add.")
        return existing.sort_values('Date').reset_index(drop=True)

    span = f"{missing[0]:%Y-%m-%d} -> {missing[-1]:%Y-%m-%d}"
    if fill == 'ffill' and not existing.empty:
        source = existing.sort_values('Date').iloc[-1]
        print(f"Carrying {source['Date']:%Y-%m-%d} (last session on file) forward to "
              f"{len(missing)} session(s): {span}")
        carried = {name: source[name] for name in FEATURE_RANGES}
        new_rows = pd.DataFrame([dict(Date=pd.Timestamp(d), **carried) for d in missing])
    else:
        print(f"Generating {len(missing)} placeholder row(s): {span}")
        new_rows = pd.DataFrame([generate_row(d) for d in missing])

    # Concatenating onto an all-NA empty frame warns and muddles dtypes, so skip it
    combined = new_rows if existing.empty else pd.concat([existing, new_rows], ignore_index=True)
    combined = (combined
                .drop_duplicates(subset='Date', keep='first')
                .sort_values('Date')
                .reset_index(drop=True))[COLUMNS]

    combined.to_csv(csv_path, index=False)
    print(f"Wrote {len(combined)} total rows to {csv_path}")
    return combined


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--csv', default=CSV_PATH, help='CSV to top up')
    parser.add_argument('--through', help='Fill through this date (YYYY-MM-DD). '
                                          'Default: the end of this week\'s prediction window.')
    parser.add_argument('--lookback', type=int, default=DEFAULT_LOOKBACK,
                        help='Business days of history to seed when creating the file')
    parser.add_argument('--rebuild', action='store_true',
                        help='Discard existing rows and regenerate from scratch')
    parser.add_argument('--fill', choices=['random', 'ffill', 'auto'], default='auto',
                        help="How to fill missing sessions. 'auto' (default) carries the "
                             "last row forward on weekends, draws placeholders otherwise.")
    args = parser.parse_args()

    if args.through:
        through = datetime.strptime(args.through, '%Y-%m-%d').date()
    else:
        # Default to covering the sessions the prediction job will ask for.
        through = week_window()[-1][0]

    fill = ('ffill' if is_weekend() else 'random') if args.fill == 'auto' else args.fill
    ensure_data(args.csv, through=through, lookback=args.lookback,
                rebuild=args.rebuild, fill=fill)


if __name__ == '__main__':
    main()
