"""Run every sample in the pack through the agent and compare with its *-expected.json.

  python run_samples.py                    # all samples
  python run_samples.py --only 03          # one sample
  python run_samples.py --screenshots out/shots   # also render each proposal in the tool

The comparison is deliberately forgiving about prose (needs, riskProfile) and strict about
facts: names, model, currency, amounts, fee, target return, greeting target, replacement.
A sample whose filename contains "sparse" must NOT contain any invented figures.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from agent import GUARDED_FIELDS, ProposalError, extract_proposal, get_path, make_client

CHECKS = [
    "clientName",
    "introGreetTo",
    "applyModel",
    "financialPlanner",
    "goalAssessment.clientType",
    "goalAssessment.currency",
    "goalAssessment.keyFigures.totalInvestment",
    "goalAssessment.keyFigures.incomeValue",
    "objective.targetReturn",
    "fees.advisorFee",
    "replacements.isReplacement",
]
TITLES = {"mr", "mrs", "ms", "dr", "the", "miss", "prof"}


def _norm(s) -> str:
    s = str(s).lower().replace("plus", "+")
    return re.sub(r"[^a-z0-9+.%]", "", s)


def same(path: str, got, exp) -> bool:
    if path == "clientName":
        got_t = set(re.findall(r"[a-z]+", str(got).lower()))
        return all(t in got_t for t in re.findall(r"[a-z]+", str(exp).lower()) if t not in TITLES)
    if path.endswith(("totalInvestment", "incomeValue", "advisorFee")):
        try:
            return abs(float(got) - float(exp)) < 1e-9
        except (TypeError, ValueError):
            return False
    if isinstance(exp, bool):
        return got is exp
    return _norm(got) == _norm(exp)


def find_samples(pack: Path, only: str | None):
    folder = pack / "sample-inputs"
    for exp in sorted(folder.glob("*-expected.json")):
        prefix = exp.name.split("-")[0]
        if only and prefix != only:
            continue
        notes = [p for p in folder.glob(f"{prefix}-*.txt")]
        if notes:
            yield prefix, notes[0], exp


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default=os.getenv("PACK_DIR", "meridian-ai-challenge"))
    ap.add_argument("--only", help="run just one sample number, e.g. 03")
    ap.add_argument("--screenshots", help="folder to save a PNG of each loaded proposal")
    args = ap.parse_args()

    pack = Path(args.pack)
    client = make_client()
    total_pass = total_checks = 0

    for prefix, notes_path, exp_path in find_samples(pack, args.only):
        expected = json.loads(exp_path.read_text(encoding="utf-8"))
        print(f"\n=== {notes_path.name} ===")
        try:
            result = extract_proposal(notes_path.read_text(encoding="utf-8"), client)
        except ProposalError as exc:
            print(f"  FAILED to produce a proposal: {exc}")
            continue
        got = result.proposal

        passed = 0
        checks = [c for c in CHECKS if get_path(expected, c) is not None]
        for path in checks:
            g, e = get_path(got, path), get_path(expected, path)
            ok = g is not None and same(path, g, e)
            passed += ok
            if not ok:
                print(f"  FAIL {path}: got {g!r}, expected {e!r}")
        total_pass += passed
        total_checks += len(checks)
        print(f"  {passed}/{len(checks)} fact checks passed (LLM attempts: {result.attempts})")

        # Fabrication watch: figures the reference output leaves blank.
        for path in GUARDED_FIELDS:
            if get_path(got, path) is not None and get_path(expected, path) is None:
                strict = "sparse" in notes_path.name
                print(f"  {'FAIL' if strict else 'note'} extra {path} = {get_path(got, path)!r}"
                      f" (quote: {result.evidence.get(path)!r})")
                if strict:
                    total_checks += 1
        for g in result.gaps:
            if g["type"] in ("missing", "removed"):
                print(f"  flagged: {g['label']}")

        if args.screenshots:
            from load_into_tool import load_into_tool
            shot = Path(args.screenshots) / f"{prefix}.png"
            load_into_tool(got, pack, headless=True, preview=True, screenshot=shot, wait=False)
            print(f"  screenshot: {shot}")

    print(f"\nOverall: {total_pass}/{total_checks} fact checks passed")
    return 0 if total_pass == total_checks else 1


if __name__ == "__main__":
    raise SystemExit(main())
