"""SmartPick core logic: preference extraction, filtering, scoring, explanation.

Pure Python + Pandas, no ML and no external APIs. Everything that can be tuned
(weights, boosts, aliases, thresholds) lives in config.json.

Pipeline
    free text / structured input
        -> parse_preferences / update_preferences   (extract + normalize)
        -> filter_products                           (stock, budget, must-haves, exclusions)
        -> score_products                            (weighted, transparent)
        -> recommend                                 (top N + explanations + relax hints)

Extras built on top of that pipeline
    reviews          load_reviews / review_summary
    why not?         reject_reasons / why_not / near_misses / find_product_in_text
    alternatives     smart_alternatives (cheaper saver, stretch picks, relaxed matches)
    similar          similar_products
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent

TYPE_KEYS = ("over_ear", "on_ear", "in_ear")

# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def load_config(path=None) -> dict:
    return json.loads(Path(path or BASE / "config.json").read_text(encoding="utf-8"))


def load_products(path=None, config=None) -> pd.DataFrame:
    config = config or load_config()
    df = pd.read_csv(path or BASE / "products.csv")
    max_w = config["lightweight_max_g"]

    def feature_set(row):
        feats = set(str(row["features"]).split(","))
        feats.add(row["type"])
        if row["weight_g"] <= max_w[row["type"]]:
            feats.add("lightweight")
        return frozenset(feats)

    df["feature_set"] = df.apply(feature_set, axis=1)
    df["in_stock"] = df["stock_status"].eq("in_stock")
    return df


def load_reviews(path=None) -> pd.DataFrame:
    """Synthetic customer reviews (reviews.csv). Empty frame if the file is missing."""
    path = Path(path or BASE / "reviews.csv")
    if not path.exists():
        return pd.DataFrame(columns=["review_id", "product_id", "reviewer", "stars", "title", "text",
                                     "verified_purchase", "helpful_votes", "date"])
    return pd.read_csv(path)


def review_summary(reviews: pd.DataFrame, product_id: str, featured: int = 3) -> dict:
    """Count, average, star histogram and a balanced set of featured reviews."""
    sub = reviews[reviews["product_id"] == product_id]
    if sub.empty:
        return {"count": 0, "mean": None, "dist": {s: 0 for s in (5, 4, 3, 2, 1)},
                "featured": [], "verified_pct": 0}
    ordered = sub.sort_values(["helpful_votes", "stars"], ascending=False)
    positive = ordered[ordered["stars"] >= 4]
    critical = ordered[ordered["stars"] <= 3]
    if len(critical) and featured >= 2:
        picked = pd.concat([positive.head(featured - 1), critical.head(1)])
    else:
        picked = ordered.head(featured)
    return {
        "count": int(len(sub)),
        "mean": round(float(sub["stars"].mean()), 2),
        "dist": {s: int((sub["stars"] == s).sum()) for s in (5, 4, 3, 2, 1)},
        "featured": picked.to_dict("records"),
        "verified_pct": int(round(100 * sub["verified_purchase"].astype(bool).mean())),
    }


def inr(value) -> str:
    return f"₹{int(round(value)):,}"


def label(key, config) -> str:
    return config["feature_labels"].get(key, key.replace("_", " "))


# --------------------------------------------------------------------------- #
# Preferences
# --------------------------------------------------------------------------- #


def empty_preferences(config) -> dict:
    return {
        "category": config["category"],
        "budget": None,
        "must_have": [],
        "preferred": [],
        "brand": None,
        "exclude_brands": [],
        "exclude_types": [],
        "exclude_features": [],
        "min_rating": None,
        "priorities": {},
        "warnings": [],
    }


def build_preferences(config, budget=None, must_have=(), preferred=(), brand=None,
                      exclude_brands=(), exclude_types=()) -> dict:
    """Preferences from the structured form (no text parsing)."""
    prefs = empty_preferences(config)
    prefs["budget"] = int(budget) if budget else None
    prefs["must_have"] = list(dict.fromkeys(must_have))
    prefs["preferred"] = [p for p in dict.fromkeys(preferred) if p not in prefs["must_have"]]
    prefs["brand"] = brand or None
    prefs["exclude_brands"] = list(exclude_brands)
    prefs["exclude_types"] = list(exclude_types)
    if "battery" in prefs["preferred"]:
        prefs["priorities"]["battery"] = config["preference_boost"]
    return prefs


# Text-extraction helpers ---------------------------------------------------- #

_STRICT_END = {"anc", "mic", "tws"}
_NEG = re.compile(r"\b(?:no|not|avoid|without|exclude|excluding|except|skip|never|don't want|dont want)\s+"
                  r"(?:any\s+|the\s+|a\s+|an\s+)*$")
_REMOVE = re.compile(r"\b(?:drop|remove|forget|ignore|don't need|dont need|no longer need|not needed)\s+"
                     r"(?:the\s+|a\s+|an\s+)*$")
_MUST = re.compile(r"\b(?:must|need|needs|require|required|has to|have to|essential|only|compulsory|should have)\b")
_SOFT = re.compile(r"\b(?:prefer|preferably|preferred|ideally|nice to have|bonus|would like|if possible|"
                   r"maybe|good to have|optional|not essential)\b")
_BRAND_EXCL_CUE = re.compile(r"\b(?:no|not|avoid|without|exclude|excluding|except|skip|never|don't want|dont want)\s+"
                             r"(?:(?:any|the|brand|brands|products from)\s+)*")
_LIST_SEP = re.compile(r"\s*(?:,|\band\b|\bor\b|&|/)\s*")

_PRIORITY_PATTERNS = {
    "price_value": r"\b(?:cheap|cheapest|affordable|value for money|budget[- ]friendly|economical|pocket[- ]friendly)\b",
    "rating": r"\b(?:best[- ]rated|top[- ]rated|highly rated|good reviews|great reviews|well reviewed)\b",
    "battery": r"\b(?:battery|long[- ]lasting|playtime|play time|playback)\b",
    "extra_features": r"\b(?:extra features|feature[- ]rich|loaded with features|packed with features)\b",
}

_BUDGET_PATTERNS = [
    r"(?:under|below|less than|within|upto|up to|max(?:imum)?(?: of| is)?|budget(?: of| is| around)?|around|"
    r"not more than|no more than|at most|capped at)\s*[:\-]?\s*(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)\s*(k|thousand)?",
    r"(?:rs\.?|inr|₹)\s*(\d+(?:\.\d+)?)\s*(k|thousand)?",
    r"(\d+(?:\.\d+)?)\s*(k|thousand)\b",
    r"(\d{3,6})\s*(?:rupees|rs\b|inr)",
]
_NOT_MONEY = re.compile(r"\s*(?:h\b|hr|hrs|hour|g\b|gram|mm|day|%|star|min)")

_OUT_OF_SCOPE = re.compile(r"\b(?:backpack|laptop bag|speaker|soundbar|charger|mixer|blender|smartwatch|"
                           r"television|keyboard|mouse|kettle|microwave)\b")
_HEADPHONE_WORDS = re.compile(r"\b(?:headphone|headphones|headset|earphone|earphones|earbud|earbuds|tws|"
                              r"over-ear|on-ear|in-ear)\b")
_HEALTH = re.compile(r"\b(?:hearing aid|hearing loss|tinnitus|medical|therapy|therapeutic|cure|diagnos\w*|"
                     r"anxiety|insomnia|adhd|autism|migraine|health benefits?)\b")


def _alias_pattern(alias: str) -> str:
    pattern = r"(?<![a-z0-9])" + re.escape(alias)
    if alias in _STRICT_END:
        pattern += r"(?![a-z0-9])"
    return pattern


def _clause_bounds(text: str, pos: int):
    cuts = [0] + [m.end() for m in re.finditer(r"[.;,!?\n]|\bbut\b", text)] + [len(text)]
    left = max(c for c in cuts if c <= pos)
    right = min((c for c in cuts if c > pos), default=len(text))
    return left, right


def _parse_budget(text: str):
    for pattern in _BUDGET_PATTERNS:
        for m in re.finditer(pattern, text):
            value = float(m.group(1))
            suffix = m.group(2) if m.lastindex and m.lastindex >= 2 else None
            if suffix:
                value *= 1000
            if _NOT_MONEY.match(text, m.end()):
                continue
            if value >= 100:
                return int(value)
    return None


def _brand_regex(brands):
    names = sorted((b.lower() for b in brands), key=len, reverse=True)
    return re.compile("(?:" + "|".join(re.escape(n) for n in names) + r")(?![a-z0-9])")


def extract_preferences(text: str, config: dict, brands) -> dict:
    """Free text -> a dict of *additions* (what this message asks for)."""
    t = re.sub(r"(?<=\d),(?=\d{3})", "", text.lower())
    out = {"budget": None, "must": [], "preferred": [], "remove": [], "brands": [],
           "exclude_brands": [], "exclude_types": [], "exclude_features": [],
           "priorities": {}, "warnings": []}

    out["budget"] = _parse_budget(t)

    # Brands: exclusions first (they follow a negation cue), the rest are preferences.
    brand_re = _brand_regex(brands)
    canon = {b.lower(): b for b in brands}
    excluded = set()
    for cue in _BRAND_EXCL_CUE.finditer(t):
        pos = cue.end()
        while True:
            bm = brand_re.match(t, pos)
            if not bm:
                break
            excluded.add(canon[bm.group(0)])
            sep = _LIST_SEP.match(t, bm.end())
            if not sep:
                break
            pos = sep.end()
    out["exclude_brands"] = sorted(excluded)
    for bm in brand_re.finditer(t):
        name = canon[bm.group(0)]
        if name not in excluded and name not in out["brands"]:
            out["brands"].append(name)

    # Features (including headphone type).
    soft_features = set(config["soft_features"])
    for key, aliases in config["feature_aliases"].items():
        for alias in aliases:
            for m in re.finditer(_alias_pattern(alias), t):
                pre = t[max(0, m.start() - 30):m.start()]
                negated = bool(_NEG.search(pre))
                if _REMOVE.search(pre):
                    out["remove"].append(key)
                elif negated:
                    if key in TYPE_KEYS:
                        out["exclude_types"].append(key)
                    # "no ANC" just means "not required": ignore
                else:
                    left, right = _clause_bounds(t, m.start())
                    clause = t[left:right]
                    if _MUST.search(clause):
                        out["must"].append(key)
                    elif _SOFT.search(clause) or key in soft_features:
                        out["preferred"].append(key)
                    else:
                        out["must"].append(key)

    # "wired" means: exclude wireless products.
    if re.search(r"\bwired\b", t) and "wireless" not in t:
        out["exclude_features"].append("wireless")

    # Soft priorities and the battery preference.
    boost = config["preference_boost"]
    for dim, pattern in _PRIORITY_PATTERNS.items():
        if re.search(pattern, t):
            out["priorities"][dim] = boost
            if dim == "battery":
                out["preferred"].append("battery")

    # Safety / scope guards.
    if _HEALTH.search(t):
        out["warnings"].append("I can't make health or medical claims. I'll only match general listening "
                               "features, so please check with a professional for any health need.")
    if _OUT_OF_SCOPE.search(t) and not _HEADPHONE_WORDS.search(t):
        out["warnings"].append("SmartPick currently recommends headphones only, so I've kept the category as headphones.")

    for k in ("must", "preferred", "remove", "exclude_types", "exclude_features"):
        out[k] = list(dict.fromkeys(out[k]))
    return out


def merge_preferences(prefs: dict, add: dict) -> dict:
    prefs = copy.deepcopy(prefs)
    if add["budget"]:
        prefs["budget"] = add["budget"]
    for key in add["remove"]:
        for field in ("must_have", "preferred"):
            if key in prefs[field]:
                prefs[field].remove(key)
    for key in add["must"]:
        if key in prefs["preferred"]:
            prefs["preferred"].remove(key)
        if key not in prefs["must_have"]:
            prefs["must_have"].append(key)
    for key in add["preferred"]:
        if key not in prefs["must_have"] and key not in prefs["preferred"]:
            prefs["preferred"].append(key)
    if add["brands"]:
        prefs["brand"] = add["brands"][0]
    for field in ("exclude_brands", "exclude_types", "exclude_features"):
        for v in add[field]:
            if v not in prefs[field]:
                prefs[field].append(v)
    # A brand that is now excluded cannot also be the preferred brand.
    if prefs["brand"] in prefs["exclude_brands"]:
        prefs["brand"] = None
    for dim, mult in add["priorities"].items():
        prefs["priorities"][dim] = max(prefs["priorities"].get(dim, 1.0), mult)
    for w in add["warnings"]:
        if w not in prefs["warnings"]:
            prefs["warnings"].append(w)
    return prefs


def parse_preferences(text: str, config: dict, brands) -> dict:
    """Convenience: first message -> normalized preference object."""
    return merge_preferences(empty_preferences(config), extract_preferences(text, config, brands))


# Refinement ------------------------------------------------------------------ #

_REFINEMENTS = {
    "cheaper": r"\b(?:cheaper|lower price|less expensive|reduce (?:the )?budget|lower (?:the )?budget|more affordable)\b",
    "battery": r"\b(?:better|longer|more|improve|bigger)\W+(?:\w+\W+){0,2}battery|battery\W+(?:\w+\W+){0,2}(?:better|longer)",
    "rating": r"\b(?:higher|better|top)\W+(?:\w+\W+){0,1}(?:rating|rated)|\bbest[- ]rated\b",
    "lightweight": r"\b(?:lighter|more lightweight|lightweight)\b",
    "features": r"\b(?:more features|feature[- ]rich|extra features)\b",
    "anc": r"\b(?:better|stronger|improve|best|more)\W+(?:\w+\W+){0,2}(?:anc|noise[- ]cancel\w*)",
}


def _bump(prefs, dim, config):
    cur = prefs["priorities"].get(dim, 1.0)
    prefs["priorities"][dim] = min(cur * config["priority_step"], config["priority_cap"])


def update_preferences(prefs: dict, text: str, config: dict, brands, top_price=None):
    """Apply a follow-up message to existing preferences.

    Returns (new_prefs, notes) where notes describe what changed, so the UI can
    tell the shopper exactly how the shortlist was re-scored.
    """
    t = text.lower()
    new = copy.deepcopy(prefs)
    notes = []

    if re.search(_REFINEMENTS["cheaper"], t):
        base = new["budget"] or top_price
        if base:
            new["budget"] = int(base * config["budget_cut_on_cheaper"] // 100 * 100)
            notes.append(f"Lowered the budget to {inr(new['budget'])}")
        _bump(new, "price_value", config)
        notes.append("Gave price value more weight")
    if re.search(_REFINEMENTS["battery"], t):
        if "battery" not in new["preferred"] and "battery" not in new["must_have"]:
            new["preferred"].append("battery")
        _bump(new, "battery", config)
        notes.append("Gave battery life more weight")
    if re.search(_REFINEMENTS["rating"], t):
        cur = new["min_rating"]
        new["min_rating"] = round(min((cur + 0.2) if cur else config["higher_rating_floor"], 4.8), 1)
        _bump(new, "rating", config)
        notes.append(f"Now requiring a rating of {new['min_rating']} or higher")
    if re.search(_REFINEMENTS["lightweight"], t):
        if "lightweight" not in new["preferred"] and "lightweight" not in new["must_have"]:
            new["preferred"].append("lightweight")
        _bump(new, "feature_match", config)
        notes.append("Prioritised lightweight designs")
    if re.search(_REFINEMENTS["features"], t):
        _bump(new, "extra_features", config)
        notes.append("Gave extra features more weight")
    if re.search(_REFINEMENTS["anc"], t):
        # The catalogue records ANC as yes/no, so "better ANC" = require it and
        # let the rating (a proxy for quality) count for more.
        if "active_noise_cancellation" not in new["must_have"]:
            if "active_noise_cancellation" in new["preferred"]:
                new["preferred"].remove("active_noise_cancellation")
            new["must_have"].append("active_noise_cancellation")
            notes.append("Added must-have: ANC")
        _bump(new, "rating", config)
        notes.append("Gave rating more weight to favour the best ANC models")

    add = extract_preferences(text, config, brands)
    if add["budget"] and add["budget"] != new["budget"]:
        notes.append(f"Set the budget to {inr(add['budget'])}")
    for key in add["must"]:
        if key not in new["must_have"]:
            notes.append(f"Added must-have: {label(key, config)}")
    for key in add["preferred"]:
        if key not in new["must_have"] and key not in new["preferred"]:
            notes.append(f"Added preference: {label(key, config)}")
    for key in add["remove"]:
        notes.append(f"Dropped: {label(key, config)}")
    for b in add["exclude_brands"]:
        if b not in new["exclude_brands"]:
            notes.append(f"Excluded brand: {b}")
    for k in add["exclude_types"]:
        notes.append(f"Excluded type: {label(k, config)}")
    if add["brands"]:
        notes.append(f"Preferred brand: {add['brands'][0]}")
    new = merge_preferences(new, add)
    return new, list(dict.fromkeys(notes))


def describe_preferences(prefs: dict, config: dict) -> str:
    parts = []
    if prefs["budget"]:
        parts.append(f"Budget up to {inr(prefs['budget'])}")
    if prefs["must_have"]:
        parts.append("Must-have: " + ", ".join(label(k, config) for k in prefs["must_have"]))
    if prefs["preferred"]:
        parts.append("Preferred: " + ", ".join(label(k, config) for k in prefs["preferred"]))
    if prefs["brand"]:
        parts.append(f"Brand preference: {prefs['brand']}")
    if prefs["exclude_brands"]:
        parts.append("Excluding brands: " + ", ".join(prefs["exclude_brands"]))
    if prefs["exclude_types"]:
        parts.append("Excluding: " + ", ".join(label(k, config) for k in prefs["exclude_types"]))
    if "wireless" in prefs["exclude_features"]:
        parts.append("Wired only")
    if prefs["min_rating"]:
        parts.append(f"Rating ≥ {prefs['min_rating']}")
    return " · ".join(parts) if parts else "No preferences captured yet"


# --------------------------------------------------------------------------- #
# Filtering
# --------------------------------------------------------------------------- #


def _reject_reason(row, prefs, config, skip=()):
    """First hard constraint the product violates, or None. Order matches the diagram."""
    if "stock" not in skip and not row["in_stock"]:
        return "Out of stock"
    if "budget" not in skip and prefs["budget"] and row["price"] > prefs["budget"]:
        return f"Over budget ({inr(row['price'])} > {inr(prefs['budget'])})"
    for key in prefs["must_have"]:
        if f"must:{key}" not in skip and key not in row["feature_set"]:
            return f"Missing must-have: {label(key, config)}"
    if "brand" not in skip and row["brand"] in prefs["exclude_brands"]:
        return f"Excluded brand: {row['brand']}"
    if "type" not in skip and row["type"] in prefs["exclude_types"]:
        return f"Excluded type: {label(row['type'], config)}"
    if "feature" not in skip:
        for key in prefs["exclude_features"]:
            if key in row["feature_set"]:
                return f"Excluded feature: {label(key, config)}"
    if "rating" not in skip and prefs["min_rating"] and row["rating"] < prefs["min_rating"]:
        return f"Rating below {prefs['min_rating']}"
    return None


def filter_products(df: pd.DataFrame, prefs: dict, config: dict):
    if df.empty:
        return df.copy(), []
    reasons = df.apply(lambda r: _reject_reason(r, prefs, config), axis=1)
    keep = reasons.isna()
    eligible = df[keep].copy()
    rejected = [{"id": r["id"], "name": r["name"], "price": r["price"], "reason": reasons[i]}
                for i, r in df[~keep].iterrows()]
    return eligible, rejected


def filter_funnel(df: pd.DataFrame, prefs: dict, config: dict):
    """Step-by-step product counts as each hard constraint is applied in turn.

    Returns [(label, count), ...]. Only constraints the shopper actually set are
    shown, and the last count always equals the number of eligible products.
    """
    steps = [("Products in catalogue", len(df))]
    current = df

    def apply(label_text, mask):
        nonlocal current
        current = current[mask(current)]
        steps.append((label_text, len(current)))

    apply("In stock", lambda d: d["in_stock"])
    if prefs["budget"]:
        apply(f"Within budget ({inr(prefs['budget'])})", lambda d: d["price"] <= prefs["budget"])
    for key in prefs["must_have"]:
        apply(f"With {label(key, config)}", lambda d, k=key: d["feature_set"].apply(lambda s: k in s))
    if prefs["exclude_brands"]:
        apply("Brands allowed", lambda d: ~d["brand"].isin(prefs["exclude_brands"]))
    if prefs["exclude_types"]:
        apply("Types allowed", lambda d: ~d["type"].isin(prefs["exclude_types"]))
    for key in prefs["exclude_features"]:
        apply(f"Without {label(key, config)}", lambda d, k=key: ~d["feature_set"].apply(lambda s: k in s))
    if prefs["min_rating"]:
        apply(f"Rating ≥ {prefs['min_rating']}", lambda d: d["rating"] >= prefs["min_rating"])
    steps.append(("Eligible for scoring", len(current)))
    return steps


def relaxation_hints(df, prefs, config, limit=3):
    """When nothing is eligible, say which single constraint is the bottleneck."""
    base_skip = {"budget"}
    hints = []

    def passing(skip):
        return df[df.apply(lambda r: _reject_reason(r, prefs, config, skip=skip) is None, axis=1)]

    if prefs["budget"]:
        cand = passing(base_skip)
        if len(cand):
            cheapest = int(cand["price"].min())
            n = int((cand["price"] == cheapest).sum())
            hints.append((n, f"Raising your budget to {inr(cheapest)} would unlock {n} matching product(s)."))
    for key in prefs["must_have"]:
        n = len(passing({f"must:{key}"}))
        if n:
            hints.append((n, f"Dropping the must-have “{label(key, config)}” would leave {n} product(s)."))
    if prefs["exclude_brands"]:
        n = len(passing({"brand"}))
        if n:
            hints.append((n, f"Allowing the excluded brand(s) would leave {n} product(s)."))
    if prefs["exclude_types"]:
        n = len(passing({"type"}))
        if n:
            hints.append((n, f"Allowing {', '.join(label(k, config) for k in prefs['exclude_types'])} would leave {n} product(s)."))
    if prefs["min_rating"]:
        n = len(passing({"rating"}))
        if n:
            hints.append((n, f"Relaxing the minimum rating would leave {n} product(s)."))
    hints.sort(key=lambda h: -h[0])
    return [h[1] for h in hints[:limit]]


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #

DIM_LABELS = {
    "feature_match": "match with your requested features",
    "rating": "customer rating",
    "battery": "battery life",
    "price_value": "price value",
    "extra_features": "extra features",
}


def effective_weights(prefs: dict, config: dict) -> dict:
    """Config weights x the shopper's priority multipliers, re-normalised to 1."""
    w = {k: v * prefs["priorities"].get(k, 1.0) for k, v in config["weights"].items()}
    if "wireless" in prefs["exclude_features"]:
        w["battery"] = 0.0  # wired products have no battery to compare
    total = sum(w.values())
    return {k: v / total for k, v in w.items()}


