# Source downloaders

How each downloader in `src/` reads its site, versions documents and detects changes. Read this before changing a downloader.

`src/cli.py` is the entry point for the downloaders; setup, dependencies and commands are in [tooling.md](tooling.md). In short: manage dependencies with `uv` (`uv add`, never `pip`), and run `uv run src/cli.py <command>` from the repository root. Shared Excel code lives in `src/register.py`.

Downloaded file names are listed in [folder-structure.md](folder-structure.md#sources-data00-source-and-data01-raw).

## EUR-Lex (`download_isrb.py`)

- The act list comes from the table at https://www.eba.europa.eu/regulation-and-policy/single-rulebook/interactive-single-rulebook. The EBA link is used only to identify the act, because it can lag behind EUR-Lex.
- `eur-lex.europa.eu` returns an AWS WAF challenge (HTTP 202, empty body) to scripted clients, so don't scrape it. Use the Publications Office SPARQL endpoint (`publications.europa.eu/webapi/rdf/sparql`) to resolve versions, and download Cellar item URLs (`.../resource/cellar/<id>/DOC_n`). Cellar content negotiation on `/resource/celex/<id>` misses some PDFs.
- Versioning uses CELEX ids:
  - `0YYYYTNNNN-YYYYMMDD` is a consolidated version.
  - `3YYYYTNNNN` is the original OJ act.
  - The "current" version is the newest consolidation dated today or earlier that has an English expression.
  - Future-dated consolidations already exist (e.g. CRR `-20270101`); they are recorded as `next_celex`, not downloaded.
  - Acts never amended (DORA, WTR) have a base-layer consolidation with no English text, so the original `3…` act is used instead.
- Filtering SPARQL with `STRSTARTS` over all CELEX ids is slow when combined with manifestation joins. Look up manifestations with `VALUES` on exact, typed (`xsd:string`) CELEX literals.

## EBA publications (`download_eba_publications.py`)

- To add a publication type, add an entry to `PUBLICATION_TYPES`: the listing's `document_type` id (250 Guidelines, 248 draft RTS, 247 draft ITS, 257 Reports, 244 Consultation papers, …; the ids come from the filter `<select>` on the page), the preferred reference kind, the register file and the download folder.
- The listing is the EBA publications page filtered on `document_type`, paged with `&page=N`. Each `article.teaser` links directly to a file (PDF, sometimes xlsx/docx/zip). A few items (Risk Assessment Reports) link to an HTML publication page instead of a file. That page is saved as `.html`, and because it sends no ETag/Last-Modified, its `sha256` is a hash of the normalised `<main>` text, which is compared on every run. The date is in `.link-icon--calendar`; some teasers also carry a "Publication" tag in the same metadata block. EBA's type tagging is loose: some items appear in more than one listing, and the RTS listing contains a few GL/ITS documents.
- EBA has no version metadata, so the register infers versions:
  - `doc_id` is assigned on first sight and never changes.
  - A new version is recorded when the same URL returns different ETag / Last-Modified / Content-Length headers and different bytes, or when an item with the same date and title appears under a new URL (a re-upload). Date + title alone isn't unique: a few pairs occur twice in the registers.
- `eba_reference` (EBA/<GL|RTS|ITS|REP|CP|…>/YYYY/NN, preferring the listing's own kind) comes from the title, the filename, or page 1 of the PDF via `pdftotext`.
- `later_same_reference` lists later items with the same reference (consolidated versions, corrigenda), as a hint that a document may be superseded. It is only a hint:
  - EBA has reused a number: EBA/REP/2025/11 appears on two different reports.
  - Some covers cite another document ("Report complementing EBA/REP/2021/18").
- The reference regex separators deliberately exclude newlines. Otherwise a cover line "EBA/Rep/2022" followed by "08 April 2022" would read as EBA/REP/2022/08.

## EBA Single Rulebook (`download_eba_single_rulebook.py`)

- The EBA publications listing misses the final versions of many older guidelines (e.g. EBA/GL/2017/16, EBA/GL/2019/03, EBA/GL/2017/06). Their final texts are on the Single Rulebook product pages, one page per regulatory product.
- Listing: there is no sitemap, and a topic page (`/regulation-and-policy/<topic>`) shows only some of its products in the body. The breadcrumb menu (`nav.breadcrumb-sw`, last `li.breadcrumb-sw__item`, its `.breadcrumb-sw__item-children` links) lists all of them. Topics come from the same menu. Product URLs vary: most are `/activities/single-rulebook/regulatory-activities/<topic>/<slug>`, some are at the site root or under `/legacy/`, so take them from the menu, never from a URL pattern.
- A product has versions (current URL; "Previous versions" `?version=<year>` and "Ongoing versions" in `.activity-versions__buttons` dropdowns) and phases (`.timeline__item`: Consultation, Final Report, Consolidated Document, each `?phase=<name>`; the version URL shows its latest phase). A phase page has a status box (`.box-data__items`: Status, Application date, Compliance deadline) and `.document-download` cards: the English file in `.card-body`, translations in a collapsed list, not downloaded. An amending act becomes the current version while the original stays a previous version, often still in force (definition of default: current 2026 amending report; EBA/GL/2016/07 under `?version=2016`).
- Consultation phases are skipped; a product only under consultation yields nothing. Products migrated from the old site keep their final texts in the description's "Documents" box (`.well a`), e.g. the downturn LGD guidelines; those links are read too (phase `Documents (product page)`), skipping translation links labelled `bg български`, `en English`, … Old-style links (`/documents/10180/<n>/<name>.pdf/<uuid>`) redirect to the file and end in a UUID, so the file name is taken from the segment with an extension.
- `doc_id` is a hash of product URL, phase title and card title. A new file version is recorded when the card's URL or "Last update" date changes and the bytes differ; no HEAD requests are needed.

## ESMA library (`download_esma.py`)

- The source is the ESMA library table filtered on section 35, "Guidelines and Technical standards" (`?f[0]=basic_section:35`). Each top-level `tbody` row has `td.views-field-*` cells: `created` (dd/mm/yyyy), `field-document-reference` (the ESMA reference), `title` (link to the document page), `field-document-section`, `field-document-type` and `field-main-document` (the file link). The `Info` cell holds nested tables of related documents and translations; only top-level rows are listings.
- Paging: `items_per_page=50` with `&page=N`. `items_per_page=100` works for page 0 only; later pages return HTTP 500.
- `doc_id` is a hash of the document page URL (`/document/<slug>`), which is steadier than the file URL. A new file URL with different bytes is a new version.
- Change detection uses ETag and Last-Modified only: ESMA answers HEAD requests with `Content-Length: 0`.
- The listing also carries translations of older guidelines as separate rows (about 470 of 775). They are kept with status `translation` and not checked: their file names end or start with a language code in many forms (`_bg_tra`, `_de_cor2`, `2011-188pt`, `-enbg_0`, the non-ISO `cz`/`ee`, `bg_-_jc_…`), and ESMA sometimes gives them the English title. A title with non-ASCII letters catches the rest. Checking them all used to trigger HTTP 429 rate limiting.

## Basel Framework (`download_basel.py`)

- Each chapter version has a URL `.../basel-framework/standard/<std>/<nn>/inforce/<effective>/published/<published>`. That date pair is the version key: BIS publishes an amendment under a new published date, so files are never re-checked once saved.
- The listing is the framework timeline (`.../basel-framework/timeline?page=N`), whose cards give the chapter, title and BIS status (Current, Forthcoming, Superseded, "Removed on <date>"). Its pager never ends (pages past the last repeat it), and its order is unstable between requests, so items can slip across page boundaries. The script therefore uses it, together with the framework home page, only to find the chapters, then reads each chapter's own timeline (`?standard=CRE&chapter=20`).
- BIS marks a few older versions "Current" next to the newer one (e.g. SRP31 2019 and 2026). `current_doc_id` picks the latest effective date, then the latest published date.
- Only Current and Forthcoming versions are downloaded. The saved file is the page's chapter column (`div.col-md-7` around `div.chapters-content`) wrapped as a standalone HTML file. The full page is not saved: its bytes and ETag change on every request, while the chapter column is byte-stable.
- Don't use the chapter PDFs (`.../basel-framework/<node>/chapter.pdf`): they are rendered on request, and the same link sometimes returns a different version of the chapter. The script checks the page's "Effective as of" date against the URL.

## ECB supervisory guides (`download_ecb_guides.py`)

- The guides page is rendered by JavaScript. The list itself is an HTML snippet named in the page's `data-snippets` attribute (`.../supervisoryguides_include.en.html`): `<dt isoDate>` + `<dd>` with `.title a` and an explicit English link `a[lang=en]`.
- The list keeps old editions next to new ones. `guide_key` (lowercased title without a leading "ECB"/"SSM" and without "- consolidated version") groups them; the newest is `edition_status=current`, and older ones are `superseded` with `superseded_by` pointing to the next edition.
- Change detection: the `?<hash>` on the title link is a cache key, not the file's MD5, and changes when the file is replaced. The server sends Last-Modified (unreliable: it reflects redeploys) and Content-Length, but no ETag. Any of these changing triggers a download; a new `_vN` version is recorded only if the SHA-256 differs.
