"""Regression checks for inline shell scripts in GitHub Actions workflows."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
GITHUB_EXPRESSION = re.compile(r"\$\{\{.*?\}\}", re.DOTALL)
HEREDOC_OPERATOR = re.compile(
    r"(?<!<)<<(-?)\s*(?:'([A-Za-z_]\w*)'|\"([A-Za-z_]\w*)\"|\\?([A-Za-z_]\w*))"
)


def _unterminated_heredocs(script: str) -> list[str]:
    """Return heredoc delimiters that never appear unindented on their own line.

    ``bash -n`` treats an unterminated heredoc as a warning (exit 0) on bash 5
    and stays silent on bash 3.2, so this is checked textually as well.
    """
    pending: list[tuple[str, bool]] = []
    unterminated: list[str] = []
    for line in script.split("\n"):
        if pending:
            delimiter, allow_tabs = pending[0]
            terminator = line.lstrip("\t") if allow_tabs else line
            if terminator == delimiter:
                pending.pop(0)
            continue
        for match in HEREDOC_OPERATOR.finditer(line):
            delimiter = match.group(2) or match.group(3) or match.group(4)
            pending.append((delimiter, match.group(1) == "-"))
    unterminated.extend(delimiter for delimiter, _ in pending)
    return unterminated


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
                problems: list[str] = []
                if result.returncode or result.stderr.strip():
                    problems.append(
                        result.stderr.strip() or f"bash -n exited {result.returncode}"
                    )
                problems.extend(
                    f"heredoc delimited by end-of-file (wanted `{delimiter}`)"
                    for delimiter in _unterminated_heredocs(parsed_script)
                )
                if problems:
                    location = (
                        f"{workflow_path.relative_to(ROOT)} :: {job_name} :: "
                        f"{step.get('name', 'unnamed step')}"
                    )
                    failures.append("\n".join([location, *problems]))

    assert not failures, "Invalid workflow shell syntax:\n\n" + "\n\n".join(failures)
