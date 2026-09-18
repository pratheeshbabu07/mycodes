# Skin Clinic Campaign Analysis API

FastAPI service that reports campaign response rates by customer segment.

| Endpoint | What it returns |
| --- | --- |
| `GET /campaign-analysis` | HTML tables: gender, age group, purchase last quarter, product usage |
| `GET /campaign-analysis.json` | The same results as JSON |
| `GET /health` | Liveness check used by Render |
| `GET /docs` | Swagger UI (built into FastAPI) |
| `GET /` | Redirects to `/campaign-analysis` |

Each table shows customers, responders, non-responders and response rate (%).

## Run locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload
# http://127.0.0.1:8000/campaign-analysis
```

## Deploy to Render

The data file lives in `data/skin_clinic_campaign.csv` and is read with a path
relative to `main.py`, so no configuration is needed beyond the build and start
commands.

1. Push this folder to its own GitHub repository:

   ```bash
   cd campaign_api
   git init -b main
   git add .
   git commit -m "Campaign analysis FastAPI app"
   git remote add origin https://github.com/<your-user>/campaign-analysis-api.git
   git push -u origin main
   ```

2. On [dashboard.render.com](https://dashboard.render.com) choose
   **New → Web Service** and connect that repository.

3. Render reads `render.yaml` and fills these in; confirm they match:

   | Setting | Value |
   | --- | --- |
   | Language / Runtime | Python 3 |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
   | Instance Type | Free |
   | Health Check Path | `/health` |

   If you push the *parent* repo instead of just this folder, also set
   **Root Directory** to `py/pcf_models/ml_scripts/DataScienceInst/campaign_api`.

4. Click **Deploy**. The live URL is
   `https://<service-name>.onrender.com/campaign-analysis`.

Note: free Render instances sleep after ~15 minutes idle, so the first request
after a pause takes 30-60 seconds to wake up.
