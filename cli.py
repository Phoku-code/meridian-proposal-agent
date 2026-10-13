"""Adviser notes in -> proposal rendered in the Meridian tool.

Examples
  python cli.py meridian-ai-challenge/sample-inputs/01-notes-retiree-income.txt
  python cli.py notes.txt --interactive          # asks follow-up questions for missing details
  python cli.py notes.txt --no-open              # just write out/proposal.json
  python cli.py --text "Mrs Dube, R3m, wants R15k a month, 10 years, fee 0.5%"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent import ProposalError, extract_proposal, format_report, make_client
from load_into_tool import load_into_tool


def read_notes(args) -> str:
    if args.text:
        return args.text
    if args.notes in (None, "-"):
        return sys.stdin.read()
    return Path(args.notes).read_text(encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("notes", nargs="?", help="path to a notes .txt file, or '-' for stdin")
    ap.add_argument("--text", help="pass the notes directly as a string")
    ap.add_argument("--out", default="out/proposal.json", help="where to write the proposal JSON")
    ap.add_argument("--pack", default=None, help="folder containing challenge-generator.html (default: $PACK_DIR)")
    ap.add_argument("--no-open", action="store_true", help="do not open the browser")
    ap.add_argument("--preview", action="store_true", help="open on the rendered preview instead of the editor")
    ap.add_argument("--headless", action="store_true", help="no visible browser (use with --screenshot)")
    ap.add_argument("--screenshot", help="save a PNG of the loaded proposal")
    ap.add_argument("--interactive", action="store_true", help="ask follow-up questions about missing details")
    args = ap.parse_args()

    notes = read_notes(args)
    client = make_client()
    try:
        result = extract_proposal(notes, client)
        if args.interactive and result.missing and sys.stdin.isatty():
            print("\nThe notes are missing some details:")
            for g in result.missing:
                print(f"  - {g['label']}")
            answer = input("\nType what you know (or press Enter to leave them as flagged): ").strip()
            if answer:
                notes += f"\n\nAdditional details from the adviser: {answer}"
                result = extract_proposal(notes, client)
    except ProposalError as exc:
        print(f"Could not build a proposal: {exc}", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.proposal, indent=2, ensure_ascii=False), encoding="utf-8")
    # Fallback for pasting into the browser console by hand:
    out.with_suffix(".console.js").write_text(
        f"window.loadProposal({json.dumps(result.proposal, ensure_ascii=False)});\n", encoding="utf-8"
    )

    print(format_report(result))
    print(f"\nWrote {out}")

    if not args.no_open:
        load_into_tool(
            result.proposal,
            args.pack,
            headless=args.headless,
            preview=args.preview,
            screenshot=args.screenshot,
            wait=not args.headless,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
