# How to query the tool and write memos

This guide shows how to write prompts that get precise, cited answers out of the tool, and how to turn an answer into a memo saved in `data/03-output/`. It assumes the wiki has already been compiled for your topic; see [How to build knowledge on a credit risk topic](how-to-guide-credit-risk-topic.md) for that.

There are two kinds of requests:

- **A question**: answered in the chat from the wiki, with links and citations. Nothing is saved unless you ask.
- **A deliverable**: a memo, comparison or report, written as a file to `data/03-output/`. These are one-off outputs; they are not part of the wiki.

```text
1. Frame the request ─► 2. Agent answers ─► 3. Review ─► 4. Save as memo ─► 5. Verify & finalise
```

## Where answers come from

The agent follows the *Query* workflow in [`AGENTS.md`](../AGENTS.md):

1. **The wiki** (`data/02-wiki`): it reads `index.md`, then the topic indexes, then only the articles it needs. Every claim keeps its pinpoint citation and legal force.
2. **The raw sources** (`data/01-raw`): if the wiki can't answer, the agent says so and suggests what to compile. If you allow it, it can also read the downloaded texts directly.
3. **Its own knowledge**: for texts that aren't downloaded (for example the Crowdfunding Regulation or national rules). This is the weakest layer: always ask for it to be flagged.

Your prompt decides which layers the agent may use and how it marks them. If you say nothing, the agent tells you when the wiki can't answer and suggests sources to compile.

## Anatomy of an effective prompt

An effective prompt answers six questions. Leave one out and the agent has to guess.

| Element | What to state | Example |
| --- | --- | --- |
| **Role and audience** | Who is writing, and for whom | "Senior consultant, writing for the client's board" |
| **Context** | The entity and the facts that change the answer: type of firm, approach, jurisdiction, size | "P2P lending platform in Ireland, business borrowers only, 8 staff" |
| **Question** | What you need to know, as one or more precise questions | "Can it outsource credit scoring? Under what conditions?" |
| **Scope** | Date of reference, which rules count, what to leave out | "Rules in force on 2026-10-09; flag anything that applies within 12 months; ignore AML" |
| **Sources** | Which layers the agent may use and how to mark them | "Wiki first, then raw sources; flag anything from general knowledge as *to verify*" |
| **Output** | Format, length, structure and where to save it | "HTML memo, 2–3 pages, saved to `data/03-output/`" |

### Template

```markdown
# ROLE
<who is writing and for whom>

# CLIENT / CONTEXT
<entity type, jurisdiction, business model, size, approach (SA/IRB), anything that changes the answer>

# QUESTION
<one or more precise questions>

# SCOPE
- Reference date: <date>; flag changes that apply within <period>
- Include: <topics, layers of rules>
- Exclude: <topics>

# SOURCES
- Use the wiki first, then the raw sources in data/01-raw
- Cite article/paragraph for every claim and state the legal force
- Tag anything not checked against a downloaded text as "To verify"

# OUTPUT
- Format: <chat answer | .md | .html memo>, <length>
- Structure: <bottom line first, then …>
- Save to data/03-output/<YYYY-MM-DD>_<short-name>.<ext>
```

You don't need every heading for a quick question. You need them all for a memo.

### Weak and strong prompts

A weak prompt:

> explain what are the requirements from regulators and if they can use an external provider

The agent has to guess the type of firm, the country, which rules count, the reference date and the output format.

A strong prompt for the same question:

> **Role:** senior consultant. **Client:** P2P lending platform authorised in Ireland, lending to SMEs only, about 8 staff.
> **Question:** what are the main regulatory requirements, and when and how may the platform use external providers (cloud, credit scoring, payments)?
> **Scope:** rules in force on 2026-10-09; flag anything applying within 12 months. Leave out AML except for one line.
> **Sources:** wiki first, then the raw sources; cite articles; tag anything from general knowledge as "To verify".
> **Output:** answer in chat first; bottom line in three lines, then requirements, then outsourcing conditions, then a timeline.

The strong prompt changes the answer, not just the style. "SMEs only" places the platform under the Crowdfunding Regulation rather than consumer-credit law. "8 staff" brings in DORA's lighter regime for microenterprises. "Tag anything as To verify" makes the gaps in the corpus visible.

## Tips for precise answers

