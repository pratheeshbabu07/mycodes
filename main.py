"""Skin clinic campaign analysis served as a FastAPI application.

Endpoints
    GET /                        -> redirects to /campaign-analysis
    GET /campaign-analysis       -> HTML tables of campaign response by segment
    GET /campaign-analysis.json  -> the same results as JSON
    GET /health                  -> liveness check for the host
"""

from pathlib import Path

import pandas as pd
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse

DATA_FILE = Path(__file__).parent / "data" / "skin_clinic_campaign.csv"

# Display order for the segments, so the tables always read low -> high.
AGE_ORDER = ["<30", "30-50", ">50"]
PRODUCT_ORDER = ["1-4", "5-8", ">8"]
PURCHASE_ORDER = ["Yes", "No"]
GENDER_ORDER = ["Female", "Male"]

app = FastAPI(
    title="Skin Clinic Campaign Analysis",
    description="Campaign response rates by customer segment.",
    version="1.0.0",
)

# Loaded once at start-up: the file is static, so re-reading it per request
# would only add latency.
df = pd.read_csv(DATA_FILE)


def categorize_products(num_products: int) -> str:
    """Bucket the number of unique products purchased."""
    if num_products <= 4:
        return "1-4"
    if num_products <= 8:
        return "5-8"
    return ">8"


def response_summary(frame: pd.DataFrame, column: str, order: list[str]) -> pd.DataFrame:
    """Customers, responders and response rate for each value of `column`."""
    counts = pd.crosstab(frame[column], frame["Response_to_Campaign"])
    counts = counts.reindex(order).dropna(how="all")

    responded = counts.get("Yes", 0)
    not_responded = counts.get("No", 0)
    customers = responded + not_responded

    summary = pd.DataFrame(
        {
            "Customers": customers,
            "Responded (Yes)": responded,
            "Did Not Respond (No)": not_responded,
            "Response Rate (%)": (responded / customers * 100).round(2),
        }
    )
    summary.index.name = column.replace("_", " ")
    return summary.astype({"Customers": int, "Responded (Yes)": int, "Did Not Respond (No)": int})


def build_segments() -> dict[str, pd.DataFrame]:
    """Every segment table, keyed by the heading it is shown under."""
    current = df.copy()
    current["Product_Usage"] = current["Unique_Products_Purchased"].apply(categorize_products)

    return {
        "Gender vs Campaign Response": response_summary(current, "Gender", GENDER_ORDER),
        "Age Group vs Campaign Response": response_summary(current, "AgeGroup", AGE_ORDER),
        "Purchase in Last Quarter vs Campaign Response": response_summary(
            current, "Purchase_Last_Quarter", PURCHASE_ORDER
        ),
        "Product Usage vs Campaign Response": response_summary(
            current, "Product_Usage", PRODUCT_ORDER
        ),
    }


def overall_stats() -> dict[str, float]:
    responders = int((df["Response_to_Campaign"] == "Yes").sum())
    total = int(len(df))
    return {
        "customers": total,
        "responders": responders,
        "response_rate_pct": round(responders / total * 100, 2),
    }


PAGE_STYLE = """
    :root { color-scheme: light dark; }
    body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
           margin: 0 auto; max-width: 860px; padding: 32px 20px; line-height: 1.5; }
    h1 { margin-bottom: 4px; }
    h2 { margin-top: 32px; font-size: 1.1rem; }
    .summary { color: #555; margin-top: 0; }
    .table-wrap { overflow-x: auto; }
    table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
    th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: right; }
    th:first-child, td:first-child { text-align: left; }
    thead th { background: #f2f2f2; }
    tbody tr:nth-child(even) { background: #fafafa; }
    footer { margin-top: 40px; font-size: 0.85rem; color: #666; }
    @media (prefers-color-scheme: dark) {
      body { background: #1b1b1b; color: #eee; }
      th, td { border-color: #444; }
      thead th { background: #2a2a2a; }
      tbody tr:nth-child(even) { background: #232323; }
      .summary, footer { color: #aaa; }
    }
"""


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/campaign-analysis")


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok", "rows": str(len(df))}


@app.get("/campaign-analysis", response_class=HTMLResponse)
async def campaign_analysis() -> HTMLResponse:
    """Campaign response rates by segment, rendered as HTML tables."""
    stats = overall_stats()
    sections = "\n".join(
        f"<h2>{heading}</h2>\n<div class='table-wrap'>{table.to_html(border=0)}</div>"
        for heading, table in build_segments().items()
    )

    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Campaign Analysis Results</title>
    <style>{PAGE_STYLE}</style>
  </head>
  <body>
    <h1>Skin Clinic Campaign Analysis</h1>
    <p class="summary">
      {stats['customers']:,} customers &middot; {stats['responders']:,} responded &middot;
      overall response rate {stats['response_rate_pct']}%
    </p>
    {sections}
    <footer>Same results as JSON: <a href="/campaign-analysis.json">/campaign-analysis.json</a></footer>
  </body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/campaign-analysis.json")
async def campaign_analysis_json() -> dict:
    """The same tables as JSON, for programmatic consumers."""
    return {
        "overall": overall_stats(),
        "segments": {
            heading: table.reset_index().to_dict(orient="records")
            for heading, table in build_segments().items()
        },
    }


if __name__ == "__main__":
    import uvicorn

    # app_dir pins the import to THIS folder. Without it the reloader subprocess
    # resolves "main" against the current working directory, which picks up the
    # capstone project's main.py (same module name, same `app`) if that is the cwd.
    # Port 8010 likewise stays clear of the capstone app's 8000.
    app_dir = Path(__file__).parent
    print(f"Serving {Path(__file__)} on http://127.0.0.1:8010/campaign-analysis")
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8010,
        reload=True,
        app_dir=str(app_dir),
        reload_dirs=[str(app_dir)],
    )