def _clip(x):
    return max(0.0, min(1.0, x))


def _has(key, row, config):
    if key == "battery":
        return row["battery_hours"] >= config["battery_good_hours"]
    return key in row["feature_set"]


def score_products(eligible: pd.DataFrame, prefs: dict, config: dict, catalogue_max_price: float):
    weights = effective_weights(prefs, config)
    ceiling = prefs["budget"] or catalogue_max_price
    scored = []
    for _, r in eligible.iterrows():
        matched_pref = [k for k in prefs["preferred"] if _has(k, r, config)]
        unmatched_pref = [k for k in prefs["preferred"] if k not in matched_pref]
        total = len(prefs["must_have"]) + len(prefs["preferred"])
        extras = [f for f in config["bonus_features"] if f in r["feature_set"]]
        subs = {
            "feature_match": 1.0 if total == 0 else (len(prefs["must_have"]) + len(matched_pref)) / total,
            "rating": _clip((r["rating"] - 3.0) / 2.0),
            "battery": _clip(r["battery_hours"] / config["battery_max_hours"]),
            "price_value": _clip(1 - r["price"] / ceiling),
            "extra_features": _clip(len(extras) / config["extra_features_cap"]),
        }
        points = {k: weights[k] * subs[k] * 100 for k in weights}
        brand_pts = config["brand_bonus"] * 100 if prefs["brand"] and r["brand"] == prefs["brand"] else 0.0
        score = min(100.0, sum(points.values()) + brand_pts)
        scored.append({
            "product": r, "score": round(score, 1), "subscores": subs, "points": points,
            "brand_points": brand_pts, "matched_preferred": matched_pref,
            "unmatched_preferred": unmatched_pref, "extras": extras,
        })
    scored.sort(key=lambda s: (-s["score"], -s["product"]["rating"], s["product"]["price"]))
    return scored, weights


