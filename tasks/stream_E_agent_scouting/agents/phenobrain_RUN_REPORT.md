# PhenoBrain Run Report (v1 Smoke Test)

**Date:** 2026-05-11
**Repo path:** `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/phenobrain/`
**Status:** **BLOCKED for v1 smoke test.** Both viable shortcuts are currently unavailable.

---

## Summary of Attempts

| Path | Result | Reason |
|---|---|---|
| 1. Docker build (recommended by scouting report) | **Cannot attempt** | Docker not installed on host. |
| 2. Native install (Python 3.6.12 + TF 1.14 + 14 GB checkpoint) | **Not attempted** | 75 min budget — explicit instruction not to download 14 GB; also Python 3.6.12 is no longer available via system pyenv/conda channels without conda. |
| 3. Tsinghua REST API fallback | **Down (502 Bad Gateway)** | Server-side outage at `http://www.phenobrain.cs.tsinghua.edu.cn/`. |

So the v1 smoke test for PhenoBrain is blocked on **infra** (no Docker, hosted API offline, 14 GB checkpoint not staged) rather than on code/repo correctness.

---

## 1. Docker Availability

```bash
$ docker --version
zsh: command not found: docker
```

Docker is **not installed** on this host. Per task constraints we do not `brew install` it. To unblock the Dockerfile path the user must:

1. Install Docker Desktop for macOS (Apple Silicon build).
2. Edit `agents/phenobrain/Docker/condarc.txt` to swap Tsinghua conda mirrors -> default channels (we are outside CN). The scouting report flagged this.
3. `cd agents/phenobrain/Docker && docker build -t phenobrain:1.0 .` — first build ~10–15 min.
4. Run with the checkpoints mounted: `docker run -v $CKPT_DIR:/codes/core ...` (exact mount mirrors README Module 2).

## 2. 14 GB Google Drive Checkpoint — Download Instructions for User

**Not started** (per task constraints — must not block on multi-hour downloads).

**Source:** https://drive.google.com/drive/folders/1cVApHHw5yLLoLRYZht9Qx52AienJlgWN (verified reachable, HTTP/2 200 on a `curl -I` at 2026-05-11 21:24 local).

**Target path on this host:**
```
/Users/yutianzhao/Desktop/RDAgentBenchmark/data/phenobrain_checkpoints/
```
(Disk has 288 GB free; full 14 GB or 4 GB subset both fit comfortably.)

**Recommended subset (saves 10 GB):** Only download the 5 ensemble model folders, per README Module 2:

- `ICTODQAcrossModel/` (IC-weighted term overlap, the strongest single similarity model)
- `HPOICCalculator/` (IC weights used by ICTO)
- `HPOProbMNBNModel/` (HPO-prior Multinomial NB / PPO)
- `LRNeuronModel/` (logistic-regression neuron / MLP-M)
- `CNBModel/` (Complement Naive Bayes)

Total subset size ~4 GB. Skipping the other 10 GB drops the 12 comparison baselines (MICA, Lin, JC, SimGIC, BOQA, GDDP, RBP, RDD, etc.) — we don't need them for our benchmark.

**Suggested commands (user to run):**
```bash
mkdir -p /Users/yutianzhao/Desktop/RDAgentBenchmark/data/phenobrain_checkpoints
cd /Users/yutianzhao/Desktop/RDAgentBenchmark/data/phenobrain_checkpoints

# Option A: gdown (subset; if Google Drive allows folder-level download)
pip install --user gdown
gdown --folder "https://drive.google.com/drive/folders/1cVApHHw5yLLoLRYZht9Qx52AienJlgWN" \
      --remaining-ok

# Option B: rclone (more reliable for large folders, supports resume)
# brew install rclone; rclone config (add a Google Drive remote); then:
# rclone copy gdrive:1cVApHHw5yLLoLRYZht9Qx52AienJlgWN ./ -P
```
Expected wall time on a residential connection: ~1.5–3 h for the full 14 GB; ~30–60 min for the 4 GB subset.

Once downloaded:
- Place the 5 folders under `agents/phenobrain/codes/core/` (the README is explicit about this).
- Compute SHA-256 for each folder and store in `data/phenobrain_checkpoints/SHASUMS` for reproducibility — Google Drive has been known to silently drop shared folders.

Additionally, three **ALBERT/BERT base models** are needed only for the *phenotype-extraction* pillar (HPO tagging from free Chinese clinical text):
- `bert_syn_project/model/bert` (Google BERT base)
- `bert_syn_project/model/albert_google` (Google ALBERT base)
- `bert_syn_project/model/albert_brightmart` (Chinese ALBERT by brightmart)

These are *not* required if we feed PhenoBrain pre-extracted HPO lists (Pillar 2 / 3 in our methods doc), which is the default for our benchmark.

## 3. Tsinghua REST API Fallback — Currently Down

The scouting report identified the hosted REST API at `http://www.phenobrain.cs.tsinghua.edu.cn/` as a checkpoint-free shortcut. I tested four endpoints from this host on 2026-05-11 ~21:23 local:

