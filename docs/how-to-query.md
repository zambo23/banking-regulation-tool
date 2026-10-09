# How to query the tool and get memos

This guide shows how to ask questions that get precise, cited answers, and how to get a client memo saved in `data/03-output/`. It assumes the wiki has been compiled for your topic; see [How to build knowledge on a credit risk topic](how-to-guide-credit-risk-topic.md) for that.

The agent does the heavy lifting through two skills in `.agents/skills/`:

| Skill | Use it for | Invoke |
| --- | --- | --- |
| `consultation-memo` | A client question answered in chat, then written up as a cited memo | `/consultation-memo`, or ask for "a memo" / paste a ROLE–CLIENT–QUESTION prompt |
| `update-body-of-knowledge` | What's new from the regulators, and refreshing the wiki | `/update-body-of-knowledge`, or ask "any regulatory updates?" |

Claude Code reads the skills directly. With other agents, point them at the skill file, e.g. "follow `.agents/skills/consultation-memo/SKILL.md`".

## Where answers come from

1. **The wiki** (`data/02-wiki`): the default. Every claim keeps its pinpoint citation and legal force.
2. **The downloaded sources** (`data/01-raw`): used when the wiki has a gap. Claims checked here are tagged **Checked**.
3. **The agent's own knowledge**: only for texts that aren't downloaded (other EU acts, national law). Always tagged **To verify**.

A memo with **To verify** items is a draft. Close them before it goes to a client.

## Write an effective prompt

A good prompt covers six elements. The skill fills in sensible defaults for most of them. **Client facts** are the one it can't guess, because they decide which rules apply.

| Element | What to state | Example |
| --- | --- | --- |
| **Role and audience** | Who is writing, for whom | "Senior consultant, for the client's board" |
| **Client facts** | Type of firm, jurisdiction, customers, SA/IRB, size | "P2P lending platform in Ireland, SME borrowers only, 8 staff" |
| **Question** | One or more precise questions | "Can it outsource credit scoring? Under what conditions?" |
| **Scope** | Reference date, what to include or leave out | "Rules in force today; flag what applies within 12 months; ignore AML" |
| **Sources** | Which layers may be used | "Wiki first, then raw sources; tag the rest To verify" (the default) |
| **Output** | Format, length, audience | "HTML memo, max 3 pages" (the default is HTML, 2–4 pages) |

The fill-in template is in [`.agents/skills/consultation-memo/reference/template.md`](../.agents/skills/consultation-memo/reference/template.md).

### Weak and strong

> explain what are the requirements from regulators and if they can use an external provider

The agent has to guess the type of firm, the country, the rules and the date.

> **Role:** senior consultant. **Client:** P2P lending platform authorised in Ireland, lending to SMEs only, about 8 staff.
> **Question:** what are the main regulatory requirements, and when may the platform use external providers (cloud, credit scoring, payments)?
> **Scope:** rules in force today; flag anything applying within 12 months; AML in one line only.

These facts change the answer itself, not just its presentation:
- "SMEs only" puts the platform under the Crowdfunding Regulation rather than consumer-credit law.
- "8 staff" brings in DORA's lighter regime for microenterprises.

### Tips

- **Name the regime.** SA or IRB; significant or less significant institution; bank, investment firm or platform.
- **Fix a reference date.** Transitional periods (CRR3, the amended definition of default) make "when" matter.
- **Ask for pinpoints and legal force.** `CRR Art. 178(1)(b)`, comply-or-explain, ECB expectation, proposal: the skill does this by default; insist if an answer lacks them.
- **Outline first for big memos.** `/consultation-memo outline` stops after the outline and source list so you can steer before anything is written.
- **Push back precisely.** "Section 3 ignores EBA/GL/2016/07 para. 23; revise it." The agent revises that section and saves a new version.
- **Ask what's missing.** "Which sources would close the To verify items?" turns gaps into a download or compile plan.

## The memo flow

```text
prompt ─► agent frames & researches ─► answer in chat ─► you correct ─► memo (.html) ─► close "To verify" ─► final
```

1. **Prompt**: use the template; the agent asks at most three questions if a client fact is missing.
2. **Review the chat answer**: right regime? citations and legal force? dates? unchecked claims flagged? Correct it in chat. It is quicker than editing the file.
3. **Memo**: say "go ahead" (or use `direct` to skip the pause). You get `data/03-output/<date>_<name>.html`: a header, the bottom line, tagged sections, a timeline, next steps, a sources table and a draft disclaimer.
4. **Close the To verify items**: download the missing texts (ask for the download scripts to be extended; don't copy files into `data/01-raw` by hand), then run `/consultation-memo recheck <memo path>`. It saves a `-v2`.
5. **Export**: open the HTML file and print to PDF.

If the memo has lasting value, ask to "turn it into a wiki article". The agent asks before adding anything outside the credit-risk scope.

### Before sending to a client

- [ ] The regime matches the client's facts, and any assumptions are stated.
- [ ] Every claim has a pinpoint citation and a legal force.
- [ ] Consultations and drafts are presented as proposals.
- [ ] Application dates and transitional periods are stated.
- [ ] No **To verify** left, or the memo is clearly marked as a draft.
- [ ] National-law points confirmed with local counsel.

## Cheat sheet

| Goal | Prompt |
| --- | --- |
| Quick answer | `What is the materiality threshold for retail exposures? Cite the sources.` |
| Compare | `Compare the NPE exit rules with the return to non-defaulted status: table with criteria, periods, legal basis.` |
| Check coverage | `Can the wiki answer <question>? If not, which sources should I compile?` |
| Limit sources | `answer from the wiki only` / `you may also read the raw sources` |
| Memo | `/consultation-memo` + your filled-in template |
| Outline only | `/consultation-memo outline` |
| Re-check a memo | `/consultation-memo recheck data/03-output/<file>.html` |
| What's new | `/update-body-of-knowledge` (or `quick` for a chat-only look) |
| Explore links | `graphify query "<question>" --graph data/03-output/graphify-out/graph.json` |
