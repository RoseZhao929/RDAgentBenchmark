"""Agent silver-gold annotation of the 200-case PMC-OA holdout using Opus 4.8.

Replicates the physician's task (HANDOFF v3): for each held-out case, given the
PMC full text + the Gemini-extracted final diagnosis (+ its Orphanet match) +
the Gemini-extracted HPO phenotype list, Opus 4.8 judges:
  - is the extracted diagnosis the correct final diagnosis of the case report?
  - if not, what is the correct diagnosis?
  - which of the extracted HPO terms are wrong / not supported by the text?
  - (bonus) salient HPO terms present in the text but missed by the extractor.

Output: data/pmc_oa_holdout/opus48_annotation.jsonl  (one row per pmc_id)
Columns mirror the doctor's two fields (correct_diagnosis, wrong_hpo_terms) plus
Opus confidence + rationale, so agent- vs physician-gold agreement can be scored
once the human annotation returns (Cohen's κ, pre-registered A5).

Usage:
  python3 scripts/annotate_holdout_opus48.py [--n N] [--concurrency K]
RESUME: skips pmc_ids already present in the output.
"""
from __future__ import annotations
import argparse, gzip, json, os, re, ssl, sys, time
from pathlib import Path
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
import urllib.request, urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.agents._adapter_utils import load_dotenv
load_dotenv()
try:
    import certifi
    _CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _CTX = ssl.create_default_context()

MODEL = "anthropic/claude-opus-4.8"
POOL = ROOT / "data/pmc_oa_holdout/HANDOFF_v3/candidates_full_pool.jsonl"
FULLTEXT = ROOT / "data/pmc_oa_holdout/HANDOFF_v3/pmc_fulltext"
OUT = ROOT / "data/pmc_oa_holdout/opus48_annotation.jsonl"
URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_TEXT_CHARS = 16000

_SYS = (
    "You are a board-certified clinical geneticist annotating rare-disease case "
    "reports to build a gold-standard evaluation set. You are given the full text "
    "of a published case report, plus an automated extractor's guess at (a) the "
    "final diagnosis and (b) the patient's HPO phenotype terms. Judge the extractor "
    "strictly against the text. Only mark a diagnosis wrong if the text clearly "
    "supports a different final diagnosis. Only mark an HPO term wrong if it is not "
    "supported by (or contradicts) the text. Reply with ONLY a JSON object."
)

_SCHEMA = (
    '{"diagnosis_correct": true|false, '
    '"correct_diagnosis": "<disease name if diagnosis_correct is false, else empty>", '
    '"wrong_hpo_terms": ["<extracted HPO terms not supported by the text>"], '
    '"missing_salient_hpo": ["<up to 5 salient phenotypes in text the extractor missed>"], '
    '"confidence": 1-5, '
    '"rationale": "<one or two sentences>"}'
)


def xml_to_text(pmc_id: str, fulltext_dir: Path = None) -> str:
    p = (fulltext_dir or FULLTEXT) / f"PMC{pmc_id}.xml.gz"
    if not p.exists():
        return ""
    try:
        raw = gzip.open(p, "rt", encoding="utf-8", errors="ignore").read()
    except Exception:
        return ""
    # strip tags, collapse whitespace
    txt = re.sub(r"<[^>]+>", " ", raw)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt[:MAX_TEXT_CHARS]


def call_opus(prompt: str, key: str, tries: int = 4) -> dict:
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": _SYS},
                     {"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 900,
    }).encode()
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(URL, data=body, method="POST", headers={
                "Authorization": f"Bearer {key}", "Content-Type": "application/json",
                "HTTP-Referer": "https://localhost"})
            with urllib.request.urlopen(req, timeout=120, context=_CTX) as r:
                d = json.loads(r.read().decode())
            content = d["choices"][0]["message"].get("content") or ""
            usage = d.get("usage", {})
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if not m:
                last = {"error": "no json", "raw": content[:200]}
                time.sleep(3); continue
            parsed = json.loads(m.group(0))
            parsed["_usage"] = usage
            return parsed
        except Exception as e:
            last = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
            time.sleep(5)
    return last or {"error": "unknown"}