| Endpoint | HTTP status |
|---|---|
| `GET /hpo-tree-init` | **502 Bad Gateway** |
| `GET /predict?model=Ensemble&hpoList[]=...` (the canonical predict call) | **502 Bad Gateway** |
| `GET /predict?model=ICTO%20%28A%29&hpoList[]=...` | **502 Bad Gateway** |
| `HEAD /pc` (web UI) | **502 Bad Gateway** |
| HTTPS variant of the above | **502 Bad Gateway** (after TLS handshake) |

All four return 502 from the reverse proxy with `Content-Length: 0`. This is a server-side outage at `cs.tsinghua.edu.cn`, not a network issue on our end (HTTPS connect succeeds, TLS handshake completes). The HTTP connection itself is alive — only the upstream PhenoBrain service is down.

**Implication for v1:** the REST API is not a reliable shortcut for our benchmark even on better days — it is community-hosted, has a `TASK_ID`-based async queue with no SLA, and is currently fully unavailable. We should plan around it.

**Action item for user:** ping cs.tsinghua.edu.cn / phenobrain maintainers via the contact in the npj Digital Medicine paper or via GitHub issue on `xiaohaomao/timgroup_disease_diagnosis` to confirm uptime expectations before we commit to using their hosted service in the paper's reproducibility plan.

## 4. Repo-Local Sanity Checks (Free)

These I *did* perform without install / downloads — they confirm the repo is structurally OK:

- `Public_Test_set.json` loads cleanly. Format: `list` of 873 samples, each `[[HP:..., HP:...], [OMIM:.../ORPHA:...]]` — **identical to RareBench**, drop-in compatible with our harness.
- `codes/requirements.txt` confirms the 63-package legacy pin (numpy 1.19.2, pandas 1.1.3, TF 1.14 implied transitively, transformers 4.18, scikit-learn 0.21.3, etc.).
- `Docker/Dockerfile` confirms base image `continuumio/anaconda3:2024.02-1`, conda env `phenobrain` on Python 3.6.12, Java OpenJDK 1.8 (`openjdk.deb` is *shipped in-tree*, ~38 MB — nice surprise, no extra Java download needed). Conda mirror is Tsinghua; needs swap for use outside CN.
- `LICENSE` confirms Apache-2.0 (good for paper).
- `PhenoBrain_Web_API/README.md` documents 11 endpoints; schema is well-specified; our adapter can be a thin layer once the service is back up.

## 5. Blocking Description (Concise)

PhenoBrain v1 smoke test is blocked on **three independent issues**, any one of which would block alone:

1. **Docker not installed** on host -> the only sanctioned install path (Python 3.6.12 + TF 1.14) is not buildable today.
2. **14 GB checkpoint** sits on Google Drive; cannot be downloaded inside this 75 min budget without blocking the agent on hours of transfer. Even with the 4 GB subset, this is at least 30 min of download time.
3. **Tsinghua REST API** returns 502 across all endpoints — currently down, so it cannot serve as the no-install fallback the scouting report assumed.

Removing **any one** of these unblocks the others (e.g. if the REST API came back up, we could smoke-test today with zero install / zero download).

## 6. Recommended Path Forward (User Decision Points)

| Decision | Effort | Outcome |
|---|---|---|
| (a) Install Docker + download 4 GB subset + build image | ~3 h wall-clock | Full local smoke test on `Public_Test_set.json` — long-term right answer. |
| (b) Wait for Tsinghua REST API to come back up, then run via API | ~0 effort once up | Zero-install smoke test path; depends on community service uptime. |
| (c) Mirror the 14 GB Google Drive to lab S3 today (per scouting report Next-Step #1) | ~3 h transfer (background) | Insures us against Drive folder vanishing; pre-stages (a). |
| (d) Drop PhenoBrain, swap to LIRICAL (Java, already in RareBench) | minimal | Loses the Chinese-clinical-text angle but the lineup remains intact. |

The scouting-report recommendation is (a)+(c). I agree — combine them: kick off (c) in the background tonight, then build the Docker image with the checkpoints already mounted tomorrow. (b) is not reliable enough to depend on.

## 7. Open Risk

Confirming the scouting report's MEDIUM-risk rating:

- **The hosted API being down today is the first concrete instance of the "single point of failure" risk** flagged in the scouting report (last commit Nov 2024, no recent maintenance signal).
- We should treat (a) — full local install with mirrored checkpoints — as the **only** durable path to a PhenoBrain result, and budget that time explicitly into the v1 plan.

## Files Touched

None on the PhenoBrain repo itself. No virtualenv, no downloads. The repo is in its as-cloned state.

## Open Issues to Flag for User

1. **Docker install needed** if we want PhenoBrain in v1. Estimated time once docker is in place: 1 h for image build, 30 min for checkpoint download (4 GB subset), 30 min for the first end-to-end smoke run.
2. **Mirror the Google Drive folder** to lab S3 *today* — the scouting report flagged this as Next-Step #1, and the current Tsinghua API outage reinforces that we cannot count on upstream stability.
3. **Email PhenoBrain authors** (xiaohaomao at github / cs.tsinghua) to (a) confirm the API outage is temporary and (b) ask whether they will keep the hosted service alive through 2026.
