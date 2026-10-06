# SmartPick – Conversational Headphone Recommender

Turns a shopper's free-text (or structured) preferences into filters, ranks a small
synthetic catalogue with transparent, configurable scoring, and explains the top 3.

Stack: Python · Pandas · Streamlit · CSV + JSON. No ML, no external APIs.
Scope: headphones only. No sensitive profiling, dynamic pricing, or health claims.

## Run

```bash
pip install -r requirements.txt
python generate_data.py      # (re)creates products.csv and scenarios.json
python evaluate.py           # runs the 15 shopper scenarios
streamlit run app.py         # launches the UI
```

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI: chat, sidebar form, cards, comparison, refinement buttons |
| `recommender.py` | Parsing, normalization, filtering, scoring, explanations |
| `products.csv` | 47 fictional products (5 out of stock) |
| `config.json` | Scoring weights, boosts, aliases, thresholds |
| `scenarios.json` | 15 shopper scenarios with budget, must-haves, preferences, expected suitable products |
| `generate_data.py` | Builds the CSV and scenarios |
| `evaluate.py` | Checks parsing, constraint safety and suitability for all scenarios |

## How it works

1. **Extract & normalize**: regex + keyword aliases turn "under 5k", "ANC", "no Boltbeat" into
   `{"budget": 5000, "must_have": ["active_noise_cancellation"], "exclude_brands": ["Boltbeat"], ...}`.
   Features in `soft_features` (lightweight, bass, ...) and anything near "prefer / ideally / bonus" are
   *preferred*; everything else is *must-have* unless the phrase says otherwise.
2. **Filter** (in order): out of stock → over budget → missing must-have → excluded brand/type/feature → minimum rating.
3. **Score** (0–100) = weighted sum of five sub-scores (0–1), weights from `config.json`:
   feature match 30%, rating 25%, battery 20%, price value 15%, extra features 10%,
   plus a small bonus for a preferred brand.
   - feature match: (must-haves + matched preferences) / (all requested)
   - rating: (rating − 3) / 2
   - battery: hours / 60
   - price value: 1 − price / budget (or catalogue max if no budget)
   - extra features: bonus features present / 4
4. **Explain**: matched features, price vs budget, score breakdown, and trade-offs
   (missing preferences, close to budget limit, shorter battery, features other top picks have).
5. **Refine**: "make it cheaper" (budget −15%), "better battery", "higher rating" (min 4.3),
   "more lightweight", "more features", or any new constraint. Filters update, the same scoring re-runs, a new top 3 appears.

If nothing fits, the app says which single constraint to relax (e.g. "raise budget to ₹2,699").

## Tuning

Edit `config.json`: change `weights`, `preference_boost`/`priority_step` (how strongly priorities shift weights),
`brand_bonus`, `lightweight_max_g`, or add words to `feature_aliases`.
