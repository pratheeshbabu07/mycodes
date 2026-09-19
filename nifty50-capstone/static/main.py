"""Nifty 50 open-direction prediction API, and the web page that consumes it.

Run it:
    python -m uvicorn main:app --host 127.0.0.1 --port 8000
then open http://127.0.0.1:8000 - or just double-click run_app.bat.

Endpoints
    GET  /                    the web page
    GET  /health              model status, feature names, dataset counts
    POST /predict             one row  -> probability, class, direction
    POST /predict/batch       many rows -> a list of the same
    GET  /datasets            what is sitting in the designated input folder
    POST /datasets/upload     add a CSV to that folder
    POST /predict/file        predict one input dataset -> data/output
    POST /predict/week        this week's forecast + chart
    GET  /outputs/{name}      download a results CSV
    GET  /chart/week.png      the weekly chart image

Datasets live in data/input and results in data/output (see paths.py). Anything in
data/input without up-to-date predictions is processed automatically at startup.
"""

import matplotlib
matplotlib.use('Agg')          # no display on a server; must precede pyplot imports

import shutil
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import paths
import model_service
from trading_calendar import is_weekend, week_window

paths.ensure_dirs()

# Load the finalized model (joblib), resolved from this file's folder rather than the
# working directory, so the server starts from anywhere.
if model_service.model() is not None:
    print("Model loaded successfully!")
else:
    print(f"Error loading model: {model_service.load_error()}")


# Define the input data structure using Pydantic
# This should match the features your model was trained on
class PredictionInput(BaseModel):
    Prev_Day_DowJones_Returns: float
    Prev_Day_Nasdaq_Returns: float
    Prev_Day_HangSeng_Returns: float
    Prev_Day_Nikkei225_Returns: float
    Prev_Day_DAX_Returns: float
    Prev_Day_VIX_Returns: float
    Prev_Day_Nifty50_HL_Ratio: float
    Prev_Day_DowJones_HL_Ratio: float


class BatchInput(BaseModel):
    rows: list


class FileRequest(BaseModel):
    name: str


# Initialize FastAPI app
app = FastAPI(title="Nifty 50 Open Direction Prediction API")

app.mount("/static", StaticFiles(directory=str(paths.STATIC_DIR)), name="static")


@app.on_event("startup")
def process_waiting_datasets():
    """Predict anything dropped into the input folder since the last run."""
    done, failed = model_service.auto_process_inputs()
    for line in done:
        print(f"[auto] {line}")
    for line in failed:
        print(f"[auto] SKIPPED {line}")
    if not done and not failed:
        print("[auto] Input folder is already up to date.")


# Define a prediction endpoint
@app.post("/predict")
async def predict(data: PredictionInput):
    if model_service.model() is None:
        return {"error": "Model not loaded. Cannot make predictions."}

    return model_service.predict_one(data.dict())


@app.post("/predict/batch")
async def predict_batch(payload: BatchInput):
    """Several feature rows at once. Same three fields back, one per row."""
    if model_service.model() is None:
        raise HTTPException(503, "Model not loaded. Cannot make predictions.")
    if not payload.rows:
        raise HTTPException(400, "No rows supplied.")
    try:
        return {"count": len(payload.rows),
                "results": [model_service.predict_one(row) for row in payload.rows]}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/health")
async def health():
    """Everything the page needs to describe the system on load."""
    today = date.today()
    window = week_window(today)
    return {
        "model_loaded": model_service.model() is not None,
        "model_error": model_service.load_error(),
        "model_type": type(model_service.model()).__name__ if model_service.model() else None,
        "features": model_service.feature_names(),
        "threshold": model_service.THRESHOLD,
        "today": today.isoformat(),
        "today_label": f"{today:%a %d %b %Y}",
        "market_open": not is_weekend(today),
        "week_label": (f"{window[0][0]:%d %b} - {window[-1][0]:%d %b %Y}" if window else None),
        "dataset_count": len(model_service.list_datasets()),
        "defaults": model_service.latest_feature_row(),
    }


@app.get("/datasets")
async def datasets():
    """What is in the designated input folder, and whether it has been processed."""
    return {"input_dir": str(paths.INPUT_DIR),
            "output_dir": str(paths.OUTPUT_DIR),
            "datasets": model_service.list_datasets()}


@app.post("/datasets/upload")
async def upload_dataset(file: UploadFile = File(...)):
    """Save an uploaded CSV into the input folder and predict it straight away."""
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(400, "Only .csv files are accepted.")

    # Keep the name to a bare filename so an upload cannot write outside the folder.
    safe_name = Path(file.filename).name
    target = paths.INPUT_DIR / safe_name
    with open(target, 'wb') as fh:
        shutil.copyfileobj(file.file, fh)

    try:
        return {"saved": safe_name, **model_service.process_input_file(safe_name)}
    except ValueError as exc:
        # The file is kept so the user can see what they uploaded and fix it.
        raise HTTPException(400, f"Saved {safe_name}, but it could not be predicted: {exc}")


@app.post("/predict/file")
async def predict_file(payload: FileRequest):
    """Predict every row of one dataset from the input folder."""
    try:
        return model_service.process_input_file(payload.name)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/predict/week")
async def predict_week():
    """This week's session-by-session forecast, plus a freshly drawn chart."""
    try:
        return model_service.run_week()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/outputs/{name}")
async def download_output(name: str):
    """Download a results CSV from the output folder."""
    target = (paths.OUTPUT_DIR / name).resolve()
    if target.parent != paths.OUTPUT_DIR.resolve() or not target.is_file():
        raise HTTPException(404, f"No such output file: {name}")
    return FileResponse(target, media_type='text/csv', filename=target.name)


@app.get("/chart/week.png")
async def week_chart():
    """The weekly chart image. Run POST /predict/week first to create it."""
    if not paths.WEEK_CHART.exists():
        raise HTTPException(404, "No chart yet - run this week's prediction first.")
    return FileResponse(paths.WEEK_CHART, media_type='image/png')


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """The web page. The JSON health check moved to /health."""
    return FileResponse(paths.STATIC_DIR / 'index.html')