def build_prompt(rec: str, text: str, dx: str, orpha: str, hpo: list) -> str:
    hpo_str = "; ".join(hpo) if hpo else "(none extracted)"
    return (
        f"CASE REPORT FULL TEXT (truncated):\n{text}\n\n"
        f"--- AUTOMATED EXTRACTION TO VERIFY ---\n"
        f"Extracted final diagnosis: {dx}  (mapped to Orphanet: {orpha})\n"
        f"Extracted HPO phenotype terms: {hpo_str}\n\n"
        f"Return ONLY this JSON:\n{_SCHEMA}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0, help="limit cases (0=all)")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--pool", default=str(POOL))
    ap.add_argument("--fulltext", default=str(FULLTEXT))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    key = os.environ["OPENROUTER_API_KEY"]
    ft = Path(args.fulltext)
    outp = Path(args.out)

    ids = sorted(f.name[3:].split(".")[0] for f in ft.glob("PMC*.xml.gz"))
    pool = {}
    for line in open(args.pool):
        r = json.loads(line)
        pool[str(r["pmc_id"])] = r
    cases = [(pid, pool[pid]) for pid in ids if pid in pool]
    if args.n:
        cases = cases[:args.n]

    done = set()
    if outp.exists():
        for line in open(outp):
            try:
                done.add(json.loads(line)["pmc_id"])
            except Exception:
                pass
    todo = [(pid, r) for pid, r in cases if pid not in done]
    print(f"[opus48] {len(cases)} cases, {len(done)} done, {len(todo)} to annotate "
          f"(model {MODEL}, concurrency {args.concurrency})", flush=True)

    lock = Lock()
    fout = outp.open("a")
    st = {"n": 0, "dx_wrong": 0, "err": 0, "in_tok": 0, "out_tok": 0}

    def work(item):
        pid, r = item
        text = xml_to_text(pid, ft)
        if not text:
            with lock:
                st["err"] += 1
            return
        prompt = build_prompt(pid, text, r.get("extracted_diagnosis", ""),
                              f"{r.get('orpha_id','')} {r.get('matched_orpha_name','')}",
                              r.get("hpo_phenotypes", []))
        res = call_opus(prompt, key)
        row = {
            "pmc_id": pid,
            "extracted_diagnosis": r.get("extracted_diagnosis"),
            "orpha_id": r.get("orpha_id"),
            "extracted_hpo": r.get("hpo_phenotypes", []),
            "opus_diagnosis_correct": res.get("diagnosis_correct"),
            "opus_correct_diagnosis": res.get("correct_diagnosis", ""),
            "opus_wrong_hpo_terms": res.get("wrong_hpo_terms", []),
            "opus_missing_salient_hpo": res.get("missing_salient_hpo", []),
            "opus_confidence": res.get("confidence"),
            "opus_rationale": res.get("rationale", ""),
            "error": res.get("error"),
            "annotator": MODEL,
        }
        u = res.get("_usage", {}) or {}
        with lock:
            fout.write(json.dumps(row, ensure_ascii=False) + "\n"); fout.flush()
            st["n"] += 1
            if res.get("diagnosis_correct") is False:
                st["dx_wrong"] += 1
            if res.get("error"):
                st["err"] += 1
            st["in_tok"] += u.get("prompt_tokens", 0) or 0
            st["out_tok"] += u.get("completion_tokens", 0) or 0
            if st["n"] % 10 == 0:
                print(f"  [{st['n']}/{len(todo)}] dx_wrong={st['dx_wrong']} err={st['err']} "
                      f"tok~{st['in_tok']//1000}k/{st['out_tok']//1000}k", flush=True)

    if args.concurrency <= 1:
        for it in todo:
            work(it)
    else:
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            list(ex.map(work, todo))
    fout.close()
    # rough cost (Opus 4.8 ≈ $15/M in, $75/M out)
    cost = st["in_tok"] / 1e6 * 15 + st["out_tok"] / 1e6 * 75
    print(f"[opus48] DONE: {st['n']} annotated, {st['dx_wrong']} diagnosis-wrong, "
          f"{st['err']} err. tokens in={st['in_tok']} out={st['out_tok']} ~${cost:.2f}", flush=True)
    print(f"[opus48] wrote {outp}")


if __name__ == "__main__":
    main()
