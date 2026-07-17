"""H4 (complexity) + H7 (specialty clustering) via HPO organ-system axis.

Specialty axis = the 23 top-level children of HP:0000118 (Phenotypic
abnormality) in hp.obo — HPO-native, objective (no manual taxonomy).

Per case (HPO-input datasets PP-Store + RareBench), map gold HPO terms to their
top-level organ system(s):
  - H4 complexity = # distinct organ systems (single=1, oligo=2-3, multi=4+).
    H4: multi-agent scaffolds (mdagents/medagents) *underperform* the no-scaffold
    control on simple cases (overthinking) and *exceed* it on complex cases.
  - H7 specialty = the modal organ system of the case. H7: per-agent weakest
    specialties correlate across agents (Spearman >=0.6) => shared blind spots
    (dataset/ontology gap, not agent-specific).

Output: data/round2/ablations/H4_H7_specialty.md
"""
from __future__ import annotations
import json, glob, re, sys
from pathlib import Path
from collections import defaultdict, Counter
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def load_hpo_roots():
    terms={}; cur=None
    for line in open('data/hpo/hp.obo'):
        line=line.rstrip('\n')
        if line=='[Term]': cur={'parents':set(),'id':None,'name':None}
        elif cur is not None and line.startswith('id: HP:'): cur['id']=line[4:].strip()
        elif cur is not None and line.startswith('name:'): cur['name']=line[6:].strip()
        elif cur is not None and line.startswith('is_a:'):
            m=re.match(r'is_a:\s*(HP:\d+)', line)
            if m: cur['parents'].add(m.group(1))
        elif line=='' and cur is not None and cur.get('id'):
            terms[cur['id']]=cur; cur=None
    ROOT='HP:0000118'
    roots={t for t,d in terms.items() if ROOT in d['parents']}
    name={t:terms[t]['name'] for t in roots}
    # term -> set of root systems (walk ancestors)
    cache={}
    def systems(hp):
        if hp in cache: return cache[hp]
        seen=set(); stack=[hp]; found=set()
        while stack:
            x=stack.pop()
            if x in seen: continue
            seen.add(x)
            if x in roots: found.add(x)
            for p in terms.get(x,{}).get('parents',()): stack.append(p)
        cache[hp]=found; return found
    return systems, name

def short(nm): return nm.replace('Abnormality of the ','').replace('Abnormality of ','').replace('the ','')

