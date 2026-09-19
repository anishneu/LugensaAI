"""Run the Milestone 8 evaluation benchmark and print a results table.

    python -m evaluation.run_benchmark

Requires TAVILY_API_KEY (both systems use live search — see baselines.py and
proposed_system.py for why). Does not use an LLM: Baseline A is not
implemented and the proposed system runs without claim extraction, both noted
plainly in the output rather than faked. See docs/evaluation.md for the full write-up of what
these numbers do and don't show.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import llm_enabled, search_enabled  # noqa: E402
from evaluation.baselines import run_baseline_b  # noqa: E402
from evaluation.benchmark import BENCHMARK_CASES  # noqa: E402
from evaluation.metrics import RunMetrics  # noqa: E402
from evaluation.proposed_system import run_proposed_system  # noqa: E402


def _print_table(rows: list[dict[str, str]]) -> None:
    columns = list(rows[0].keys())
    widths = {c: max(len(c), max(len(row[c]) for row in rows)) for c in columns}
    header = " | ".join(c.ljust(widths[c]) for c in columns)
    print(header)
    print("-+-".join("-" * widths[c] for c in columns))
    for row in rows:
        print(" | ".join(row[c].ljust(widths[c]) for c in columns))


def main() -> None:
    if not search_enabled():
        print("TAVILY_API_KEY is not set — both systems need live search for this benchmark. Aborting.")
        sys.exit(1)

    print("Baseline A (plain LLM call, no tools): not implemented.")
    print(f"LLM-backed components enabled: {llm_enabled()} (this benchmark runs without them either way)")
    print()

    results: list[RunMetrics] = []
    for case in BENCHMARK_CASES:
        print(f"Running case '{case.case_id}' ({case.category})...")
        results.append(run_baseline_b(case))
        results.append(run_proposed_system(case))

    print()
    _print_table([r.as_row() for r in results])

    print()
    for r in results:
        if r.notes or r.error:
            print(f"[{r.case_id}/{r.system}]")
            if r.error:
                print(f"  error: {r.error}")
            for note in r.notes:
                print(f"  note: {note}")

    output_path = Path(__file__).resolve().parent / "last_run_results.json"
    output_path.write_text(json.dumps([r.__dict__ for r in results], indent=2))
    print(f"\nFull results written to {output_path}")


if __name__ == "__main__":
    main()