- **Name the regime and the approach.** "Standardised approach" or "IRB"; "significant institution supervised by the ECB" or "less significant institution"; "bank" or "investment firm". The rules often differ.
- **Fix a reference date.** Many rules have transitional periods (CRR3, the amended definition of default). "As of 2026-10-09, and what changes in 2027" avoids mixing two regimes.
- **Ask for legal force.** Law, comply-or-explain guidelines, ECB expectations and consultation papers carry very different weight. Ask the agent to label each claim.
- **Ask for pinpoints.** "Cite the article and paragraph" gives you `CRR Art. 178(1)(b)` instead of "the CRR says".
- **Ask what's missing.** "Which sources would you need to answer this fully?" turns gaps into a compile plan.
- **Split large requests.** For a long memo, first ask for an outline and a source list, approve it, then ask for the memo. This is the same idea as the source plan in Step 2 of the topic guide.
- **Ask one thing per prompt when it matters.** A comparison and a memo in the same prompt usually means two half-answers.
- **Push back.** If an answer looks thin or wrong, say where: "Section 3 ignores EBA/GL/2016/07 para. 23; revise it." The agent revises that part rather than starting again.

### Useful prompt patterns

| Goal | Prompt |
| --- | --- |
| Quick answer | `What is the materiality threshold for retail exposures? Cite the sources.` |
| Compare | `Compare the NPE exit rules with the return to non-defaulted status: table with criteria, periods, legal basis.` |
| Timeline | `Which credit risk rules change between now and 2028? Table with date, change, source.` |
| Impact | `For an SA bank with a large residential mortgage book, what does CRR3 change in risk weights? Bottom line first.` |
| Check coverage | `Can the wiki answer <question>? If not, which sources should I compile?` |
| Explore links | `graphify query "<question>"` (needs the graph in `data/03-output/graphify-out/`; see [how-to-graphify](how-to-graphify.md)) |

## Writing a memo

### Step 1: Ask for the answer first

Use the full template above and ask for the answer **in chat**. Reviewing in chat is quicker than editing a file, and the agent keeps the context for the memo.

### Step 2: Review the answer

Check before you ask for the memo:

- Is the **regime** right for the client's facts (the *Context* element of the prompt)?
- Does every important claim have a **citation and a legal force**?
- Are the **dates** and transitional periods correct?
- Are claims not backed by a downloaded source **flagged**?

Correct anything wrong in chat first.

### Step 3: Ask for the memo

> prepare a memo (.html), save into data/03-output/

Add anything the memo needs that the chat answer didn't have:

> prepare a memo (.html) for the client's board, max 3 pages, with a bottom line box, a "next steps" section and a sources table showing legal force; save into data/03-output/

What you get (see `data/03-output/2026-10-09_p2p-platform-ireland-outsourcing-memo.html` for an example):

- **One self-contained file**, named `<YYYY-MM-DD>_<short-name>.html`. It opens in any browser and prints cleanly to PDF.
- **A memo header**: to, from, date, subject.
- **A bottom line** before the detail.
- **Verification tags** on each statement: *Checked* (verified against a downloaded text) or *To verify* (not yet checked).
- **A sources table** with the file path of every source used, its legal force and whether it was checked.
- **A disclaimer** that the memo is a draft until the *To verify* items are checked.

Ask for `.md` instead of `.html` if you want to edit the memo yourself or paste it elsewhere.

### Step 4: Verify and finalise

1. **Close the *To verify* items.** Either check them yourself, or download the missing texts and ask the agent to re-check:

   > the Crowdfunding Regulation is now in data/01-raw; re-check every "To verify" item in the memo and update the tags

   Don't copy files into `data/01-raw` by hand; extend the download scripts instead (see [Handling gaps](how-to-guide-credit-risk-topic.md#handling-gaps)).
2. **Spot-check two or three citations** against the source PDFs.
3. **Export**: open the HTML file and print to PDF.

### Step 5: Keep what lasts

Outputs in `data/03-output/` are disposable. If a memo contains analysis you will reuse, ask:

> turn the outsourcing section of the memo into a wiki article

The agent proposes where it goes and asks first, especially for topics outside the credit risk scope. The new article cites the memo as a source.

## Before sending anything to a client

- [ ] The regime matches the client's facts (type of firm, jurisdiction, borrowers, approach).
- [ ] Every claim has a pinpoint citation and a legal force.
- [ ] Consultation papers and drafts are presented as proposals, not rules.
- [ ] Dates, application dates and transitional periods are stated.
- [ ] No *To verify* tags remain, or the memo is clearly marked as a draft.
- [ ] National law points are confirmed with local counsel.

## Prompt cheat sheet

| Goal | Prompt |
| --- | --- |
| Ask | any question; add "cite the sources and state the legal force" |
| Limit the sources | `answer from the wiki only` / `you may also read the raw sources` |
| Flag gaps | `tag anything not checked against a downloaded text as "To verify"` |
| Outline first | `propose the outline and sources for a memo on <topic>; don't write it yet` |
| Memo | `prepare a memo (.html), save into data/03-output/` |
| Revise | `revise section <n>: <what's wrong>` |
| Re-check | `re-check every "To verify" item against data/01-raw and update the tags` |
| Keep | `turn this into a wiki article` |
