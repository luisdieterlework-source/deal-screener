# Example memos

Three sample screening memos on well-known, heavily covered private tech companies:

| Company | Memo | PDF | Raw JSON | Sources |
|---|---|---|---|---|
| Stripe (payments infrastructure) | [stripe.md](stripe.md) | [stripe.pdf](stripe.pdf) | [stripe.json](stripe.json) | 23 |
| Notion (productivity SaaS) | [notion.md](notion.md) | [notion.pdf](notion.pdf) | [notion.json](notion.json) | 20 |
| Perplexity (AI search) | [perplexity.md](perplexity.md) | [perplexity.pdf](perplexity.pdf) | [perplexity.json](perplexity.json) | 28 |

## How these were produced (please read)

- **Produced during development, not by a live run of this app.** No `ANTHROPIC_API_KEY` was
  available in the build environment, so the research was done by a Claude research agent with
  web search, following the same system prompt and JSON schema the app uses
  (`deal_screener/prompts.py`). The JSON files were then rendered with the app's own renderer:
  `python -m deal_screener --render examples/stripe.json --out examples`.
- **As of 2026-11-04.** Valuations, revenue estimates and funding change quickly.
- **Citations come from search results.** The build sandbox blocked opening most external pages,
  so claims are backed by the search result title and snippet of the cited URL, not a full read
  of the page. Some links are syndicated copies of the original article. A live run of the app
  reads pages with its `fetch_page` tool.
- **Estimates are labelled as estimates.** Revenue figures for private companies (e.g. Sacra's
  Stripe and Notion numbers, press reports on Perplexity's ARR) are third-party or press figures,
  not company disclosures.
- **Uncited items are analysis.** A few acquirer and competitor lines are analytical judgement
  without a source; the renderer flags uncited factual claims as *(unverified)*.

Not investment advice. Only public information was used.
