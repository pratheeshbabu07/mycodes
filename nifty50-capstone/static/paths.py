"""Every file location the Nifty 50 predictor uses, in one place.

Paths are resolved from this file's own location, not the working directory, so the
server and the batch script behave the same however they are launched - from an IDE,
from another folder, or by double-clicking run_app.bat.

    data/input/   the designated folder for test/input datasets. Drop a CSV here and
                  the API picks it up.
    data/output/  predictions written back out, one CSV per input file, plus the
                  weekly chart.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Versioned artefact name - v1 is the Elastic Net logistic regression saved by the
# Phase 6 notebook. Bump the suffix when a retrained model replaces it.
MODEL_PATH = BASE_DIR / 'nifty50_open_direction_logreg_v1.joblib'
STATIC_DIR = BASE_DIR / 'static'

DATA_DIR = BASE_DIR / 'data'
RAW_DIR = DATA_DIR / 'raw'              # Phase 1 output, the notebooks read this
PROCESSED_DIR = DATA_DIR / 'processed'  # Phase 2/3 output, what the model trains on
INPUT_DIR = DATA_DIR / 'input'
OUTPUT_DIR = DATA_DIR / 'output'

# The training table, used by evaluate_model.py.
TRAINING_CSV = PROCESSED_DIR / 'processed_ohlc_data.csv'

# Where evaluate_model.py writes its metrics and plots.
RESULTS_DIR = BASE_DIR / 'results'

# The rolling feature file the weekly job tops up and predicts from.
FEATURE_CSV = INPUT_DIR / 'future_prediction_data.csv'

# Weekly job artefacts.
WEEK_CSV = OUTPUT_DIR / 'nifty50_predictions.csv'
WEEK_CHART = OUTPUT_DIR / 'nifty50_predictions.png'

# Suffix appended to an input file's stem when its predictions are written out.
OUTPUT_SUFFIX = '_predictions.csv'


def ensure_dirs():
    """Create the data folders if they are not there yet. Safe to call repeatedly."""
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def output_for(input_path):
    """Where predictions for `input_path` get written."""
    return OUTPUT_DIR / (Path(input_path).stem + OUTPUT_SUFFIX)
