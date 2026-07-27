"""Filter the MIMIC note eval subset to drop 'prior/known diagnosis' cases.

Problem this addresses
----------------------
The v1 evaluable subset (E-mapping, rare, principal, note) still mixes two
clinically different situations:

* genuine diagnostic reasoning — the rare disease is worked up during THIS
  admission from an undifferentiated presentation (e.g. fatigue -> babesiosis);
* prior/known disease — the patient is admitted for a complication or routine
  follow-up of an ALREADY-diagnosed rare disease, and the note states it as
  history ("history of pituitary adenoma s/p resection", "hx NMO on
  rituximab"). Here the diagnosis is not inferred; it is asserted as history.

The second kind is a soft leak: not the verbatim gold name (that is masked),
but a "history of <disease>" structure that hands the answer to the model.

Rule-based detection (no LLM)
-----------------------------
For cases where the gold name occurred verbatim before masking, we inspect a
window around each ``[MASKED_DIAGNOSIS]`` token for history cues
(history of / hx / known / s/p / diagnosed with / on <disease-specific drug> /
follow-up ...). If any mask token sits in such a context, the case is flagged
``prior_known`` and dropped from the conservative subset.

Honest limitation
------------------
Cases whose gold name never appeared verbatim (it was never in the kept text)
cannot be judged this way: the note may still *imply* a prior diagnosis in
paraphrase. Those are marked ``history_undeterminable=true`` and KEPT, but the
manifest reports their count so the residual uncertainty is explicit. Precisely
separating them needs an LLM or human read (out of scope here).

No LLM calls. No fabrication. Deterministic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

HIST_PRE = re.compile(
    r"(?i)(history of|hx of|\bhx\b|\bh/o\b|known|s/p|status[- ]post|established|"
    r"chronic|underlying|diagnosed with|carries a? diagnosis|"
    r"past medical history|\bpmh\b)[^.]{0,40}$"
)
HIST_POST = re.compile(
    r"(?i)^[^.]{0,40}(diagnosed|\bdx\b|resection|s/p|"
    r"on (ivig|rituximab|chemo|chemotherapy|treatment|therapy|infusions)|"
    r"followup|follow-up|\bf/u\b)"
)
MASK = "[MASKED_DIAGNOSIS]"


def is_prior_known(model_input: str) -> bool:
    for m in re.finditer(re.escape(MASK), model_input):
        pre = model_input[max(0, m.start() - 45) : m.start()]
        post = model_input[m.end() : m.end() + 45]
        if HIST_PRE.search(pre) or HIST_POST.search(post):
            return True
    return False


def build(in_path: Path, out_path: Path | None) -> dict[str, Any]:
    rows = [json.loads(l) for l in in_path.open() if l.strip()]
    kept: list[dict] = []
    n_prior = 0
    n_undet = 0
    digest = hashlib.sha256()
    for r in rows:
        had_verbatim = r.get("gold_name_verbatim_hits_before_mask", 0) > 0
        prior = is_prior_known(r["model_input"]) if had_verbatim else False
        undeterminable = not had_verbatim
        r["prior_known_flag"] = prior
        r["history_undeterminable"] = undeterminable
        r["task_version"] = "mimic-note-eval-subset-v2"
        if prior:
            n_prior += 1
            continue  # drop from conservative subset
        if undeterminable:
            n_undet += 1
        kept.append(r)

    writer = out_path.open("w") if out_path else None
    try:
        for r in kept:
            line = json.dumps(r, ensure_ascii=False)
            digest.update(line.encode("utf-8"))
            if writer:
                writer.write(line + "\n")
    finally:
        if writer:
            writer.close()

    dz = Counter(r["evaluation_only"]["gold_orpha"] for r in kept)
    names = {r["evaluation_only"]["gold_orpha"]: r["evaluation_only"]["gold_disease"] for r in kept}
    return {
        "input_n": len(rows),
        "dropped_prior_known": n_prior,
        "n_final": len(kept),
        "n_distinct_diseases": len(dz),
        "kept_history_undeterminable": n_undet,
        "note": (
            f"{n_undet} kept cases had no verbatim gold occurrence, so a "
            "rule-based prior-history check cannot confirm they are genuine "
            "work-ups; they may still imply a known diagnosis in paraphrase. "
            "Separating these requires an LLM/human read."
        ),
        "top_diseases": [
            {"orpha": o, "name": names[o], "n": n} for o, n in dz.most_common(12)
        ],
        "output": str(out_path) if out_path else None,
        "output_sha256": digest.hexdigest(),
        "task_version": "mimic-note-eval-subset-v2",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--input",
        type=Path,
        default=Path("data/mimic_iv_rd_slice/note_eval_subset_v1.jsonl"),
    )
    p.add_argument(
        "--output",
        type=Path,
        help="Credentialed JSONL output (keep under gitignored data/).",
    )
    args = p.parse_args()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
    print(json.dumps(build(args.input, args.output), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
