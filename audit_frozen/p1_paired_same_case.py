"""补5 — P1 true same-case paired test: gold-HPO vs extracted-HPO -> diagnosis.

The paper's 0.40 vs 0.04 headline compared LIRICAL on gold-HPO (25 Phenopacket
cases) vs extracted-HPO (25 RareArena cases) — DIFFERENT datasets, so it cannot
be read as a phenotype-extraction penalty (confounds dataset with condition).

This runs a genuine same-case paired design on ONE fixed set of Phenopacket
cases (which have gold HPO), both conditions on the same diagnoser (llm_control
= single-LLM baseline) via LiteLLM:

  Condition A (gold_hpo):     gold HPO terms  -> diagnose -> R@1
  Condition B (extracted_hpo): gold HPO -> synth vignette -> LLM re-extract HPO
                               -> diagnose -> R@1

Same cases, same backbone, same diagnoser prompt. Reports paired ΔR@1 + McNemar.
Diagnoser & extractor prompts copied from harness/agents/llm_control.py;
scoring reuses harness crossmap; ranked-list parsing reuses parse_ranked_top5.

Note: this isolates the extraction-quality effect WITHOUT LIRICAL (whose ~2GB
HPO DB is not in this slim checkout). It answers the causal question the paper's
0.40-vs-0.04 could not.
"""
from __future__ import annotations
import sys, json, os, re, time, random
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO)); os.chdir(REPO)
# orphadata path patch (crossmap needs the in-repo XML, repo hardcodes a mac path)
import harness.pmc_oa.orphanet as _orph  # noqa: E402
_LOCAL_ORPHA = str(REPO / 'data' / 'orphadata' / 'en_product1.xml')
_orph.DEFAULT_ORPHA_XML = _LOCAL_ORPHA
_orph.parse_orphadata.__defaults__ = (_LOCAL_ORPHA,)
from harness.metrics.cross_map import gold_hit_with_crossmap  # noqa: E402
from harness.agents._adapter_utils import parse_ranked_top5  # noqa: E402
from harness.ingest import ingest_phenopacket_store  # noqa: E402
from openai import OpenAI  # noqa: E402
from scipy import stats  # noqa: E402

LITELLM_BASE = 'https://litellm.dealism.ai/v1'
LITELLM_KEY = os.environ.get('LITELLM_API_KEY', '')  # set LITELLM_API_KEY in env; do NOT hardcode
MODEL = 'google/gemini-3-flash-preview'   # same family as paper's Gemini control
N_CASES = 50
SEED = 42
OUT = REPO / 'audit_frozen'
_client = OpenAI(api_key=LITELLM_KEY, base_url=LITELLM_BASE, timeout=60, max_retries=2)

# ---- prompts copied verbatim from harness/agents/llm_control.py ----
_SYSTEM_P2 = (
    "You are an expert clinical geneticist specializing in rare diseases. "
    "Given clinical findings, produce a ranked differential diagnosis as a "
    "numbered list (most likely first). Each line must be exactly '1. "
    "<Disease Name>'. Use canonical Orphanet / OMIM disease names."
)
_SYSTEM_P1 = (
    "You are a clinical phenotyping assistant. Given a case description, "
    "extract every distinct clinical phenotypic finding as a short noun "
    "phrase (e.g. 'progressive proximal muscle weakness', 'optic atrophy', "
    "'macrocephaly'). Output ONLY a numbered list, one finding per line, no "
    "commentary. Do not infer diseases."
)


def _chat(system, user, max_tokens=2500):
    for attempt in range(3):
        try:
            r = _client.chat.completions.create(
                model=MODEL, temperature=0.0, max_tokens=max_tokens,
                timeout=60,  # per-request timeout so one stalled call can't hang the run
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}])
            return r.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                return f"__ERROR__ {type(e).__name__}: {e}"
            time.sleep(2)
    return ""


def synth_vignette(hpo_labels, demo):
    """Deterministic narrative vignette from gold HPO (no LLM; mirrors the
    paper's 'synthesize vignette from HPO labels' step, kept rule-based so the
    ONLY LLM-introduced noise is in the re-extraction条件)."""
    who = "The patient"
    if demo:
        bits = []
        if demo.get('age') is not None:
            bits.append(f"{int(demo['age'])}-year-old")
        if demo.get('sex') and demo['sex'] != 'unknown':
            bits.append(demo['sex'])
        if bits:
            who = "A " + " ".join(bits) + " patient"
    findings = "; ".join(hpo_labels)
    return f"{who} presented with the following clinical findings: {findings}."