# --------------------------------------------------------------------------- #
# Explanation
# --------------------------------------------------------------------------- #


def _tradeoffs(rec, rank, top, pool, prefs, config):
    p = rec["product"]
    notes = []
    for key in rec["unmatched_preferred"]:
        notes.append(f"Doesn't meet your preference for {label(key, config)}"
                     + (f" ({int(p['battery_hours'])} h battery)" if key == "battery" else ""))
    if prefs["budget"] and p["price"] >= 0.9 * prefs["budget"]:
        notes.append(f"Priced close to your {inr(prefs['budget'])} limit")
    wireless_hours = [s["product"]["battery_hours"] for s in pool if s["product"]["battery_hours"] > 0]
    if p["battery_hours"] > 0 and wireless_hours:
        median = float(pd.Series(wireless_hours).median())
        if median - p["battery_hours"] >= 8:
            notes.append(f"Battery ({int(p['battery_hours'])} h) is shorter than the typical {int(median)} h of similar options")
    others = [o for i, o in enumerate(top) if i != rank]
    lacking = [f for f in config["bonus_features"]
               if f not in p["feature_set"] and any(f in o["product"]["feature_set"] for o in others)]
    if lacking:
        notes.append("No " + ", ".join(label(f, config) for f in lacking[:3]) + " (offered by other top picks)")
    if p["rating"] < 4.2:
        notes.append(f"Rating of {p['rating']} is modest")
    if "lightweight" not in p["feature_set"] and p["type"] == "over_ear" and p["weight_g"] >= 290:
        notes.append(f"Heavier build ({int(p['weight_g'])} g)")
    if rank > 0:
        diff = p["price"] - top[0]["product"]["price"]
        if diff > 0:
            notes.append(f"Costs {inr(diff)} more than the #1 pick")
    if not notes:
        notes.append("No significant drawbacks compared with the other shortlisted options")
    return notes