def main():
    from harness.metrics.cross_map import gold_hit_with_crossmap, gold_hit_with_variants
    from harness.ingest import ingest_phenopacket_store, ingest_rarebench
    systems, root_name = load_hpo_roots()

    case_gold={}; case_systems={}
    def add(c):
        case_gold[c.case_id]=c.gold_label
        sysc=Counter()
        for hp in (c.gold_hpo_terms or []):
            hid = hp if isinstance(hp,str) else getattr(hp,'hpo_id',None) or getattr(hp,'id',None)
            if not hid: continue
            for s in systems(hid): sysc[s]+=1
        case_systems[c.case_id]=sysc
    for c in ingest_phenopacket_store('data/phenopacket_store/notebooks'): add(c)
    for split in ('RAMEDIS','LIRICAL','MME','HMS'):
        for c in ingest_rarebench(f'data/rarebench_hf/data_unzipped/data/{split}.jsonl',split): add(c)

    # cells: per agent use Gemini Flash N=500 (and lirical/vc for reference)
    AGENT_CELLS={
        'llm_control':[('phenopacket_store','google_gemini-3-flash-preview'),('rarebench','google_gemini-3-flash-preview')],
        'mdagents':[('phenopacket_store','google_gemini-3-flash-preview'),('rarebench','google_gemini-3-flash-preview')],
        'medagents':[('phenopacket_store','google_gemini-3-flash-preview'),('rarebench','google_gemini-3-flash-preview')],
        'deeprare':[('phenopacket_store','google_gemini-3-flash-preview'),('rarebench','google_gemini-3-flash-preview')],
        'lirical':[('phenopacket_store','lirical'),('rarebench','lirical')],
        'vc_rdagent':[('phenopacket_store','vc_rdagent'),('rarebench','vc_rdagent')],
    }
    def hits_by_case(agent):
        out={}
        for ds,bb in AGENT_CELLS[agent]:
            for p in glob.glob(f'data/round2/phase4a/predictions_{ds}_{agent}_{bb}*.jsonl'):
                best={}
                for line in open(p):
                    try: r=json.loads(line)
                    except: continue
                    cid=r.get('case_id')
                    if cid is None: continue
                    pr=best.get(cid)
                    if pr is None or (r.get('status')=='ok' and pr.get('status')!='ok'): best[cid]=r
                    elif pr.get('status')!='ok': best[cid]=r
                for r in best.values():
                    if r.get('status')!='ok': continue
                    g=case_gold.get(r['case_id'])
                    if not g: continue
                    preds=r.get('ranked_predictions',[]); variants=r.get('extra',{}).get('ranked_predictions_variants') or []
                    hit=(variants and gold_hit_with_variants(variants[0],g)) or (preds and gold_hit_with_crossmap(preds[0],g))
                    out[r['case_id']]=1 if hit else 0
        return out

    agent_hits={a:hits_by_case(a) for a in AGENT_CELLS}

    # ---- H4: complexity (# organ systems) ----
    def cbin(n): return 'single (1)' if n==1 else 'oligo (2-3)' if n<=3 else 'multi (4+)' if n>=4 else 'none'
    BINS=['single (1)','oligo (2-3)','multi (4+)']
    h4=defaultdict(lambda: defaultdict(lambda:{'n':0,'h':0}))
    for agent in ('llm_control','mdagents','medagents'):
        for cid,hit in agent_hits[agent].items():
            ns=len([s for s,c in case_systems.get(cid,{}).items()])
            if ns==0: continue
            b=cbin(ns)
            h4[agent][b]['n']+=1; h4[agent][b]['h']+=hit

    # ---- H7: modal specialty per case ----
    h7=defaultdict(lambda: defaultdict(lambda:{'n':0,'h':0}))
    for agent in AGENT_CELLS:
        for cid,hit in agent_hits[agent].items():
            sysc=case_systems.get(cid,{})
            if not sysc: continue
            spec=max(sysc.items(), key=lambda kv: kv[1])[0]
            h7[agent][spec]['n']+=1; h7[agent][spec]['h']+=hit

    md=["# H4 + H7 — Complexity & Specialty (HPO organ-system axis)","",
        f"Specialty axis = 23 top-level children of HP:0000118 (hp.obo). HPO-input layers (PP-Store + RareBench).","",
        "## H4 — Complexity (# distinct organ systems) × scaffold","",
        "H4: multi-agent underperforms control on *simple* (overthinking), exceeds on *complex*.","",
        "| Agent | single (1) | oligo (2-3) | multi (4+) |","|---|---|---|---|"]
    for agent in ('llm_control','mdagents','medagents'):
        row=[f"| `{agent}`"]
        for b in BINS:
            s=h4[agent][b]; row.append(f"{s['h']}/{s['n']}={s['h']/s['n']:.2f}" if s['n'] else "—")
        md.append(" | ".join(row)+" |")
    # H4 verdict: compare scaffold vs control delta per bin
    md.append("")
    def r1(agent,b):
        s=h4[agent][b]; return s['h']/s['n'] if s['n'] else None
    verdict=[]
    for b in BINS:
        c=r1('llm_control',b)
        for sc in ('mdagents','medagents'):
            v=r1(sc,b)
            if c is not None and v is not None:
                verdict.append(f"- {sc} − control on **{b}**: {v-c:+.2f}")
    md+= verdict
    md.append("\n**H4 reading**: if scaffold−control is negative on `single` and positive on `multi`, H4 supported.")

    md+=["","## H7 — Specialty R@1 per agent (modal organ system)","",
         "| Specialty | "+" | ".join(f"`{a}`" for a in AGENT_CELLS)+" |",
         "|---|"+"---|"*len(AGENT_CELLS)]
    allspecs=sorted({s for a in AGENT_CELLS for s in h7[a]}, key=lambda s: -sum(h7[a][s]['n'] for a in AGENT_CELLS))
    for s in allspecs:
        row=[f"| {short(root_name.get(s,s))}"]
        for a in AGENT_CELLS:
            d=h7[a][s]; row.append(f"{d['h']/d['n']:.2f}({d['n']})" if d['n']>=5 else "—")
        md.append(" | ".join(row)+" |")

    # H7 cross-agent rank correlation (Spearman) on specialties with enough n
    def spearman(a,b):
        common=[(x,y) for x,y in zip(a,b)]
        n=len(common)
        if n<3: return None
        ra=_rank([x for x,_ in common]); rb=_rank([y for _,y in common])
        ma=sum(ra)/n; mb=sum(rb)/n
        num=sum((ra[i]-ma)*(rb[i]-mb) for i in range(n))
        da=sum((ra[i]-ma)**2 for i in range(n))**.5; db=sum((rb[i]-mb)**2 for i in range(n))**.5
        return num/(da*db) if da*db else None
    def _rank(xs):
        order=sorted(range(len(xs)), key=lambda i: xs[i])
        r=[0]*len(xs)
        for pos,i in enumerate(order): r[i]=pos
        return r
    # build per-agent specialty R@1 vectors over common specialties (n>=10)
    llm_agents=['llm_control','mdagents','medagents']
    common_specs=[s for s in allspecs if all(h7[a][s]['n']>=10 for a in llm_agents)]
    md+=["","## H7 — cross-agent weak-specialty correlation (Spearman ρ)","",
         f"Over {len(common_specs)} specialties with n≥10 in all of {llm_agents}:",""]
    if len(common_specs)>=3:
        vecs={a:[h7[a][s]['h']/h7[a][s]['n'] for s in common_specs] for a in llm_agents}
        md.append("| pair | Spearman ρ |"); md.append("|---|---|")
        for i in range(len(llm_agents)):
            for j in range(i+1,len(llm_agents)):
                rho=spearman(vecs[llm_agents[i]], vecs[llm_agents[j]])
                md.append(f"| {llm_agents[i]} vs {llm_agents[j]} | {rho:.2f} |" if rho is not None else "| - | n/a |")
        md.append("\n**H7 reading**: ρ≥0.6 => shared blind spots (ontology/data gap, not agent-specific).")
    else:
        md.append("(insufficient common specialties with n≥10)")

    Path('data/round2/ablations/H4_H7_specialty.md').write_text("\n".join(md))
    print("Wrote H4_H7_specialty.md")
    print("\n".join(md))

if __name__=='__main__':
    main()
