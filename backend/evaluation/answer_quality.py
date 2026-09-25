"""Compares three ways of answering the same question from the same sources, and measures each answer.

    python -m evaluation.answer_quality collect [--case ID ...]      # once: real sources, free, slow, networked
    python -m evaluation.answer_quality run     [--case ID ...] [--system A,B,PIPELINE]
    python -m evaluation.answer_quality rescore                      # after changing a metric: no model, no network
    python -m evaluation.answer_quality report

The systems, all on the local model and all reading the same frozen sources (`frozen_corpus.py`):

- **A**: the model alone, given only the place and the question. What a plain chat model would say.
- **B**: the model handed every source's text in one prompt and asked to answer from them and cite by number. Retrieval-augmented
  generation with none of the pipeline's checks.
- **PIPELINE**: the real agent: planning, relevance ranking, claim extraction with citations, deterministic verification,
  synthesis, and the overview's own unbacked-sentence check.

No search credit is spent (the sources are frozen) and no model but the local one is used. Each run is saved as it finishes, so
an interrupted evaluation resumes where it stopped. Answers are written to `evaluation/runs/` (gitignored); what is committed is
`answer_quality_results.json`, which holds the measurements and no source or answer text.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.core.llm_service import LLMServiceError, OllamaLLMService  # noqa: E402
from app.models.evidence import Evidence  # noqa: E402
from app.models.location import Location  # noqa: E402
from evaluation import frozen_corpus  # noqa: E402
from evaluation.quality_cases import QUALITY_CASES, QualityCase  # noqa: E402
from evaluation.quality_metrics import (  # noqa: E402
    citation_check,
    sentence_grounding,
    states_a_limit,
    unsupported_specifics,
    word_count,
)

RUNS_DIR = Path(__file__).resolve().parent / "runs"
RESULTS_PATH = Path(__file__).resolve().parent / "answer_quality_results.json"
SYSTEMS = ("A", "B", "PIPELINE")
RUN_TIMEOUT_SECONDS = 20 * 60  # no single run may take longer than this
_SOURCE_BUDGET_CHARS = 8000  # what fits in the model's context beside the question

_SYSTEM_PROMPT = (
    "You are a careful analyst answering a question about a place. Answer in plain prose, about 150 words, with no headings."
)
_SYSTEM_PROMPT_SOURCES = (
    _SYSTEM_PROMPT + " Use only the numbered sources you are given, and cite them like [1]. If they do not cover something, say so "
    "instead of filling the gap."
)


_JSON_REPLY = ' Reply as JSON: {"answer": "your answer, as plain prose"}'


def _ask(llm: OllamaLLMService, system_prompt: str, user_prompt: str) -> str:
    """One call, made the way the pipeline's own calls are: the service forces JSON output (every component of the app
    asks for JSON), so the baselines answer in a JSON field too and the model and its settings are identical for all three."""
    for attempt in range(3):  # the local server sometimes answers 500 once and is fine a moment later
        try:
            raw = llm.complete(system_prompt + _JSON_REPLY, user_prompt)
            break
        except LLMServiceError:
            if attempt == 2:
                raise
            time.sleep(20)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    answer = value.get("answer") if isinstance(value, dict) else None
    if isinstance(answer, list):
        answer = " ".join(str(part) for part in answer)
    return str(answer) if answer else raw


def _place_line(location: Location) -> str:
    return ", ".join(p for p in (location.name, location.city, location.region, location.country) if p)


def _source_text(item: Evidence) -> str:
    return f"{item.source_title}. {item.text}".strip()


def _provenance_text(item: Evidence) -> str:
    """What the system was told about a source besides its words: who published it, when, and its license line. An answer
    may say "a 2026 Reddit post" or "CC BY-SA" without inventing anything, so these count as known when looking for specifics."""
    when = item.published_at.strftime("%Y-%m-%d %B %Y") if item.published_at else ""
    return " ".join(part for part in (item.publisher or "", when, " ".join(item.metadata.values())) if part)


def answer_a(llm: OllamaLLMService, location: Location, question: str, evidence: list[Evidence]) -> tuple[str, dict]:
    return _ask(llm, _SYSTEM_PROMPT, f"Place: {_place_line(location)}\nQuestion: {question}"), {}


def answer_b(llm: OllamaLLMService, location: Location, question: str, evidence: list[Evidence]) -> tuple[str, dict]:
    lines: list[str] = []
    used = 0
    for i, item in enumerate(evidence, start=1):
        line = f"[{i}] {_source_text(item)[:350]}"
        if used + len(line) > _SOURCE_BUDGET_CHARS:
            break
        lines.append(line)
        used += len(line)
    prompt = f"Place: {_place_line(location)}\nQuestion: {question}\n\nSources:\n" + "\n".join(lines)
    return _ask(llm, _SYSTEM_PROMPT_SOURCES, prompt), {"sources_in_prompt": len(lines)}


def answer_pipeline(llm: OllamaLLMService, location: Location, question: str, evidence: list[Evidence]) -> tuple[str, dict]:
    agent = frozen_corpus.build_frozen_agent(evidence, use_llm=True)
    response = agent.run(location, question)
    answer = "\n".join(part for part in (response.summary, *response.key_findings, response.details, response.recommendation) if part)
    check = citation_check(response.claims, response.evidence)
    return answer, {
        "evidence_kept": len(response.evidence),
        "claims": check.claims,
        "claims_with_real_citation": check.with_real_citation,
        "claims_worded_like_source": check.worded_like_its_source,
        "claims_supported": sum(1 for c in response.claims if c.status.value == "supported"),
        "claims_contradicted": sum(1 for c in response.claims if c.status.value == "contradicted"),
        "topics_planned": len(response.topics),
        "topics_with_evidence": len({e.topic for e in response.evidence}),
        "limitations": list(response.limitations),
        "trace_steps": len(response.research_trace),
    }


_RUNNERS = {"A": answer_a, "B": answer_b, "PIPELINE": answer_pipeline}


def _with_timeout(fn, seconds: int):
    """Runs `fn` in a daemon thread so a stuck model call cannot hold the whole evaluation past `seconds`."""
    box: dict = {}

    def target() -> None:
        try:
            box["value"] = fn()
        except Exception as exc:  # recorded as the run's error, never hidden
            box["error"] = f"{type(exc).__name__}: {exc}"

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        return None, f"timed out after {seconds // 60} minutes"
    return box.get("value"), box.get("error")


def score_answer(case: QualityCase, answer: str, limitations: list[str] | None) -> dict:
    """The deterministic measurements of one answer against its case's frozen sources (no model involved)."""
    location, evidence, _ = frozen_corpus.load(case)
    sources = [_source_text(e) for e in evidence]
    allowed = [case.place, case.question, _place_line(location), *(_provenance_text(e) for e in evidence)]
    grounding = sentence_grounding(answer, sources)
    specifics = unsupported_specifics(answer, sources, allowed)
    return {
        "words": word_count(answer),
        "sentences_assessed": grounding.assessed,
        "sentences_ungrounded": grounding.ungrounded,
        "ungrounded_share": grounding.ungrounded_share,
        "specifics_total": specifics.total,
        "specifics_unsupported": len(specifics.unsupported),
        "unsupported_examples": list(specifics.unsupported[:6]),
        "states_a_limit": states_a_limit(answer, limitations),
        "states_a_limit_in_its_own_words": states_a_limit(answer, None),
    }


