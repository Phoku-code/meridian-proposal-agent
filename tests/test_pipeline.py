"""Offline tests for the pipeline logic (no API key, no browser needed).

Run:  python tests/test_pipeline.py      (or: pytest -q)
A FakeClient stands in for the LLM so we can test validation, retries and the
fabrication guard deterministically.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent  # noqa: E402


class FakeClient:
    """Returns canned responses one after another, like chat.completions.create()."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        text = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        msg = SimpleNamespace(content=text if isinstance(text, str) else json.dumps(text))
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


NOTES = (
    "Mr George Whitfield, 63. Lump sum of about R6.2 million, wants roughly R28,000 a month. "
    "Horizon 15+ years. Income model. Adviser fee 0.60%."
)


def good_output(**over):
    out = {
        "proposal": {
            "clientName": "Mr George Whitfield",
            "applyModel": "income",
            "needs": "Mr Whitfield wants income.",
            "goalAssessment": {
                "clientType": "Individual",
                "currency": "ZAR",
                "keyFigures": {"totalInvestment": "6200000", "incomeValue": "28000"},
            },
            "objective": {"investmentHorizon": "15 years+"},
            "fees": {"advisorFee": "0.60"},
        },
        "evidence": {
            "goalAssessment.keyFigures.totalInvestment": "about R6.2 million",
            "goalAssessment.keyFigures.incomeValue": "R28,000 a month",
            "objective.investmentHorizon": "Horizon 15+ years",
            "fees.advisorFee": "Adviser fee 0.60%",
        },
        "gaps": [],
    }
    out.update(over)
    return out


def test_parse_amounts():
    assert agent.parse_amounts("R6.2 million") == [6_200_000]
    assert agent.parse_amounts("~R8.5m to invest") == [8_500_000]
    assert agent.parse_amounts("R45k a month income") == [45_000]
    assert agent.parse_amounts("USD 1.2m offshore") == [1_200_000]
    assert agent.parse_amounts("R28,000 a month") == [28_000]
    assert agent.parse_amounts("fee 0.75%") == [0.75]
    assert agent.parse_amounts("four and a half million") == []  # words: no digits to compare


def test_valid_output_passes_through_unchanged():
    res = agent.extract_proposal(NOTES, FakeClient(good_output()))
    p = res.proposal
    assert p["goalAssessment"]["keyFigures"] == {"totalInvestment": "6200000", "incomeValue": "28000"}
    assert p["fees"]["advisorFee"] == "0.60"
    assert "TO CONFIRM" not in p["needs"]
    assert res.attempts == 1 and not res.missing


def test_fabricated_figure_without_evidence_is_removed_and_flagged():
    out = good_output()
    del out["evidence"]["goalAssessment.keyFigures.totalInvestment"]
    res = agent.extract_proposal(NOTES, FakeClient(out))
    assert "totalInvestment" not in res.proposal["goalAssessment"]["keyFigures"]
    assert "[TO CONFIRM WITH CLIENT: investment amount" in res.proposal["needs"]
    assert any(g["type"] == "removed" for g in res.gaps)


def test_quote_not_in_notes_is_removed():
    sparse = "Mrs Petersen wants to invest a few million rand. Balanced feel."
    out = good_output()
    out["proposal"]["goalAssessment"]["keyFigures"] = {"totalInvestment": "5000000"}
    out["evidence"] = {"goalAssessment.keyFigures.totalInvestment": "R5 million to invest"}  # not in notes
    out["proposal"].pop("objective")
    out["proposal"].pop("fees")
    res = agent.extract_proposal(sparse, FakeClient(out))
    assert "keyFigures" not in res.proposal["goalAssessment"]
    assert any("not found in the notes" in g["note"] for g in res.gaps)


def test_value_must_match_its_own_quote():
    out = good_output()
    out["proposal"]["goalAssessment"]["keyFigures"]["totalInvestment"] = "620000"  # off by 10x
    res = agent.extract_proposal(NOTES, FakeClient(out))
    assert "totalInvestment" not in res.proposal["goalAssessment"]["keyFigures"]
    assert any("does not match" in g["note"] for g in res.gaps)


def test_numbers_are_normalised_to_digit_strings():
    out = good_output()
    out["proposal"]["goalAssessment"]["keyFigures"] = {"totalInvestment": "R6.2 million", "incomeValue": 28000}
    out["proposal"]["fees"]["advisorFee"] = "0.60%"
    res = agent.extract_proposal(NOTES, FakeClient(out))
    kf = res.proposal["goalAssessment"]["keyFigures"]
    assert kf == {"totalInvestment": "6200000", "incomeValue": "28000"}
    assert res.proposal["fees"]["advisorFee"] == "0.60"


def test_missing_core_details_are_flagged_in_needs():
    out = {
        "proposal": {"clientName": "Mrs Petersen", "applyModel": "balanced", "needs": "Prospect."},
        "evidence": {},
        "gaps": [
            {"label": "investment amount", "type": "missing", "note": ""},
            {"label": "time horizon", "type": "missing", "note": ""},
        ],
    }
    res = agent.extract_proposal("Mrs Petersen, a few million", FakeClient(out))
    assert res.proposal["needs"].endswith("[TO CONFIRM WITH CLIENT: investment amount, time horizon.]")


def test_retries_on_invalid_json():
    client = FakeClient("sorry, here you go: not json", good_output())
    res = agent.extract_proposal(NOTES, client)
    assert res.attempts == 2 and client.calls == 2


def test_retries_on_unknown_model():
    bad = good_output()
    bad["proposal"]["applyModel"] = "aggressive-plus"
    client = FakeClient(bad, good_output())
    res = agent.extract_proposal(NOTES, client)
    assert res.attempts == 2 and res.proposal["applyModel"] == "income"


def test_gives_up_after_max_attempts():
    client = FakeClient("nope")
    try:
        agent.extract_proposal(NOTES, client, max_attempts=2)
    except agent.ProposalError:
        assert client.calls == 2
    else:
        raise AssertionError("expected ProposalError")


def test_markdown_fenced_json_is_accepted():
    fenced = "```json\n" + json.dumps(good_output()) + "\n```"
    res = agent.extract_proposal(NOTES, FakeClient(fenced))
    assert res.attempts == 1


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print(f"ok  {name}")
    print(f"\n{len(tests)} tests passed")
