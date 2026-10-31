"""Run the behaviour evals against a running server (spec 07).

    uv run python -m evals.run [--cases discovery specs repo-reader] [--trials 3] [--compare results/<file>.json]

Each trial uses a disposable project and always deletes it. Results go to ``evals/results/<timestamp>.json``.
Only event summaries are printed, never secrets.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .cases import CASES, Case

RESULTS = Path(__file__).parent / "results"


def grade(case: Case, trial: dict) -> dict:
    graded = {}
    for name, check in case.checks.items():
        try:
            passed, note = check(trial)
        except (
            KeyError,
            IndexError,
            TypeError,
        ) as problem:  # a trial that ended before this check's data
            passed, note = None, f"not reached ({problem!r})"
        graded[name] = {"passed": passed, "note": note}
    return graded


def run_trial(client: httpx.Client, case: Case, number: int) -> dict:
    project = client.post(
        "/api/projects", json={"title": f"[eval] {case.name} #{number}"}
    ).json()["project_id"]
    try:
        trial = case.run(client, project)
        return {
            "project": project,
            "checks": grade(case, trial),
            "turns": trial.get("turns", []),
        }
    except Exception as problem:  # noqa: BLE001 — one failed trial is a result, not the end of the run
        return {
            "project": project,
            "error": f"{type(problem).__name__}: {problem}",
            "trace": traceback.format_exc(limit=3),
            "checks": {},
        }
    finally:
        client.delete(f"/api/projects/{project}")


def rates(results: dict) -> dict[str, dict[str, list[int]]]:
    """case -> check -> [passed, reached]."""
    table: dict[str, dict[str, list[int]]] = {}
    for case, trials in results.items():
        for trial in trials:
            for check, outcome in trial["checks"].items():
                cell = table.setdefault(case, {}).setdefault(check, [0, 0])
                if outcome["passed"] is not None:
                    cell[1] += 1
                    cell[0] += int(outcome["passed"])
    return table


def report(results: dict, previous: dict | None = None) -> str:
    now, before = rates(results), rates(previous or {})
    lines = []
    for case, trials in results.items():
        errors = sum(1 for t in trials if "error" in t)
        lines.append(
            f"{case}: {len(trials)} trial(s){f', {errors} ended in an error' if errors else ''}"
        )
        for check, (passed, reached) in now.get(case, {}).items():
            line = (
                f"  {check:<34} {passed}/{reached}"
                if reached
                else f"  {check:<34} not reached"
            )
            old = before.get(case, {}).get(check)
            if old and old[1] and reached:
                line += f"   (was {old[0]}/{old[1]})"
            lines.append(line)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Behaviour evals over several trials")
    parser.add_argument(
        "--cases", nargs="+", choices=sorted(CASES), default=sorted(CASES)
    )
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--compare", type=Path, help="an earlier results file to compare with"
    )
    args = parser.parse_args(argv)

    results: dict[str, list[dict]] = {}
    with httpx.Client(base_url=args.base_url, timeout=900) as client:
        client.get("/api/health").raise_for_status()
        for name in args.cases:
            for number in range(1, args.trials + 1):
                print(f"{name} trial {number}/{args.trials}…", flush=True)
                trial = run_trial(client, CASES[name], number)
                results.setdefault(name, []).append(trial)
                if "error" in trial:
                    print(f"  error: {trial['error']}", flush=True)
                for check, outcome in trial["checks"].items():
                    mark = {True: "pass", False: "FAIL", None: "n/a"}[outcome["passed"]]
                    print(f"  {mark:<4} {check}: {outcome['note']}", flush=True)

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{datetime.now(UTC):%Y%m%d-%H%M%S}.json"
    out.write_text(
        json.dumps({"trials": args.trials, "results": results}, indent=2),
        encoding="utf-8",
    )
    previous = (
        json.loads(args.compare.read_text(encoding="utf-8"))["results"]
        if args.compare
        else None
    )
    print("\n" + report(results, previous))
    print(f"\nSaved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
