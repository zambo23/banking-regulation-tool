# AGENTS.md

This file provides guidance to AI agents working in this repository.

## What this project is

A "second brain" for **EU banking regulation and the Basel Framework, focused on credit risk**.

It follows the LLM Wiki pattern popularised by Andrej Karpathy.
Instead of re-reading raw documents for every question, an LLM compiles them once into a persistent, interlinked Markdown wiki and keeps it up to date as sources change.

There are three layers:

1. **Sources**: the Excel registers that track every version (`data/00-source`), the official texts downloaded by the Python scripts in `src/` (`data/01-raw`), and Markdown versions of the PDFs among them (`data/02-raw-md`). The downloaded texts are immutable.
2. **Wiki** (`data/03-wiki`): Markdown articles written and maintained by the agent. This is the knowledge base.
3. **Schema** (this file, the docs below and the agent prompts `docs/agent-prompt-*.md`): the rules the agent follows to build, query and maintain the wiki.

The user decides which sources matter and asks the questions. The agent does the bookkeeping: summarising, cross-referencing, citing, indexing, and flagging content that has gone stale.

An agent here has two jobs:

- **Librarian**: compile sources into the wiki, answer questions from it, audit it. Follow [docs/llm-wiki.md](docs/llm-wiki.md) and [docs/workflows.md](docs/workflows.md).
- **Developer**: maintain the download scripts. Follow [docs/downloaders.md](docs/downloaders.md) and [docs/tooling.md](docs/tooling.md).

## Wiki rules

Read [docs/llm-wiki.md](docs/llm-wiki.md): scope, the legal force of each source, the wiki's structure, article format, citation and linking rules, and principles.

## Workflows

Read [docs/workflows.md](docs/workflows.md): update sources, regulatory watch, `compile`, query, memos and reports, source map, knowledge graph, `audit`.

## Folder structure

Read [docs/folder-structure.md](docs/folder-structure.md).

## Tooling

Read [docs/tooling.md](docs/tooling.md).

## Source downloaders

Read [docs/downloaders.md](docs/downloaders.md): how each downloader reads its site, versions documents and detects changes.

## Background

[docs/banking-regulators.md](docs/banking-regulators.md): who the BIS, the EU legislators, the EBA, the ECB and DNB are, and how binding their output is.
