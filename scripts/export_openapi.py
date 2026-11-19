import json
from pathlib import Path

from desk.main import app

if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "openapi.json"
    target.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