def _reason(rec, rank, prefs, config):
    p = rec["product"]
    strong = sorted((k for k, v in rec["subscores"].items() if v >= 0.6 and k != "feature_match"),
                    key=lambda k: -rec["points"][k])[:2]
    bits = []
    if prefs["must_have"]:
        bits.append(f"meets all {len(prefs['must_have'])} of your must-haves")
    if prefs["preferred"] and rec["matched_preferred"]:
        bits.append(f"covers {len(rec['matched_preferred'])} of {len(prefs['preferred'])} preferences")
    if strong:
        bits.append("scores well on " + " and ".join(DIM_LABELS[k] for k in strong))
    if rec["brand_points"]:
        bits.append(f"is from your preferred brand {p['brand']}")
    lead = "Highest overall score" if rank == 0 else f"Ranked #{rank + 1}"
    return f"{lead} ({rec['score']}/100): " + (", ".join(bits) if bits else "a balanced all-rounder") + "."


def recommend(prefs: dict, products: pd.DataFrame, config: dict) -> dict:
    eligible, rejected = filter_products(products, prefs, config)
    scored, weights = score_products(eligible, prefs, config, float(products["price"].max()))
    top = scored[: config["top_n"]]
    recs = []
    for rank, rec in enumerate(top):
        p = rec["product"]
        matched = [label(k, config) for k in prefs["must_have"]]
        matched += [label(k, config) for k in rec["matched_preferred"]]
        if rec["brand_points"]:
            matched.append(f"{p['brand']} (preferred brand)")
        rec = dict(rec)
        rec.update({
            "rank": rank + 1,
            "matched": matched,
            "tradeoffs": _tradeoffs(rec, rank, top, scored, prefs, config),
            "reason": _reason(rec, rank, prefs, config),
            "also_has": [label(f, config) for f in rec["extras"]
                         if f not in prefs["must_have"] and f not in rec["matched_preferred"]],
            "budget_left": (prefs["budget"] - p["price"]) if prefs["budget"] else None,
        })
        rec["checks"] = checklist(rec, prefs, config)
        recs.append(rec)
    return {
        "prefs": prefs,
        "top": recs,
        "eligible_count": len(eligible),
        "ranked": scored,
        "rejected": rejected,
        "funnel": filter_funnel(products, prefs, config),
        "weights": weights,
        "hints": [] if recs else relaxation_hints(products[products["in_stock"]], prefs, config),
    }


