"""Everything that turns features into predictions, with the model loaded once.

The API layer (main.py) is thin on purpose: it does HTTP, this module does the work.
Nothing here imports FastAPI, so it can be used from a notebook or a script too.

Three jobs:
  predict_frame()        a dataframe of features -> the same rows plus predictions
  process_input_file()   one CSV in data/input -> a predictions CSV in data/output
  run_week()             top up the feature file, predict this week, draw the chart
"""

from datetime import date, datetime

import joblib
import pandas as pd

import paths
from trading_calendar import is_weekend, week_window
from load_prediction_data import ensure_data
from week_chart import save_week_chart

# Features the model was trained on, in training order. Read off the fitted estimator
# where possible so the API and the web form can never drift from the model.
FALLBACK_FEATURES = [
    'Prev_Day_DowJones_Returns',
    'Prev_Day_Nasdaq_Returns',
    'Prev_Day_HangSeng_Returns',
    'Prev_Day_Nikkei225_Returns',
    'Prev_Day_DAX_Returns',
    'Prev_Day_VIX_Returns',
    'Prev_Day_Nifty50_HL_Ratio',
    'Prev_Day_DowJones_HL_Ratio',
]

# Above this probability the model calls an up open. Matches the /predict endpoint.
THRESHOLD = 0.5

_model = None
_load_error = None


def _load():
    global _model, _load_error
    if _model is None and _load_error is None:
        try:
            _model = joblib.load(paths.MODEL_PATH)
        except Exception as exc:          # noqa: BLE001 - surfaced through /health
            _load_error = str(exc)
    return _model


def model():
    """The fitted estimator, or None if it could not be loaded."""
    return _load()


def load_error():
    """Why the model failed to load, or None."""
    _load()
    return _load_error


def feature_names():
    """Feature columns in the order the model expects them."""
    est = _load()
    names = getattr(est, 'feature_names_in_', None)
    return list(names) if names is not None else list(FALLBACK_FEATURES)


def predict_frame(df):
    """Add predictions to a frame of feature rows.

    Returns a new frame: any non-feature columns the caller passed in (Date, say) are
    kept, followed by Predicted Probability, Predicted Class and Nifty 50 Open
    Direction. Raises ValueError naming the columns that are missing.
    """
    est = _load()
    if est is None:
        raise RuntimeError(f"Model not loaded: {_load_error}")

    features = feature_names()
    missing = [c for c in features if c not in df.columns]
    if missing:
        raise ValueError("Missing feature column(s): " + ", ".join(missing))

    X = df[features].astype(float)
    if X.isna().any().any():
        bad = sorted(X.columns[X.isna().any()])
        raise ValueError("Non-numeric or blank values in: " + ", ".join(bad))

    proba = est.predict_proba(X)[:, 1]
    out = df.copy()
    out['Predicted Probability'] = proba
    out['Predicted Class'] = (proba >= THRESHOLD).astype(int)
    out['Nifty 50 Open Direction'] = ['Up' if p >= THRESHOLD else 'Down' for p in proba]
    return out


def predict_one(features_dict):
    """Single row in, the three result fields out. What POST /predict returns."""
    row = predict_frame(pd.DataFrame([features_dict])).iloc[0]
    return {
        'predicted_probability': float(row['Predicted Probability']),
        'predicted_class': int(row['Predicted Class']),
        'nifty_50_open_direction': row['Nifty 50 Open Direction'],
    }


# --- the designated input folder -------------------------------------------------

def list_datasets():
    """Every CSV sitting in data/input, with its row count and output status."""
    paths.ensure_dirs()
    items = []
    for path in sorted(paths.INPUT_DIR.glob('*.csv')):
        out = paths.output_for(path)
        try:
            rows = len(pd.read_csv(path))
            error = None
        except Exception as exc:          # noqa: BLE001 - reported to the page
            rows, error = 0, str(exc)
        items.append({
            'name': path.name,
            'rows': rows,
            'modified': datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec='seconds'),
            'processed': out.exists(),
            'output_name': out.name if out.exists() else None,
            'error': error,
        })
    return items


def _resolve_input(name):
    """The input file called `name`, refusing anything outside data/input."""
    candidate = (paths.INPUT_DIR / name).resolve()
    if candidate.parent != paths.INPUT_DIR.resolve():
        raise ValueError(f"'{name}' is not a file in the input folder.")
    if not candidate.is_file():
        raise FileNotFoundError(f"No such input dataset: {name}")
    return candidate


