"""Generate the research contract without opening production storage."""

import json
import tempfile
from pathlib import Path

from src.research.api import create_app

with tempfile.TemporaryDirectory() as root:
    schema = create_app(root, start_worker=False).openapi()
Path("frontend/research-openapi.json").write_text(json.dumps(schema, indent=2) + "\n")
