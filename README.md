# Meridian proposal agent

Turns a Portfolio Manager's rough notes (or a voice-note transcript) into a proposal that is
pre-populated in the Meridian proposal tool, ready to review and tweak.

```
adviser notes ──► LLM extraction ──► schema check ──► grounding guard ──► gaps flagged ──► window.loadProposal(...)
 (text file)      {proposal,         (schema.json,    (every figure must   ([TO CONFIRM     (Playwright opens
                   evidence, gaps}    retry on error)  be quoted from the    WITH CLIENT]     the tool in a browser)
                                                       notes and match it)   + report)
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env        # (Windows: copy .env.example .env) then edit .env and add your key
```

Unzip the challenge pack into this folder so that `meridian-ai-challenge/challenge-generator.html`
exists (or set `PACK_DIR` in `.env`).

**Model / framework:** plain Python with the `openai` SDK pointed at any OpenAI-compatible
endpoint. The defaults in `.env.example` use **Google Gemini** (`gemini-3.8-flash`) through its
OpenAI-compatible endpoint, with a free key from Google AI Studio. Change `LLM_BASE_URL`,
`LLM_MODEL` and `LLM_API_KEY` to use OpenAI, Claude, or a local model. (I first tried GitHub Models,
but it was retired on 30 July 2026.) Model names change over time; if you get a 404 saying a model is
"no longer available", check the provider's current model list.

## Run

```bash
# one set of notes -> JSON + proposal opens in the tool
python cli.py meridian-ai-challenge/sample-inputs/01-notes-retiree-income.txt

# a voice-note transcript works the same way
python cli.py meridian-ai-challenge/sample-inputs/04-voice-note-transcript.txt

# ask follow-up questions in the terminal when core details are missing
python cli.py meridian-ai-challenge/sample-inputs/03-notes-sparse.txt --interactive

# notes inline, or just write out/proposal.json without opening a browser
python cli.py --text "Dr Dube, R3m, R15k a month, 10 years, fee 0.5%" --no-open
```

Outputs land in `out/`: `proposal.json` and `proposal.console.js` (paste into the tool's browser
console as a manual fallback).

## Troubleshooting

- **"The model service did not return a normal answer"**: the endpoint is wrong, retired, or something
  on your network is intercepting the request. Run `python check_llm.py` to see what comes back.
- **Mac/Linux:** use `python3 -m venv .venv`, `source .venv/bin/activate`, `cp .env.example .env`,
  and forward slashes in paths (`meridian-ai-challenge/sample-inputs/...`).

## Check it against the samples

```bash
python run_samples.py                          # compares each sample with its *-expected.json
python run_samples.py --screenshots out/shots  # also renders each proposal in the tool
python tests/test_pipeline.py                  # offline tests, no API key needed
```

## Design decisions

- **Contract first.** The output is validated against `schema.json`. If the model returns invalid
  JSON or an unknown model ID, it is shown the errors and asked to fix them (max 3 attempts).
- **Use `applyModel`.** The agent picks one of the three model portfolios and lets the tool fill
  allocation, composition and fees. The LLM only supplies client-specific fields.
- **Never fabricate figures.** The model must return a short verbatim quote ("evidence") for every
  amount, income, fee, horizon, target return and benchmark. Code then checks that the quote really
  appears in the notes and that the number in the value matches the number in the quote
  (`R6.2 million` -> `6200000`). Anything that fails is removed, not guessed.
- **Say what is missing.** Core gaps (investment amount, monthly income, horizon) are appended to
  `needs` as `[TO CONFIRM WITH CLIENT: ...]`, and a report lists assumptions (for example a loosely
  named model mapped to the closest one) so the PM can see what to check.
- **Notes are data.** They are wrapped in tags and the prompt says to ignore any instructions in them.
- **Vague amounts stay vague.** "A few million" is not turned into a number.

## Results

Run with `gemini-3.8-flash` via `python run_samples.py` (each sample succeeded on the first LLM attempt):

| Sample | Fact checks | Notes |
|---|---|---|
| 01 retiree income | 8/8 | Also extracted the horizon (`15+ years`), backed by a quote from the notes. |
| 02 growth / offshore | 9/9 | Also extracted the horizon (`10-year+`), backed by a quote. |
| 03 sparse notes | 5/5 | Did not invent an amount, income or horizon; flagged all three for the client. |
| 04 voice transcript | 8/8 | Handled spoken wording ("four and a half million", "ten years plus"). |
| **Overall** | **30/30** | |

The reference outputs leave the horizon blank for samples 01, 02 and 04, so the agent's extra
`investmentHorizon` values show up as "extra" notes in the run. Each one is grounded in a verbatim
quote from the notes, so I treated them as correct rather than fabricated.

## Limitations

- Voice notes work from a transcript only; there is no audio transcription yet.
- Prose fields (`needs`, `riskProfile`) are model-written and should be reviewed by the PM. That is
  the point of loading into the editor rather than auto-sending.
- Model selection relies on the profile descriptions in `prompt.md`. A loosely named model
  ("bespoke", "Reg 28") is mapped to the closest profile and flagged as an assumption.
- The grounding check proves a figure was in the notes; it cannot prove the notes were right.

## What I would do next

1. **Voice notes:** transcribe audio (Whisper or a hosted speech API) and feed the transcript into
   the same pipeline. Add light clean-up for fillers and spoken numbers ("four and a half million").
2. **WhatsApp:** a small webhook (Twilio sandbox) that accepts text or a voice note, runs the
   pipeline, and replies with the flags plus a link to the proposal.
3. **Real follow-up questions:** turn the `--interactive` prompt into a short back-and-forth
   (in the terminal first, then WhatsApp) that asks only for the missing details.
4. **Evaluation:** grow the sample set (messy notes, multiple clients in one note, contradictions,
   non-ZAR clients) and track fact accuracy per model and prompt change.
5. **Safeguards for production:** audit log of notes and outputs, PII handling, and a confirmation
   step before anything reaches a client.
