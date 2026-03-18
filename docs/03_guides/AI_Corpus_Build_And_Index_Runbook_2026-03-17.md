# AI Corpus Build and Index Runbook -- 2026-03-17

**Author:** Codex (GPT-5)
**Timestamp:** 2026-03-17 18:42:14 -06:00
**Purpose:** Give another AI a precise, bounded task for building a realistic
large source corpus and indexing it with HybridRAG3 / HybridRAG3_Educational.

---

## Paste-Ready Prompt For Another AI

Use this as the prompt:

```text
You are responsible for building a large realistic HybridRAG source corpus and indexing it.

Repo:
- D:\HybridRAG3_Educational

Goal:
- Build about 500 GB of source material that resembles a real mixed enterprise workload.
- Split the corpus across these role domains:
  1. engineering docs
  2. logistics analyst docs
  3. program management docs
  4. autocad docs
  5. cyber security docs
  6. system administrator docs
  7. field engineer docs

Hard rules:
- Work only in the educational repo / sanitized workload.
- Do not mix personal/private data into this corpus.
- Prefer public, redistributable, professionally structured source material.
- Keep a manifest of every dataset/source URL you use.
- Log what you downloaded, where you stored it, and approximate size by domain.
- Keep test/demo/eval artifacts out of the serving source folder.
- If you create helper scripts, keep them inside D:\HybridRAG3_Educational\tools or docs.
- Before indexing, run a quick QC pass so obvious junk does not enter the live index.

Target layout:
- D:\RAG Source Data\Engineering
- D:\RAG Source Data\Logistics_Analyst
- D:\RAG Source Data\Program_Management
- D:\RAG Source Data\AutoCAD
- D:\RAG Source Data\Cyber_Security
- D:\RAG Source Data\Systems_Administrator
- D:\RAG Source Data\Field_Engineer
- D:\RAG Source Data\_MANIFEST

Desired mix by domain:
- PDFs, DOCX, HTML exports, TXT, MD, RST/TXT docs, spreadsheets if already supported
- vendor manuals
- standards/guides
- operations procedures
- engineering/design references
- deployment / maintenance manuals
- compliance / security guidance
- runbooks / troubleshooting guides
- project/program planning templates and governance docs

Avoid:
- toy examples
- trap docs
- testing packs
- golden seeds
- random temp files
- duplicate zip bundles inside the source folder unless there is a real reason

Acquisition requirements:
- Use domain-focused public sources.
- Prefer official docs, manuals, public handbooks, public standards guidance, and vendor knowledge bases.
- Download enough volume to approach 500 GB total.
- Keep a running size table by domain and overall total.
- Deduplicate obvious duplicates where practical.

Before indexing:
1. Write/update a manifest file under D:\RAG Source Data\_MANIFEST with:
   - domain
   - source URL or origin
   - local folder
   - estimated size
   - notes
2. Run the repo QC tooling against the chosen source folder if available.
3. Make sure the serving source folder does not include:
   - Testing_Addon_Pack
   - golden_seeds_*
   - temp/demo docs
   - pipeline smoke docs

Indexing:
1. Point the repo config/runtime paths at the chosen source folder, DB path, and embeddings cache.
2. Run indexing with the HybridRAG repo tooling.
3. After indexing, run:
   - tools/refresh_source_quality.py
   - tools/index_qc.py
4. Record:
   - chunk count
   - source count
   - total DB size
   - embeddings cache size
   - source_quality refresh stats
   - contamination/QC findings

Validation:
- Run at least 10 realistic retrieval probes across the 7 domains.
- Report the top hits and whether they look relevant.
- Flag contamination or dominance problems by domain.

Deliverables:
- the populated source folder
- manifest files
- indexing command(s) used
- QC report
- refresh-source-quality report
- retrieval probe report

Do not stop at download only. Complete the workflow through indexing and validation.
```

---

## Operator Notes

- For this workload, better realism comes from breadth plus structure, not from
  mixing everything into one flat directory.
- A role-split source tree will make later collection/index partitioning easier.
- After indexing, run:

```text
python tools/refresh_source_quality.py --db "D:\RAG Indexed Data\hybridrag.sqlite3"
python tools/index_qc.py
```

- If retrieval still looks noisy after indexing, the next lever is corpus
  separation or collection scoping, not more prompt tuning.
