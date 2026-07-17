"""Smoke test for RDMA Pillar 1 (phenotype/finding extraction from EHR text).

Exercises:
  rdma.utils.llm_client.OpenRouterLLMClient  (LLM backbone wiring)
  rdma.hporag.entity.LLMEntityExtractor      (Pillar 1 extraction entry point)

This is the minimal RDMA path that does NOT depend on the unavailable heavy
deps (sent2vec, scispacy, spacy==3.8.5, faiss, fastembed, etc.) or the
external Google-Drive embedding files. It calls OpenRouter once per text and
returns the list of phenotypic finding strings parsed from the model's JSON
output. The downstream HPO-term matcher (rdma/hpo/matcher.py) would consume
this list, but it requires the gdown embeddings and is out of scope for the
smoke test.
"""

import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path("/Users/yutianzhao/Desktop/RDAgentBenchmark")
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

assert os.environ.get("OPENROUTER_API_KEY"), "OPENROUTER_API_KEY missing in .env"

from rdma.utils.llm_client import OpenRouterLLMClient
from rdma.hporag.entity import LLMEntityExtractor

# Raw OpenRouter model ID is accepted directly thanks to the MODEL_MAPPING
# fallback (`MODEL_MAPPING.get(key, key)` at llm_client.py:704).
MODEL_ID = "google/gemini-3-flash-preview"

EHR_TEXT = (
    "The patient is a 7-year-old boy with progressive proximal muscle "
    "weakness over the past two years. Physical examination reveals "
    "bilateral calf hypertrophy and a positive Gower sign. He has "
    "difficulty climbing stairs and frequent falls. Serum creatine "
    "kinase is markedly elevated at 18,500 U/L. There is a family "
    "history of a maternal uncle who died at age 19 from a similar "
    "muscle disease."
)


def main():
    print(f"[rdma-smoke] model_id = {MODEL_ID}")
    t0 = time.time()

    llm = OpenRouterLLMClient(
        model_type=MODEL_ID,
        temperature=0.1,
    )
    print("[rdma-smoke] OpenRouterLLMClient initialized")

    extractor = LLMEntityExtractor(
        llm_client=llm,
        negation=True,
        family_history=True,  # exclude maternal-uncle findings
    )
    print("[rdma-smoke] LLMEntityExtractor initialized")

    entities = extractor.extract_entities(EHR_TEXT)
    dt = time.time() - t0

    print(f"[rdma-smoke] elapsed = {dt:.1f}s")
    print(f"[rdma-smoke] num_entities = {len(entities)}")
    for i, ent in enumerate(entities):
        print(f"  [{i}] {ent}")

    if not entities:
        print("[rdma-smoke] WARN: extractor returned an empty list "
              "(could be JSON-parse miss; see raw response upstream).")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
