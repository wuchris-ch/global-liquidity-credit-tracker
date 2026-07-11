"""Regression checks for inline shell scripts in GitHub Actions workflows."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
GITHUB_EXPRESSION = re.compile(r"\$\{\{.*?\}\}", re.DOTALL)


def test_inline_bash_steps_have_valid_syntax() -> None:
    """Catch YAML indentation mistakes before GitHub executes a run block."""
    failures: list[str] = []

    for workflow_path in sorted(WORKFLOWS_DIR.glob("*.y*ml")):
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        for job_name, job in workflow.get("jobs", {}).items():
            if not str(job.get("runs-on", "")).startswith("ubuntu"):
                continue

            for step in job.get("steps", []):
                script = step.get("run")
                shell = str(step.get("shell", "bash")).split()[0]
                if not script or shell != "bash":
                    continue

                # GitHub expands expressions before invoking the generated script.
                parsed_script = GITHUB_EXPRESSION.sub("github_expression", script)
                result = subprocess.run(
                    ["bash", "-n"],
                    input=parsed_script,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if result.returncode:
                    location = (
                        f"{workflow_path.relative_to(ROOT)} :: {job_name} :: "
                        f"{step.get('name', 'unnamed step')}"
                    )
                    failures.append(f"{location}\n{result.stderr.strip()}")

    assert not failures, "Invalid workflow shell syntax:\n\n" + "\n\n".join(failures)
