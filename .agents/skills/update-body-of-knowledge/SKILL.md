---
name: update-body-of-knowledge
description: Regulatory watch and wiki refresh for EU banking regulation, focused on credit risk. Checks the EBA, ECB Banking Supervision, EUR-Lex, BIS and ESMA RSS feeds and the download registers, writes a dated report to data/03-output/reg-watch/, and, after the user confirms, downloads the new sources and compiles them into the wiki. Use when the user asks for regulatory updates, what's new, a weekly check, or to refresh/update the body of knowledge. Arguments - quick | from <YYYY-MM-DD> | client "<description>" | html.
---

# Update the body of knowledge

Find what has changed in EU banking regulation since the last check, say what matters for credit risk and which wiki articles and sources are affected, then, once the user confirms, bring the sources and the wiki up to date.

Follow `AGENTS.md` throughout, in particular *Scope: credit risk first*, *Source authority*, *Citing regulation* and the `compile` and `audit` workflows.

The run has two phases. **Phase 1 changes nothing** outside `data/03-output/reg-watch/`. **Phase 2 runs only after the user explicitly confirms** which proposed actions to take.

## Arguments

| Argument | Effect |
|---|---|
| *(none)* | Full Phase 1, Markdown report, then ask about Phase 2 |
| `quick` | Step 1 only; report in the chat, save nothing, don't update `last-check.txt` |
| `from <YYYY-MM-DD>` | Use this start date instead of `last-check.txt` |
| `client "<description>"` | Add an "Impact on client" column; keep ESMA and the Central Bank of Ireland in scope when relevant to the client |
| `html` | Save the report as `.html` instead of `.md` (self-contained, printable) |

## Period

- **From**: the `from` argument; otherwise the date in `data/03-output/reg-watch/last-check.txt`; otherwise 14 days ago.
- **To**: today.

## Phase 1: watch and report

### Step 1: Feeds (RSS where available)

Fetch these feeds and keep the items published in the period. The URLs were tested on 2026-10-09.

| Source | Feed |
|---|---|
| EBA (news + "EBA E-mail alert" digests) | https://www.eba.europa.eu/rss.xml |
| ECB Banking Supervision: publications | https://www.bankingsupervision.europa.eu/rss/pub.html |
| ECB Banking Supervision: press | https://www.bankingsupervision.europa.eu/rss/press.html |
| EUR-Lex: Parliament and Council legislation | https://eur-lex.europa.eu/EN/display-feed.rss?rssId=162 |
| EUR-Lex: acts of the Official Journal L (delegated and implementing regulations) | https://eur-lex.europa.eu/EN/display-feed.rss?rssId=165 |
| EUR-Lex: Commission proposals | https://eur-lex.europa.eu/EN/display-feed.rss?rssId=161 |
| BIS media releases (Basel Committee) | https://www.bis.org/doclist/all_pressrels.rss |
| ESMA (only for crowdfunding, securitisation, or a client that needs it) | https://www.esma.europa.eu/rss.xml |

- The EBA feed is short and mixes news with "EBA E-mail alert" digests. Open each digest in the period and list the publications it announces.
- The EUR-Lex feeds hold only the latest 100 items, and the OJ L feed is mostly unrelated acts. Keep only acts that amend or supplement the CRR (575/2013), the CRD (2013/36/EU), the BRRD, DORA (2022/2554) or another act in `data/00-source/isrb_documents.xlsx`, or that adopt EBA RTS/ITS. If the period is longer than the feed covers, say so and use the SPARQL approach in `src/download_isrb.py` for legislation.
- Don't scrape `eur-lex.europa.eu` HTML pages: they return a WAF challenge. RSS and Cellar are fine.
- If a feed fails, record it in the report and continue.

No RSS feed exists for these; check the pages for items in the period:

- Basel Committee publications: https://www.bis.org/bcbs/publications.htm. It may block scripted access (HTTP 403); if so, rely on the BIS media releases feed and say so in the report.
- Central Bank of Ireland, only with a `client` in Ireland: https://www.centralbank.ie/news-media

### Step 2: Registers

Run every download script with `--check` (see *Commands* in `AGENTS.md`) and list what is new or changed. Don't download. The `reports` and `cp` checks take several minutes; run them in the background while you work on Step 3.

### Step 3: Filter and classify

For each item from Steps 1 and 2:

1. **Scope**: core credit risk, context, or out of scope (per `AGENTS.md`). Out-of-scope items get one line each at the end of the report and no analysis.
2. **Type and legal force**: law (regulation, directive, delegated or implementing act); EBA guidelines (comply-or-explain); ECB expectations; report (not binding); consultation (proposal only, with the deadline for comments); Q&A; speech or press release (not binding).
3. **Status and dates**: proposed, final draft, adopted, or published in the OJ; date of entry into force, date of application, transitional periods.
4. **Wiki impact**: search `data/02-wiki` for the topic and the act reference. List the articles to update, and say whether the item would justify a new article.
5. **Corpus**: is the document already in a register in `data/00-source`? If not, name the download script that should pick it up, or say that a script needs extending.

Don't guess. If a document can't be opened, say so and classify it from the title only, marked *from title*.

### Step 4: Stale sources

Run the stale-sources part of `audit`: wiki articles citing a file that the registers now mark as outdated.

### Step 5: Report

Save to `data/03-output/reg-watch/<YYYY-MM-DD>_regulatory-update.md` (or `.html` with the `html` argument):

1. **Summary**: period covered, feeds checked (OK / failed), items found and kept, and the 3–5 items that matter most, one line each.
2. **Credit risk updates**: a table sorted by importance: Date | Source | Item (with link) | Type & legal force | Status & key dates | Why it matters | Wiki articles affected (+ Impact on client, with `client`).
3. **Context items** (own funds, Pillar 2, governance, stress testing): same table, shorter.
4. **Open consultations**: title, deadline for comments, topic.
5. **Coming into application in the next 12 months**: date, rule, source.
6. **Stale wiki articles**: from Step 4, with the newer source version.
7. **Proposed actions**, numbered by priority:
   - download commands to run;
   - compile scopes, as `compile <scope>`;
   - recompiles of stale articles;
   - script extensions for sources that no downloader covers.
8. **Out of scope**: one line per item.

Then write today's date to `data/03-output/reg-watch/last-check.txt`.

Every item has a link to the official page or document. Never present a consultation or a draft as a rule in force.

### End of Phase 1

In the chat, give a five-line summary, the path of the report and the numbered proposed actions. Ask which actions to run ("all", "1, 3", or "none"). Stop and wait.

## Phase 2: update (only after confirmation)

Run only the actions the user confirmed, in priority order:

1. **Download**: run the confirmed download scripts without `--check`. Report the new files and versions from the registers' `history` sheets.
2. **Compile**: run each confirmed `compile <scope>` as defined in `AGENTS.md`, including updating the indexes and appending to `log.md`. Ask before creating a topic wiki that isn't in the suggested list.
3. **Recompile stale articles**: update their claims and the `sources[].path` to the new versions, and bump the `updated` date.
4. **Script extensions**: propose the change to the relevant script in `src/` and wait for approval before editing it.

Then run a full `audit` and report it without fixing anything; fixes need a separate confirmation, as `AGENTS.md` requires.

Finish with the summary required by the `compile` workflow (sources processed or skipped, articles created and updated, stub links, open questions), plus a link to the Phase 1 report.

## Rules

- Never rename, move or edit files in `data/01-raw`.
- Never merge, delete or reorganise wiki articles without explicit confirmation.
- If a feed or script fails, report it; don't silently drop it.