# --------------------------------------------------------------------------- #
# Bonus: side-by-side comparison card
# --------------------------------------------------------------------------- #


def comparison_table(recs, config) -> pd.DataFrame:
    if not recs:
        return pd.DataFrame()
    P = [r["product"] for r in recs]
    best_price = min(p["price"] for p in P)
    best_rating = max(p["rating"] for p in P)
    best_batt = max(p["battery_hours"] for p in P)
    best_weight = min(p["weight_g"] for p in P)
    best_score = max(r["score"] for r in recs)

    def star(cond, text):
        return f"{text} ★" if cond else text

    cols = {}
    for r, p in zip(recs, P):
        cols[f"#{r['rank']} {p['name']}"] = {
            "Price": star(p["price"] == best_price, inr(p["price"])),
            "Rating": star(p["rating"] == best_rating, f"{p['rating']} / 5"),
            "Battery": star(p["battery_hours"] == best_batt, f"{int(p['battery_hours'])} h" if p["battery_hours"] else "Wired"),
            "ANC": "✓" if "active_noise_cancellation" in p["feature_set"] else "✗",
            "Wireless": "✓" if "wireless" in p["feature_set"] else "✗",
            "Weight": star(p["weight_g"] == best_weight, f"{int(p['weight_g'])} g"),
            "Type": label(p["type"], config),
            "Score": star(r["score"] == best_score, f"{r['score']} / 100"),
            "Matched": ", ".join(r["matched"]) or "-",
            "Also has": ", ".join(r["also_has"]) or "-",
            "Main trade-off": r["tradeoffs"][0],
        }
    return pd.DataFrame(cols)