def run_one(case: QualityCase, system: str) -> dict:
    path = RUNS_DIR / f"{case.case_id}__{system}.json"
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if "error" not in saved:  # a failed run (a model server hiccup, a timeout) is tried again, a finished one is kept
            return saved

    location, evidence, corpus_info = frozen_corpus.load(case)
    llm = OllamaLLMService()

    started = time.perf_counter()
    value, error = _with_timeout(lambda: _RUNNERS[system](llm, location, case.question, evidence), RUN_TIMEOUT_SECONDS)
    seconds = round(time.perf_counter() - started, 1)

    result: dict = {"case_id": case.case_id, "system": system, "seconds": seconds, "corpus": {**corpus_info, "items": len(evidence)}}
    if value is None:
        result["error"] = error or "no answer"
    else:
        answer, extra = value
        result.update(score_answer(case, answer, extra.get("limitations")), **extra)
        result["answer"] = answer
    RUNS_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def _selected(ids: list[str] | None) -> list[QualityCase]:
    cases = [c for c in QUALITY_CASES if not ids or c.case_id in ids]
    if ids and len(cases) != len(set(ids)):
        sys.exit(f"Unknown case id in {ids}. Known: {[c.case_id for c in QUALITY_CASES]}")
    return cases


def cmd_collect(args) -> None:
    for case in _selected(args.case):
        if frozen_corpus.corpus_path(case).exists() and not args.refresh:
            print(f"{case.case_id}: already collected (use --refresh to redo)")
            continue
        print(f"{case.case_id}: collecting for {case.place!r} ...", flush=True)
        try:
            payload = frozen_corpus.collect(case)
            print(f"  {len(payload['evidence'])} items {payload['counts']}")
        except Exception as exc:
            print(f"  FAILED: {type(exc).__name__}: {exc}")


def cmd_run(args) -> None:
    systems = [s.strip().upper() for s in args.system.split(",")]
    for case in _selected(args.case):
        if not frozen_corpus.corpus_path(case).exists():
            print(f"{case.case_id}: no corpus (run collect first), skipped")
            continue
        for system in systems:
            print(f"{case.case_id} / {system} ...", end=" ", flush=True)
            r = run_one(case, system)
            print(r.get("error") or f"{r['seconds']}s, {r['words']} words, ungrounded {r['ungrounded_share']}, unsupported specifics {r['specifics_unsupported']}/{r['specifics_total']}", flush=True)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def cmd_rescore(_args) -> None:
    """Recomputes every saved run's measurements from its saved answer: no model, no network. For when a metric changes."""
    for case in QUALITY_CASES:
        for system in SYSTEMS:
            path = RUNS_DIR / f"{case.case_id}__{system}.json"
            if not path.exists():
                continue
            r = json.loads(path.read_text(encoding="utf-8"))
            if "answer" in r:
                r.update(score_answer(case, r["answer"], r.get("limitations")))
                path.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print("rescored")


