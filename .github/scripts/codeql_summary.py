"""Reads CodeQL's SARIF output and reports it where a person will see it: the job summary and file annotations.

Used when the results cannot be uploaded to GitHub code scanning (a private repository without GitHub Code Security), so
the Security tab has nothing to show. The analysis is unchanged; only where its results go is different. This script never
fails the job: a finding is information to read, not a broken build. Run it as `python codeql_summary.py <dir-or-file>...`.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

_MAX_ANNOTATIONS = 40
_MAX_LISTED = 60
# CodeQL levels as GitHub annotation levels. Everything is at most a warning: this report never marks the build failed.
_ANNOTATION_LEVEL = {"error": "warning", "warning": "warning", "note": "notice", "recommendation": "notice", "none": "notice"}


def _escape(value: str, *, is_property: bool = False) -> str:
    """GitHub's workflow-command escaping: `%`, newlines, and for property values also `:` and `,`."""
    value = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return value.replace(":", "%3A").replace(",", "%2C") if is_property else value


def _sarif_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(sorted(path.rglob("*.sarif")))
        elif path.is_file():
            files.append(path)
        else:
            print(f"::notice::No CodeQL results at {raw}: the analysis did not produce any, so there is nothing to report.")
    return files


def findings_in(sarif: dict) -> list[dict]:
    """Every result in a SARIF document as {rule, level, message, file, line}."""
    found: list[dict] = []
    for run in sarif.get("runs", []):
        rules = {rule.get("id"): rule for rule in run.get("tool", {}).get("driver", {}).get("rules", [])}
        for result in run.get("results", []):
            rule_id = result.get("ruleId") or "unknown"
            default = (rules.get(rule_id, {}).get("defaultConfiguration") or {}).get("level")
            location = ((result.get("locations") or [{}])[0]).get("physicalLocation", {})
            found.append(
                {
                    "rule": rule_id,
                    "level": result.get("level") or default or "warning",
                    "message": (result.get("message") or {}).get("text", "").strip(),
                    "file": (location.get("artifactLocation") or {}).get("uri", ""),
                    "line": (location.get("region") or {}).get("startLine", 1),
                }
            )
    return found


def render(findings: list[dict], analysed: int) -> str:
    if analysed == 0:
        return "### CodeQL\n\nNo results file was found, so nothing could be reported: the analysis step did not produce one.\n"
    if not findings:
        return f"### CodeQL\n\nNo findings ({analysed} result file(s) read). The analysis ran on every file of the language.\n"
    counts = Counter(f["level"] for f in findings)
    lines = ["### CodeQL", "", f"{len(findings)} finding(s): " + ", ".join(f"{n} {level}" for level, n in counts.most_common()), ""]
    lines += ["| Level | Rule | Where | What |", "|---|---|---|---|"]
    for f in findings[:_MAX_LISTED]:
        message = f["message"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {f['level']} | `{f['rule']}` | `{f['file']}:{f['line']}` | {message} |")
    if len(findings) > _MAX_LISTED:
        lines.append(f"\n{len(findings) - _MAX_LISTED} more are in the uploaded results file.")
    return "\n".join(lines) + "\n"


def annotate(findings: list[dict]) -> list[str]:
    commands = []
    for f in findings[:_MAX_ANNOTATIONS]:
        level = _ANNOTATION_LEVEL.get(f["level"], "warning")
        title = f"title={_escape('CodeQL: ' + f['rule'], is_property=True)}"
        properties = f"file={_escape(f['file'], is_property=True)},line={f['line']},{title}" if f["file"] else title
        commands.append(f"::{level} {properties}::{_escape(f['message'])}")
    return commands


def main(argv: list[str]) -> int:
    files = _sarif_files(argv or ["."])
    findings: list[dict] = []
    for path in files:
        findings.extend(findings_in(json.loads(path.read_text(encoding="utf-8"))))
    for command in annotate(findings):
        print(command)
    report = render(findings, len(files))
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