# --------------------------------------------------------------------------- #
# Explainability: "Why this product?" checklist
# --------------------------------------------------------------------------- #


def checklist(rec: dict, prefs: dict, config: dict) -> list:
    """[(ok, text)] lines such as '✓ Within your ₹5,000 budget'. Warnings come from trade-offs."""
    p = rec["product"]
    out = []
    if prefs["budget"]:
        left = prefs["budget"] - p["price"]
        out.append((True, f"Within your {inr(prefs['budget'])} budget ({inr(p['price'])}, {inr(left)} to spare)"))
    for key in prefs["must_have"]:
        out.append((True, label(key, config).capitalize() if key != "active_noise_cancellation" else "ANC"))
    for key in rec["matched_preferred"]:
        if key != "battery":
            out.append((True, f"{label(key, config).capitalize()} (preferred)"))
    if p["battery_hours"] >= config["battery_good_hours"]:
        out.append((True, f"{int(p['battery_hours'])}-hour battery"))
    out.append((True, f"{p['rating']}★ customer rating"))
    if rec["brand_points"]:
        out.append((True, f"From your preferred brand, {p['brand']}"))
    return out


# --------------------------------------------------------------------------- #
# "Why not this product?"
# --------------------------------------------------------------------------- #

_WHY_NOT = re.compile(r"\bwhy\s+(?:not|isn'?t|wasn'?t|didn'?t|no)\b|\bwhy\s+(?:is|was)\b.*\bnot\b")


