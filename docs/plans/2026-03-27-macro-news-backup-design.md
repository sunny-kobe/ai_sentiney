# Macro News Backup Design

**Goal:** Reduce remaining morning-report degradation by adding a fast free backup chain for macro news when `news_cctv` is slow or empty.

## Problem

After fixing morning global indices, the main remaining morning degradation comes from `macro_news`:

- `ak.news_cctv()` can time out under the current runtime budget
- when it times out, morning reports often degrade even though other free public news feeds are still available
- the collector currently tries only one primary CCTV path plus one broad global feed fallback, which is too narrow and too slow-first

In practice, this means morning reports now usually have overnight indices, but still lose freshness because one macro-news source is fragile.

## Product Principle

**Morning news should prefer fast, broad public feeds over a single slow canonical feed.**

For morning decision support, timely macro context matters more than insisting on one specific editorial source.

## Options

### Option 1: Increase `news_cctv` timeout

Rejected. It directly slows morning output and still keeps the system dependent on one fragile source.

### Option 2: Add a short backup chain across multiple free public feeds

Recommended. This preserves timeliness and increases source diversity without adding cost.

### Option 3: Add a paid macro-news API

Rejected for now. It adds credentials and cost before the free path is exhausted.

## Recommended Design

Keep the current macro-news return shape:

- `telegraph`
- `ai_tech`

But change the collection strategy to a staged chain:

1. try `ak.news_cctv()` for today
2. if empty, try `ak.news_cctv()` for yesterday
3. if still empty or timed out, try free public live feeds in priority order:
   - `ak.stock_info_global_cls(symbol="全部")`
   - `ak.stock_info_global_sina()`
   - `ak.stock_info_global_futu()`
   - `ak.stock_info_global_ths()`
4. normalize whichever source returns data first into headline strings
5. derive `ai_tech` from the normalized headline list using the existing keyword filter

## Why This Ordering

- CCTV remains first because it is still relevant as a curated macro source when available
- `cls` and `sina` are fast and broad, and currently reachable in this environment
- `futu` and `ths` are good fallback surfaces if the first two are unavailable
- this avoids waiting on multiple slow sources in sequence once one fast source already succeeded

## Data Contract

All backup feeds should normalize to a simple headline list:

- `stock_info_global_cls`: prefer `标题`
- `stock_info_global_sina`: use `内容`
- `stock_info_global_futu`: prefer `标题`, fall back to `内容`
- `stock_info_global_ths`: prefer `标题`

The collector only needs top N concise items, not full article content.

## Error Handling

- one backup feed failing must not abort the rest
- if a source returns an empty DataFrame, move on immediately
- if any backup source yields usable headlines, mark `macro_news` as `fresh`
- only return empty `telegraph` when the full chain is exhausted

## Testing Strategy

Add tests proving:

- macro news falls back from CCTV timeout to backup feeds
- backup feeds normalize correctly into `telegraph`
- AI-related headline extraction still works on backup content
- morning mode no longer degrades on macro news when backup feeds succeed

## Risks

- free news-feed schemas can change
- some backup feeds may contain noisy market headlines

These are acceptable because the current issue is missing context, not over-abundance of context, and the report already surfaces quality state explicitly.