def cmd_report(_args) -> None:
    rows: list[dict] = []
    for case in QUALITY_CASES:
        for system in SYSTEMS:
            path = RUNS_DIR / f"{case.case_id}__{system}.json"
            if path.exists():
                r = json.loads(path.read_text(encoding="utf-8"))
                r.pop("answer", None)
                r["limitations"] = len(r.get("limitations", []))  # a count: the text can quote answers and sources
                r["kind"] = case.kind
                rows.append(r)
    ok = [r for r in rows if "error" not in r]
    print(f"{len(rows)} runs, {len(rows) - len(ok)} failed\n")
    print("| system | runs | mean seconds | mean words | sentences ungrounded | unsupported specifics | per 100 words | says it lacks something (own words / any) |")
    print("|---|---|---|---|---|---|---|---|")
    summary = {}
    for system in SYSTEMS:
        rs = [r for r in ok if r["system"] == system]
        if not rs:
            continue
        assessed = sum(r["sentences_assessed"] for r in rs)
        ungrounded = sum(r["sentences_ungrounded"] for r in rs)
        total = sum(r["specifics_total"] for r in rs)
        unsupported = sum(r["specifics_unsupported"] for r in rs)
        limit = sum(1 for r in rs if r["states_a_limit"])
        own = sum(1 for r in rs if r["states_a_limit_in_its_own_words"])
        words = sum(r["words"] for r in rs)
        summary[system] = {
            "runs": len(rs), "mean_seconds": _mean([r["seconds"] for r in rs]), "mean_words": _mean([r["words"] for r in rs]),
            "sentences_assessed": assessed, "sentences_ungrounded": ungrounded,
            "specifics_total": total, "specifics_unsupported": unsupported, "runs_admitting_a_limit": limit, "runs_admitting_a_limit_in_own_words": own,
            "unsupported_specifics_per_100_words": round(100 * unsupported / words, 2),
        }
        share = f"{ungrounded}/{assessed} ({ungrounded / assessed:.0%})" if assessed else "n/a"
        spec = f"{unsupported}/{total} ({unsupported / total:.0%})" if total else "n/a"
        print(f"| {system} | {len(rs)} | {summary[system]['mean_seconds']} | {summary[system]['mean_words']} | {share} | {spec} | {100 * unsupported / words:.2f} | {own}/{len(rs)} / {limit}/{len(rs)} |")
    pipe = [r for r in ok if r["system"] == "PIPELINE"]
    if pipe:
        c, real, worded = (sum(r[k] for r in pipe) for k in ("claims", "claims_with_real_citation", "claims_worded_like_source"))
        sup = sum(r["claims_supported"] for r in pipe)
        print(f"\nPIPELINE claims: {c} extracted, {real} cite evidence that exists, {worded} are worded like it, {sup} marked supported by the verifier")
        summary["pipeline_claims"] = {"claims": c, "with_real_citation": real, "worded_like_source": worded, "supported": sup}
    print("\nPer case (ungrounded sentences / assessed, unsupported specifics / total):")
    for case in QUALITY_CASES:
        cells = []
        for system in SYSTEMS:
            r = next((x for x in ok if x["case_id"] == case.case_id and x["system"] == system), None)
            cells.append(f"{system} {r['sentences_ungrounded']}/{r['sentences_assessed']}, {r['specifics_unsupported']}/{r['specifics_total']}" if r else f"{system} -")
        corpus = next((r["corpus"] for r in ok if r["case_id"] == case.case_id), None)
        print(f"  {case.case_id:<18} {' | '.join(cells)}   corpus {corpus['items'] if corpus else '-'}")
    RESULTS_PATH.write_text(json.dumps({"summary": summary, "runs": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nWritten to {RESULTS_PATH.name} (measurements only: no source or answer text)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in (("collect", cmd_collect), ("run", cmd_run), ("rescore", cmd_rescore), ("report", cmd_report)):
        p = sub.add_parser(name)
        p.set_defaults(fn=fn)
        if name in ("collect", "run"):
            p.add_argument("--case", action="append", help="a case id (repeatable); default all")
        if name == "collect":
            p.add_argument("--refresh", action="store_true")
        if name == "run":
            p.add_argument("--system", default=",".join(SYSTEMS))
    args = parser.parse_args()
    try:
        args.fn(args)
    except LLMServiceError as exc:
        sys.exit(f"The local model is not available: {exc}")


if __name__ == "__main__":
    main()