def is_why_not(text: str) -> bool:
    return bool(_WHY_NOT.search(text.lower()))


def find_product_in_text(text: str, products: pd.DataFrame):
    """Product row whose full name (or model name) appears in the text, longest match wins."""
    t = text.lower()
    best, best_len = None, 0
    for _, r in products.iterrows():
        name = r["name"].lower()
        model = name[len(r["brand"]):].strip()
        for cand in (name, model):
            if len(cand) > best_len and re.search(r"(?<![a-z0-9])" + re.escape(cand) + r"(?![a-z0-9])", t):
                best, best_len = r, len(cand)
    return best


def reject_reasons(row, prefs: dict, config: dict) -> list:
    """Every hard constraint a product violates (the filter itself reports only the first)."""
    out = []
    if not row["in_stock"]:
        out.append("It is out of stock")
    if prefs["budget"] and row["price"] > prefs["budget"]:
        out.append(f"It exceeds your budget by {inr(row['price'] - prefs['budget'])} "
                   f"({inr(row['price'])} vs {inr(prefs['budget'])})")
    for key in prefs["must_have"]:
        if key not in row["feature_set"]:
            out.append(f"It doesn't have {label(key, config)}, which you marked as a must-have")
    if row["brand"] in prefs["exclude_brands"]:
        out.append(f"You asked to exclude {row['brand']}")
    if row["type"] in prefs["exclude_types"]:
        out.append(f"You asked to exclude {label(row['type'], config)} headphones")
    for key in prefs["exclude_features"]:
        if key in row["feature_set"]:
            out.append("It is wireless and you asked for wired" if key == "wireless"
                       else f"It has {label(key, config)}, which you excluded")
    if prefs["min_rating"] and row["rating"] < prefs["min_rating"]:
        out.append(f"Its rating ({row['rating']}) is below your minimum of {prefs['min_rating']}")
    return out


def why_not(product, result: dict, config: dict) -> dict:
    """Explain why one product is (not) in the top picks.

    status: 'recommended' | 'filtered' | 'outranked'
    """
    prefs = result["prefs"]
    name = product["name"]
    for r in result["top"]:
        if r["product"]["id"] == product["id"]:
            return {"status": "recommended", "headline": f"{name} is already one of your picks (#{r['rank']}).",
                    "details": [r["reason"]]}
    reasons = reject_reasons(product, prefs, config)
    if reasons:
        first = reasons[0][0].lower() + reasons[0][1:]
        extra = f" (and {len(reasons) - 1} more issue{'s' if len(reasons) > 2 else ''})" if len(reasons) > 1 else ""
        return {"status": "filtered", "headline": f"{name} wasn't recommended because {first}{extra}.",
                "details": reasons[1:]}
    mine = next((s for s in result["ranked"] if s["product"]["id"] == product["id"]), None)
    if mine and result["top"]:
        bar = result["top"][-1]
        gaps = sorted(((bar["points"][k] - mine["points"][k], k) for k in mine["points"]), reverse=True)
        gap_lines = [f"{DIM_LABELS[k]}: {d:.1f} points behind the #{bar['rank']} pick" for d, k in gaps if d > 0.4][:3]
        if bar["brand_points"] and not mine["brand_points"]:
            gap_lines.append("not from your preferred brand")
        return {"status": "outranked",
                "headline": (f"{name} passes every filter but scored {mine['score']} against {bar['score']} "
                             f"for the #{bar['rank']} pick."),
                "details": gap_lines or ["It is very close; the tie was broken on rating and price."]}
    return {"status": "outranked", "headline": f"{name} didn't make the shortlist.", "details": []}