def process_input_file(name):
    """Predict every row of one input dataset and write the results to data/output."""
    paths.ensure_dirs()
    src = _resolve_input(name)
    df = pd.read_csv(src)
    result = predict_frame(df)

    out_path = paths.output_for(src)
    result.to_csv(out_path, index=False)
    return {
        'input_name': src.name,
        'output_name': out_path.name,
        'rows': len(result),
        'up': int((result['Predicted Class'] == 1).sum()),
        'down': int((result['Predicted Class'] == 0).sum()),
        'records': _records(result),
    }


def _is_stale(src):
    """True when `src` has no predictions yet, or they predate the input file."""
    out = paths.output_for(src)
    return not out.exists() or out.stat().st_mtime < src.stat().st_mtime


def auto_process_inputs():
    """Predict any dataset in data/input that has no up-to-date output.

    Called on server startup, so dropping a CSV into the folder and restarting is
    enough - nobody has to press anything.
    """
    paths.ensure_dirs()
    done, failed = [], []
    for src in sorted(paths.INPUT_DIR.glob('*.csv')):
        if not _is_stale(src):
            continue
        try:
            summary = process_input_file(src.name)
            done.append(f"{summary['input_name']} -> {summary['output_name']} "
                        f"({summary['rows']} rows)")
        except Exception as exc:          # noqa: BLE001 - one bad file must not stop boot
            failed.append(f"{src.name}: {exc}")
    return done, failed


# --- the weekly forecast ---------------------------------------------------------

def _records(df):
    """Frame -> JSON-safe list of dicts, with dates as plain strings."""
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime('%Y-%m-%d')
    return out.where(pd.notna(out), None).to_dict(orient='records')


def run_week(today=None):
    """Top up the feature file, predict this week's sessions, and draw the chart.

    Weekday run - Monday to Friday of this week, days up to today marked as already
    traded and the rest as forecast. Weekend run - all of next week as forecast, with
    Friday's row carried forward since no new market data has arrived.
    """
    paths.ensure_dirs()
    today = today or date.today()
    weekend_run = is_weekend(today)
    window = week_window(today)
    if not window:
        raise RuntimeError("Every session this week is a market holiday - nothing to chart.")

    target_days = [d for d, _ in window]
    forecast_flags = dict(window)
    target_dates = pd.to_datetime([d.isoformat() for d in target_days])

    # NOTE: ensure_data fills gaps with RANDOM PLACEHOLDER features unless the file
    # already holds real data - see load_prediction_data.py.
    df_full = ensure_data(paths.FEATURE_CSV, through=target_days[-1],
                          fill='ffill' if weekend_run else 'random')
    if df_full.empty:
        raise RuntimeError(f"No usable data in {paths.FEATURE_CSV}.")

    df_full['Date'] = pd.to_datetime(df_full['Date'])
    df_week = (df_full[df_full['Date'].dt.normalize().isin(target_dates)]
               .sort_values('Date')
               .copy())
    if df_week.empty:
        raise RuntimeError(f"No feature rows for {target_days[0]} to {target_days[-1]}.")

    predicted = predict_frame(df_week)
    df_predictions = pd.DataFrame({
        'Date': predicted['Date'].dt.strftime('%Y-%m-%d'),
        'Day': predicted['Date'].dt.strftime('%a'),
        'Horizon': ['Forecast' if forecast_flags[d.date()] else 'Already traded'
                    for d in predicted['Date']],
        'Predicted Probability': predicted['Predicted Probability'].values,
        'Predicted Class': predicted['Predicted Class'].values,
        'Nifty 50 Open Direction': predicted['Nifty 50 Open Direction'].values,
    })

    df_predictions.to_csv(paths.WEEK_CSV, index=False)
    save_week_chart(df_predictions, target_days, today, weekend_run, paths.WEEK_CHART)

    return {
        'today': today.isoformat(),
        'today_label': f"{today:%a %d %b %Y}",
        'weekend_run': weekend_run,
        'week_label': f"{target_days[0]:%d %b} - {target_days[-1]:%d %b %Y}",
        'n_traded': int((df_predictions['Horizon'] == 'Already traded').sum()),
        'n_forecast': int((df_predictions['Horizon'] == 'Forecast').sum()),
        'csv_name': paths.WEEK_CSV.name,
        'records': _records(df_predictions),
    }


def latest_feature_row():
    """The most recent feature row on file - used to prefill the web form."""
    try:
        df = pd.read_csv(paths.FEATURE_CSV)
    except Exception:                      # noqa: BLE001 - prefill is a nicety
        return None
    if df.empty:
        return None
    row = df.sort_values('Date').iloc[-1] if 'Date' in df.columns else df.iloc[-1]
    return {name: float(row[name]) for name in feature_names() if name in row}