def diagnose(hpo_labels):
    """Feed HPO labels as clinical findings, get ranked top-5 diagnoses."""
    findings = "Clinical findings (HPO):\n" + "\n".join(f"- {x}" for x in hpo_labels)
    out = _chat(_SYSTEM_P2, findings)
    if out.startswith("__ERROR__"):
        return [], out
    return parse_ranked_top5(out, k=5), out


def extract_hpo(vignette):
    """LLM re-extracts phenotype phrases from a free-text vignette."""
    out = _chat(_SYSTEM_P1, vignette)
    if out.startswith("__ERROR__"):
        return [], out
    phrases = []
    for line in out.splitlines():
        m = re.match(r"\s*\d+[\.\)]\s*(.+)", line)
        if m:
            phrases.append(m.group(1).strip())
    return phrases, out


def main():
    # gold comes straight from each phenopacket case (c.gold_label); no need to
    # ingest all datasets. Same seed-42 shuffle as the paper's P5/P1 pilots.
    rng = random.Random(SEED)
    cases = list(ingest_phenopacket_store('data/phenopacket_store/notebooks'))
    rng.shuffle(cases)
    cases = cases[:N_CASES]

    rows = []
    fout = (OUT / '_p1_paired_rows.jsonl').open('w')
    print(f"P1 paired: {len(cases)} phenopacket cases, model={MODEL}", file=sys.stderr)
    for i, c in enumerate(cases):
        g = c.gold_label
        present = [t.label or t.id for t in c.gold_hpo_terms if not t.negated]
        if not present:
            continue
        demo = {'age': c.demographics.age_at_onset_years, 'sex': c.demographics.sex}

        # Condition A: gold HPO -> diagnose
        preds_a, raw_a = diagnose(present)
        hit_a = 1 if (preds_a and gold_hit_with_crossmap(preds_a[0], g)) else 0

        # Condition B: gold HPO -> synth vignette -> re-extract HPO -> diagnose
        vig = synth_vignette(present, demo)
        extracted, raw_ext = extract_hpo(vig)
        preds_b, raw_b = diagnose(extracted) if extracted else ([], "")
        hit_b = 1 if (preds_b and gold_hit_with_crossmap(preds_b[0], g)) else 0

        row = {'case_id': c.case_id, 'gold_disease': g.disease_name,
               'n_gold_hpo': len(present), 'n_extracted_hpo': len(extracted),
               'gold_hpo_hit': hit_a, 'extracted_hpo_hit': hit_b,
               'gold_top1': preds_a[:1], 'extracted_top1': preds_b[:1]}
        rows.append(row)
        fout.write(json.dumps(row) + "\n")
        print(f"  [{i+1}/{len(cases)}] {c.case_id[:26]:26s} "
              f"gold_hpo={len(present):2d} ext_hpo={len(extracted):2d} "
              f"A_hit={hit_a} B_hit={hit_b}", file=sys.stderr)
    fout.close()

    n = len(rows)
    ha = sum(r['gold_hpo_hit'] for r in rows)
    hb = sum(r['extracted_hpo_hit'] for r in rows)
    # McNemar paired
    b = sum(1 for r in rows if r['gold_hpo_hit'] and not r['extracted_hpo_hit'])  # gold-win
    cc = sum(1 for r in rows if r['extracted_hpo_hit'] and not r['gold_hpo_hit'])  # ext-win
    disc = b + cc
    chi2 = ((abs(b - cc) - 1) ** 2 / disc) if disc else None
    p = float(stats.chi2.sf(chi2, 1)) if chi2 is not None else None

    report = {
        'design': 'SAME-CASE paired: gold-HPO vs LLM-re-extracted-HPO -> same diagnoser',
        'model': MODEL, 'n_cases': n, 'seed': SEED,
        'gold_hpo_R@1': round(ha / n, 4) if n else None,
        'extracted_hpo_R@1': round(hb / n, 4) if n else None,
        'delta_pp': round((ha - hb) / n * 100, 1) if n else None,
        'mcnemar': {'gold_win': b, 'extracted_win': cc, 'discordant': disc,
                    'chi2_cc': round(chi2, 3) if chi2 is not None else None, 'p': p},
        'mean_n_gold_hpo': round(sum(r['n_gold_hpo'] for r in rows) / n, 1) if n else None,
        'mean_n_extracted_hpo': round(sum(r['n_extracted_hpo'] for r in rows) / n, 1) if n else None,
        'contrast_with_paper': 'paper 0.40(gold, 25 PP cases) vs 0.04(extracted, 25 RareArena cases) '
                               'was cross-dataset; this is the same-case control the paper lacked. '
                               'Interpretation: the true extraction penalty is (gold_R@1 - extracted_R@1) '
                               'measured on identical cases and diagnoser.',
    }
    (OUT / '_p1_paired_report.json').write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))


if __name__ == '__main__':
    main()
