# How to build knowledge on a credit risk topic

This guide shows how to use the tool to cover a credit risk topic end to end, from downloading the sources to asking questions and keeping the answers current. It uses two examples: **Definition of default** (already compiled) and **Collateral valuation** (not yet compiled).

The tool has two halves:

- **Python scripts** (`src/`) download official texts and track their versions in Excel registers (`data/00-source/`).
- **An AI agent**, such as Claude Code, reads those texts and writes an interlinked Markdown wiki (`data/02-wiki/`), following the rules in [`AGENTS.md`](../AGENTS.md).

You decide what matters and ask the questions; the agent does the reading, writing, citing and bookkeeping.

```text
1. Refresh sources ─► 2. Scope the topic ─► 3. Compile ─► 4. Review
        ▲                                                       │
        └──────────── 6. Keep current ◄──── 5. Ask questions ◄──┘
```

## Before you start

- Install the dependencies: `pip install -r requirements.txt`. Install `pdftotext` (poppler) too; the agent uses it to read PDFs.
- Start your agent from the repository root so it picks up `AGENTS.md`. Claude Code reads it through `CLAUDE.md`.
- `data/` is not in git. Back it up separately if the wiki matters to you.

## Step 1: Refresh the sources

Run the download scripts, or ask the agent to run them. Each run downloads only what is new or changed; old versions are kept.

```bash
python src/download_isrb.py                          # CRR, CRD, BRRD, … (current EUR-Lex consolidated texts)
python src/download_eba_publications.py guidelines
python src/download_eba_publications.py rts
python src/download_eba_publications.py its
python src/download_eba_publications.py reports      # several minutes
python src/download_eba_publications.py cp           # several minutes
python src/download_ecb_guides.py
```

Add `--check` to see what would change without downloading anything.

## Step 2: Scope the topic

This is the step that most affects quality. A topic is usually spread across several layers of rules, and the corpus has about 1,400 documents, most of them unrelated to your topic. Ask the agent for a **source plan before it compiles anything**:

> Propose the sources for "Collateral valuation": which CRR articles, EBA guidelines, RTS, reports and ECB guide chapters. Flag gaps and anything you would skip. Don't compile yet.

Then check the plan against these points:

| Check | Why |
| --- | --- |
| Every **layer** is present: CRR articles → RTS/ITS → EBA guidelines → ECB expectations | A topic covered only by guidelines, without the CRR articles behind them, misleads |
| Only **parts** of big texts are used: the relevant CRR articles, the relevant chapter of an ECB guide | Keeps the compile focused and the log precise |
| **Consultation papers** only where no final text exists | They are proposals, not rules |
| **Superseded editions** are left out unless you want history | The registers mark them, e.g. `edition_status=superseded` for ECB guides |
| **False positives** are dropped | A title search for "valuation" also finds prudent valuation and credit valuation adjustment, which are market-risk topics |
| **Gaps** are listed | Some key texts are not in the corpus. See [Handling gaps](#handling-gaps) |

### Example plans

**Definition of default** (compiled on 2026-10-09; see `data/02-wiki/default-and-npe/`):

| Layer | Sources |
| --- | --- |
| Law | CRR Art. 178, plus Art. 127 (standardised-approach exposures in default) and Art. 47a (non-performing exposures) |
| Guidelines | EBA/GL/2016/07, and EBA/GL/2026/05 amending it |
| ECB | ECB guide to internal models, Part B "Definition of default" |
| Skipped | consultation papers (superseded by final texts); 2014–2016 benchmarking and QIS reports (historical) |
| Gaps | the materiality-threshold RTS and the ECB Regulation on the threshold; EBA Q&A |

**Collateral valuation** (proposal, not yet compiled):

| Layer | Candidate sources |
| --- | --- |
| Law | CRR Art. 194 (eligibility principles for credit risk mitigation), Art. 207 (financial collateral), Art. 208 (immovable property collateral), Art. 229 (valuation of other eligible collateral) |
| RTS / guidelines | EBA/GL/2025/03 (ADC exposures to residential property under CRR3); EBA/RTS/2025/05 (unfinished property) |
| Reports | EBA Report on the CRM framework (2018) |
| ECB | ECB guide to internal models: the LGD chapter, for how collateral enters LGD estimates |
| Proposals | EBA/CP/2019/04: Section 7 covers the valuation of immovable and movable property. Use it only as context |
| Skip | prudent valuation (RTS 2020/04, CP 2014/38), credit valuation adjustment (CVA) and additional collateral outflows: they share words with the topic but not its subject |
| Gap | the final EBA Guidelines on loan origination and monitoring are not in the registers, only the 2019 consultation paper |

## Step 3: Compile

Give the agent the topic and, ideally, the approved plan:

> compile "Collateral valuation" using the plan above, excluding the consultation paper except as context

The agent then works through `AGENTS.md` → *Workflows* → `compile <scope>`:

1. Reads each source in full, or the agreed parts.
2. Creates or updates articles in the right topic wiki, for example `credit-risk-mitigation/`. It asks before creating a topic wiki that isn't in the suggested list.
3. Cites every claim to a pinpoint (`CRR Art. 208(3)`, `EBA/GL/2016/07 para. 51`) and records the exact file version in each article's frontmatter.
4. Updates the topic `index.md`, the top-level `index.md` and `log.md` (source paths and checksums).
5. Never touches `data/01-raw`.

It ends with a summary: sources used and skipped, articles created and updated, stub links, and open questions. A topic of this size takes one session.

## Step 4: Review

Spend ten minutes on these checks before relying on the result:

- **Legal force is explicit.** Law, comply-or-explain guidelines, ECB expectations and proposals must be distinguishable in every article.
- **Dates are right.** Look for application dates and transitional regimes. For example, the definition-of-default amendments apply from 19 October 2026, so the articles state both regimes until then.
- **Spot-check two or three citations** against the source PDF. The paths are in each article's frontmatter.
- **Stubs and gaps.** The summary lists linked-but-missing articles and sources missing from the corpus. Decide what to compile next.
- **The log** (`data/02-wiki/log.md`) shows exactly what was read. "Partial" means other parts of the same document are still available for other topics.

To fix something, tell the agent what's wrong and where; it updates the article and the `updated` date.

## Step 5: Ask questions

Ask in plain language. The agent answers from the wiki (index → topic index → articles) with links and citations:

- *When can a forborne exposure return to non-defaulted status, and how does that differ from the NPE exit rules?*
- *What valuation and revaluation frequency does the CRR require for residential property collateral?*
- *Compare the ECB and EBA expectations on the use of external data for default identification.*

- **If the wiki can't answer**, the agent says so and suggests sources to compile. That's your next compile scope.
- **Saving answers**: one-off analyses go to `data/03-output/`. Answers with lasting value can become wiki articles; the agent asks first.
- **Check the date**: answers reflect the source versions in the articles. Run Step 6 if they might be out of date.

## Step 6: Keep it current

1. **Refresh** the sources (Step 1), for example weekly or before important work.
2. **Audit**: ask the agent to `audit`. It reports:
   - articles whose sources are now outdated: a newer file version, a new CRR consolidation, a superseded ECB edition, a later EBA document with the same reference, or a document no longer listed;
   - sources changed since they were compiled;
   - duplicates, broken links and contradictions.
3. **Recompile** what the audit flags:

   > recompile the articles that rely on the old CRR consolidation

   The agent proposes changes and waits for your approval before merging, deleting or reorganising anything.

Also re-read time-sensitive passages after their key dates. The compile log notes them, for example "after 2026-10-19, revise the wording to the present tense".

## Handling gaps

Some relevant texts are not downloaded:

- Commission Delegated and Implementing Regulations (adopted RTS/ITS);
- ECB Regulations;
- the EBA Q&A;
- EBA documents missing from the publications listing.

Don't copy files into `data/01-raw` by hand: the registers wouldn't know them and audits would miss their updates. Instead:

- **Extend the download scripts** to cover the missing source. Ask the agent, for example: "add Commission Delegated Regulations adopting the CRR RTS to the EUR-Lex downloader".
- **Work around it for now**: the agent can cite a requirement through a source that reports it. For example, the ECB materiality threshold is cited via the ECB guide to internal models, and the article says so.

## Prompt cheat sheet

| Goal | Prompt |
| --- | --- |
| Plan | `Propose sources for "<topic>"; flag gaps; don't compile yet.` |
| Compile | `compile "<topic>"`, or `compile <file paths / register filter>` |
| Narrow | `compile only CRR Art. 192–241 for credit-risk-mitigation` |
| Ask | any question; add "cite the sources" for pinpoint references |
| Save | `save this answer to output` / `turn this into a wiki article` |
| Check | `audit` |
| Fill gaps | `compile the stubs in default-and-npe` |
| Explore | `which credit risk topics are covered, and which stubs are most linked?` |