def near_misses(result: dict, products: pd.DataFrame, config: dict, n: int = 3) -> list:
    """Best-rated products that fail exactly one constraint ('almost made it')."""
    prefs = result["prefs"]
    top_ids = {r["product"]["id"] for r in result["top"]}
    found = []
    for _, row in products.iterrows():
        if row["id"] in top_ids:
            continue
        reasons = reject_reasons(row, prefs, config)
        if len(reasons) == 1:
            found.append({"product": row, "reason": reasons[0]})
    found.sort(key=lambda f: (-f["product"]["rating"], f["product"]["price"]))
    return found[:n]


# --------------------------------------------------------------------------- #
# Smart budget alternatives
# --------------------------------------------------------------------------- #


def smart_alternatives(result: dict, products: pd.DataFrame, config: dict) -> dict:
    """Never just say 'no results'.

    saver   - best product at least 15% cheaper than the #1 pick (what you give up)
    stretch - better-rated options slightly above budget (or the cheapest ones if nothing fits)
    relaxed - when nothing fits: best products if one must-have is relaxed
    """
    prefs = result["prefs"]
    top = result["top"]
    out = {"saver": None, "stretch": [], "relaxed": []}
    max_price = float(products["price"].max())

    if top:
        best = top[0]
        cheaper = [s for s in result["ranked"]
                   if s["product"]["price"] <= best["product"]["price"] * config["budget_cut_on_cheaper"]]
        if cheaper:
            s = cheaper[0]
            p, b = s["product"], best["product"]
            bits = [f"saves {inr(b['price'] - p['price'])}",
                    f"rating {p['rating'] - b['rating']:+.1f}★"]
            if p["battery_hours"] and b["battery_hours"]:
                bits.append(f"battery {int(p['battery_hours'] - b['battery_hours']):+d} h")
            out["saver"] = {"product": p, "score": s["score"], "note": "Compared with your #1 pick: " + ", ".join(bits)}

    if prefs["budget"]:
        free = copy.deepcopy(prefs)
        free["budget"] = None
        eligible, _ = filter_products(products, free, config)
        above = eligible[eligible["price"] > prefs["budget"]]
        if top:
            above = above[(above["price"] <= prefs["budget"] * 1.35) & (above["rating"] > top[0]["product"]["rating"])]
            above = above.sort_values(["rating", "price"], ascending=[False, True])
        else:
            above = above.sort_values(["price", "rating"], ascending=[True, False])
        for _, p in above.head(2).iterrows():
            extra = p["price"] - prefs["budget"]
            note = f"{inr(extra)} over budget"
            if top:
                note += f" · {p['rating'] - top[0]['product']['rating']:+.1f}★ vs your #1 pick"
            out["stretch"].append({"product": p, "note": note})

    if not top and prefs["must_have"]:
        seen = {}
        for key in prefs["must_have"]:
            relaxed = copy.deepcopy(prefs)
            relaxed["must_have"].remove(key)
            if key not in relaxed["preferred"]:
                relaxed["preferred"].append(key)
            eligible, _ = filter_products(products, relaxed, config)
            scored, _ = score_products(eligible, relaxed, config, max_price)
            for s in scored[:2]:
                pid = s["product"]["id"]
                if pid not in seen or s["score"] > seen[pid]["score"]:
                    seen[pid] = {"product": s["product"], "score": s["score"],
                                 "note": f"Everything except {label(key, config)}"}
        out["relaxed"] = sorted(seen.values(), key=lambda a: -a["score"])[:3]
    return out


# --------------------------------------------------------------------------- #
# Similar products
# --------------------------------------------------------------------------- #


def similar_products(product, products: pd.DataFrame, config: dict, prefs: dict | None = None, n: int = 3) -> list:
    """In-stock products most like `product` (shared features 60%, same type 20%, price closeness 20%)."""
    base = product["feature_set"]
    rows = []
    for _, r in products[products["in_stock"] & (products["id"] != product["id"])].iterrows():
        jaccard = len(base & r["feature_set"]) / len(base | r["feature_set"])
        price_close = 1 - min(1.0, abs(r["price"] - product["price"]) / max(product["price"], 1))
        sim = 0.6 * jaccard + 0.2 * (r["type"] == product["type"]) + 0.2 * price_close
        diff = r["price"] - product["price"]
        bits = [f"{inr(abs(diff))} {'cheaper' if diff < 0 else 'pricier'}" if diff else "same price",
                f"{r['rating'] - product['rating']:+.1f}★"]
        if r["battery_hours"] and product["battery_hours"]:
            bits.append(f"{int(r['battery_hours'] - product['battery_hours']):+d} h battery")
        rows.append({
            "product": r, "similarity": int(round(sim * 100)), "note": " · ".join(bits),
            "within_budget": None if not (prefs and prefs["budget"]) else bool(r["price"] <= prefs["budget"]),
        })
    rows.sort(key=lambda x: -x["similarity"])
    return rows[:n]
