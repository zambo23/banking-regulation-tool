# Wiki rules

The rules the agent follows to build, query and maintain the wiki: what to cover, how binding each source is, how articles are structured, and how to cite. The tasks themselves (`compile`, query, `audit`, …) are in [workflows.md](workflows.md).

## Scope: credit risk first

The corpus covers much more than credit risk: about 2,500 documents, including AML, payments, MiCA, DORA, securities-markets rules from ESMA and the whole Basel Framework. Compile selectively.

- **Core**: the default definition, the standardised approach and IRB (PD, LGD, EAD/CCF, model governance and validation, internal models), credit risk mitigation, NPE and forbearance, provisioning (the IFRS 9 interplay and the prudential backstop), loan origination and monitoring, large exposures and concentration, counterparty credit risk, securitisation, credit-risk reporting and disclosure.
- **Context**: own funds, Pillar 2/SREP/ICAAP, internal governance, stress testing. Cover these only as far as they bear on credit risk.
- **Out of scope unless the user asks**: AML/CFT, payments, crypto-assets, operational resilience, deposit guarantee schemes, resolution, and most ESMA material (securities markets, funds, investor protection). ESMA documents on securitisation and credit rating agencies can bear on credit risk (securitisation is core; ratings feed the standardised approach).
- **Basel Framework**: CRE, LEX, the credit-risk chapters of DIS (DIS40–DIS43) and SRP32 are core; SCO, CAP, RBC and the rest of SRP are context; MAR, OPE, LEV, LCR, NSF, MGN and BCP only on request.

## Source authority

Every claim must make its legal force clear. From most to least binding:

| Level | Sources in this repo | Force |
|---|---|---|
| 1 | CRR, CRD, BRRD, … (`eurlex/`) | law |
| 2 | delegated and implementing regulations adopting RTS/ITS | law. The EBA files in `eba-rts/` and `eba-its/` are the EBA's **final drafts**; the adopted text is the regulation published in EUR-Lex |
| 3 | EBA guidelines (`eba-guidelines/`) | comply-or-explain |
| by type | EBA Single Rulebook product pages (`eba-single-rulebook/`) | the force of the document: guidelines comply-or-explain, final draft RTS/ITS as above, reports and opinions not binding. The register adds the EBA's own `phase_status` (e.g. "Applicable", "In force"), application date and compliance deadline; prefer it over `eba-guidelines/` for a guideline's status and dates |
| — | ECB supervisory guides (`ecb-guides/`) | ECB supervisory expectations for significant institutions; not law |
| — | ECB supervisory priorities (`ecb-priorities/`) | where ECB supervisors will focus over the next three years (reviews, inspections); not law and no new requirement, but they drive SREP findings and measures |
| — | EBA reports (`eba-reports/`) | analysis and benchmarking; not binding |
| — | EBA consultation papers (`eba-consultation-papers/`) | **proposals only**; never present them as rules in force |
| — | EBA other publications (`eba-other/`): work programmes, roadmaps, discussion papers, peer reviews, responses to the Commission | not binding. A work programme lists planned deliverables, not rules; a discussion paper is an early proposal |
| — | Basel Framework (`bis-basel/`) | BCBS international standards: **not EU law**. The EU applies them through the CRR/CRD, with its own choices and dates; cite the EU text for what binds an EU bank, and Basel for the international benchmark or a reform not yet transposed. A "Forthcoming" version is agreed but not yet effective |
| 3 | ESMA guidelines and recommendations (`esma/`, `doc_type` "Guidelines & Recommendations") | comply-or-explain |
| — | other ESMA documents (`esma/`): final reports, compliance tables, reference documents, consultation papers | by type: a final report may contain final draft RTS/ITS (the adopted text is in EUR-Lex) or final guidelines; a consultation paper is a proposal; compliance tables and reference documents are information |

## The wiki (`data/03-wiki`)

### Structure

The file layout is in [folder-structure.md](folder-structure.md#wiki-data03-wiki). Keep these files up to date:

- `index.md`: lists every topic wiki with a one-line description and a link (`[[irb-approach/index|IRB approach]]`). Update it whenever a topic wiki is created or its scope changes.
- `log.md`: append-only. Each entry has the date and, for every source processed, its `data/01-raw/...` path, SHA-256 (from the register) and the articles created or updated. It is how the agent knows what has already been compiled.
- `<topic>/index.md`: a 2–3 line description of the topic wiki, then every article with a one-line description and a `[[link]]`. Update it whenever an article is created, renamed or substantially changed.

Suggested starting topic wikis (create them as material arrives, not in advance):
- `regulatory-framework`, which also holds cross-cutting initiatives such as the simplification agenda
- `default-and-npe`
- `standardised-approach`
- `irb-approach`
- `credit-risk-mitigation`
- `provisioning`
- `loan-origination-and-monitoring`
- `large-exposures`
- `counterparty-credit-risk`
- `securitisation`
- `supervision-and-pillar-2`
- `esg-risks`
- `macroprudential`

Ask the user before creating a topic wiki outside this list.

### Article format

Every article has, in this order:

1. YAML frontmatter, as in the example below.
2. An H1 title.
3. An introduction of 2–4 lines.
4. `## Key points`: 3–7 dense bullets.
5. Body sections (`##`).
6. `## Related articles`: `[[wikilinks]]`.
7. `## Sources`: the sources cited, each with its pinpoint references.

```yaml
---
tags: [irb, pd, lgd]
created: 2026-10-09
updated: 2026-10-09
sources:
  - path: data/01-raw/eurlex/CRR/02013R0575-20260626.pdf
    ref: CRR, consolidated 2026-06-26
  - path: data/01-raw/eba-single-rulebook/model-validation/2017-11-20_..._v1.pdf
    ref: EBA/GL/2017/16
---
```

### Citing regulation

- Cite precisely: act plus article or paragraph (`CRR Art. 178(1)(b)`, `EBA/GL/2016/07 para. 23`). Quote short key definitions verbatim.
- Record the version a claim relies on. `sources[].path` is the exact versioned file: a CELEX consolidation date, or `_vN` and the EBA reference or `doc_id`. This is how stale content is detected later.
- Always cite the file in `data/01-raw`, even when you read its Markdown version in `data/02-raw-md`: the registers and `log.md` track the `01-raw` path and its SHA-256. Check a figure, table or formula against the PDF when the Markdown looks garbled.
- State the legal force when it isn't law (guideline, ECB expectation, draft, proposal). Give application dates and transitional periods when relevant.
- Keep regulatory terminology as the sources use it ("obligor", "unlikely to pay", "downturn LGD"). Define a technical term the first time it appears.

### Writing and linking

- Clear, dense, no filler. Use bullets and short sections where they help scanning.
- Link every concept that has an article. Link important concepts that don't have one yet too (stub links), and list them in the session summary.
- Before creating an article, search for similar ones. Prefer updating an existing article. If two articles overlap, propose a merge to the user.

## Principles

The wiki must be:

- **consistent**: same naming, structure and style everywhere;
- **self-contained**: readable without the sources;
- **densely linked**;
- **traceable**: every claim leads to a versioned source;
- **current**: stale content is flagged, never silently kept;
- **cheap to read**, for humans and LLMs alike.

When a structural choice is ambiguous (new topic wiki, merge, reorganisation), ask the user.
