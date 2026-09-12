"""Refresh the TypeScript contract with the repository's notice conventions."""

import subprocess
from pathlib import Path

subprocess.run(
    [
        "npx",
        "openapi-typescript",
        "research-openapi.json",
        "-o",
        "src/lib/research-api.d.ts",
    ],
    cwd="frontend",
    check=True,
)
path = Path("frontend/src/lib/research-api.d.ts")
text = path.read_text()
if text.startswith("/**"):
    text = text.split("*/", 1)[1].lstrip()
path.write_text(text)
