"""Check the connection to the model service.  Run:  python check_llm.py
Prints what the service answers. Never prints your key."""
import os
from pathlib import Path

import httpx


def load_env(path=".env"):
    p = Path(path)
    if not p.exists():
        print("WARNING: no .env file found in this folder.")
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
key = os.getenv("LLM_API_KEY") or ""
base = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")
model = os.getenv("LLM_MODEL", "gemini-3.8-flash")
print("Base URL :", base)
print("Model    :", model)
print("Key      :", f"set ({len(key)} characters)" if key else "MISSING")

try:
    r = httpx.post(
        base + "/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "user", "content": "Reply with the single word: ready"}]},
        timeout=60,
    )
except Exception as exc:
    raise SystemExit(f"\nCould not connect: {type(exc).__name__} - {exc}")

print("\nstatus      :", r.status_code)
print("content-type:", r.headers.get("content-type"))
print("body        :", r.text[:400].replace("\n", " "))
if r.status_code == 200 and "choices" in r.text:
    print("\nRESULT: OK - the model service works.")
elif r.status_code in (401, 403):
    print("\nRESULT: key rejected (wrong, expired or not allowed).")
elif r.status_code == 404:
    print("\nRESULT: URL or model name not found - model names change; check the provider's current list.")
else:
    print("\nRESULT: unexpected answer - send everything above to your support person.")
