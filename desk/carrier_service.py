import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "carrier_shipments.json"
app = FastAPI(title="Reference Carrier API", version="1.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/shipments")
def shipments():
    outage_file = os.environ.get("DESK_CARRIER_OUTAGE_FILE")
    if outage_file and Path(outage_file).exists():
        return JSONResponse({"detail": "Synthetic carrier outage"}, status_code=503)
    return json.loads(FIXTURE.read_text(encoding="utf-8"))
