from __future__ import annotations
import json
import sys
import httpx

OLLAMA = "http://127.0.0.1:11434"

def main() -> int:
    c = httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0), proxy=None, trust_env=False)
    try:
        tags = c.get(f"{OLLAMA}/api/tags")
        tags.raise_for_status()
        data = tags.json()
        models = [m.get("name") for m in data.get("models", [])]
        print("OLLAMA_MODELS:", models)

        # pick mistral if available, else fail with clear message
        mistral = None
        for cand in ("mistral:7b", "mistral-nemo:12b", "mistral:latest", "mistral"):
            if cand in models:
                mistral = cand
                break
        if not mistral:
            print("FAIL: No mistral model tag found in ollama /api/tags", file=sys.stderr)
            return 2

        # generate test
        r = c.post(f"{OLLAMA}/api/generate", json={"model": mistral, "prompt": "Say OK", "stream": False})
        r.raise_for_status()
        print("MISTRAL_GENERATE_OK:", r.json().get("response", "")[:80])

        # embeddings test (required for Data menu)
        emb_model = "nomic-embed-text:latest"
        r2 = c.post(f"{OLLAMA}/api/embeddings", json={"model": emb_model, "prompt": "hello"})
        r2.raise_for_status()
        j = r2.json()
        vec = j.get("embedding")
        if not vec or not isinstance(vec, list):
            print("FAIL: embeddings missing/invalid", file=sys.stderr)
            return 3
        print("EMBEDDINGS_OK: dim=", len(vec))
        return 0
    finally:
        c.close()

if __name__ == "__main__":
    raise SystemExit(main())
