"""Run the 15 shopper scenarios through SmartPick and check the results.

For each scenario this verifies:
  1. PARSE   - the free-text request is normalized to the expected structured preferences
  2. FILTER  - no recommended product is out of stock, over budget, or violates a constraint
  3. SUITABLE- every recommended product is in the scenario's expected_suitable list
  4. TOP 3   - exactly min(3, number of suitable products) are returned (0 when nothing fits)

After the scenarios, extra checks cover the newer features: customer reviews,
product images, "why not?", near misses, budget alternatives, similar products,
the "better ANC" refinement and product lookup in chat.

Run:  python evaluate.py
"""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import recommender as rec
import visuals

BASE = Path(__file__).parent


def extra_checks(config, products, scenarios) -> int:
    """Checks for reviews, images, why-not, alternatives, similar products and refinements."""
    reviews = rec.load_reviews()
    brands = sorted(products["brand"].unique())
    bad = []

    def check(ok, msg):
        if not ok:
            bad.append(msg)

    # reviews: every product has some, and their mean matches the catalogue rating
    for _, p in products.iterrows():
        s = rec.review_summary(reviews, p["id"])
        check(s["count"] >= 10, f"{p['id']} has only {s['count']} reviews")
        check(s["mean"] is not None and abs(s["mean"] - p["rating"]) <= 0.06,
              f"{p['id']} review mean {s['mean']} != rating {p['rating']}")
        # reviews must not praise ANC when the product has none
        if "active_noise_cancellation" not in p["feature_set"]:
            check(not any("noise cancellation tunes" in r["text"] for r in s["featured"]),
                  f"{p['id']} review praises ANC it lacks")

    # images: valid SVG for every product
    for _, p in products.iterrows():
        try:
            ET.fromstring(visuals.product_svg(p))
        except ET.ParseError as exc:
            check(False, f"{p['id']} svg invalid: {exc}")
        check(visuals.image_html(p).startswith("<img src=\"data:image/svg+xml;base64,"), f"{p['id']} image tag")

    by_id = {s["id"]: s for s in scenarios}

    def run(sid):
        prefs = rec.parse_preferences(by_id[sid]["text"], config, brands)
        return rec.recommend(prefs, products, config)

    r1 = run("S01")
    # why not: over-budget product, a recommended product, an outranked product
    pricey = products[products["name"] == "Auralis Studio ANC Pro"].iloc[0]
    w = rec.why_not(pricey, r1, config)
    check(w["status"] == "filtered" and "exceeds your budget by ₹6,999" in w["headline"], f"why_not filtered: {w['headline']}")
    w = rec.why_not(r1["top"][0]["product"], r1, config)
    check(w["status"] == "recommended", "why_not recommended")
    outranked = next(s for s in r1["ranked"][config["top_n"]:])
    w = rec.why_not(outranked["product"], r1, config)
    check(w["status"] == "outranked" and "scored" in w["headline"], f"why_not outranked: {w['headline']}")

    # near misses: exactly one failing constraint each, none already recommended
    misses = rec.near_misses(r1, products, config)
    check(len(misses) > 0, "no near misses for S01")
    top_ids = {r["product"]["id"] for r in r1["top"]}
    for m in misses:
        check(len(rec.reject_reasons(m["product"], r1["prefs"], config)) == 1 and m["product"]["id"] not in top_ids,
              f"bad near miss {m['product']['id']}")

    # smart alternatives: cheaper saver is really cheaper and stays within budget
    alts = rec.smart_alternatives(r1, products, config)
    if alts["saver"]:
        check(alts["saver"]["product"]["price"] <= r1["top"][0]["product"]["price"] * config["budget_cut_on_cheaper"], "saver not cheaper")
    for a in alts["stretch"]:
        check(a["product"]["price"] > r1["prefs"]["budget"], "stretch pick is within budget")
    r13 = run("S13")  # no results: must still offer something
    alts = rec.smart_alternatives(r13, products, config)
    check(not r13["top"] and (alts["relaxed"] or alts["stretch"]), "S13 gives no alternatives")
    for a in alts["relaxed"]:
        check(a["product"]["in_stock"], "relaxed pick out of stock")

    # similar products
    best = r1["top"][0]["product"]
    sims = rec.similar_products(best, products, config, r1["prefs"])
    check(len(sims) == 3 and all(x["product"]["id"] != best["id"] for x in sims), "similar products")

    # refinements and chat helpers
    prefs, notes = rec.update_preferences(r1["prefs"], "better ANC", config, brands, 4000)
    check("active_noise_cancellation" in prefs["must_have"] and prefs["priorities"].get("rating", 1) > 1, "better ANC")
    check(rec.is_why_not("why not Zenwave Focus ANC?") and not rec.is_why_not("wireless under 5000"), "is_why_not")
    found = rec.find_product_in_text("why not zenwave focus anc?", products)
    check(found is not None and found["name"] == "Zenwave Focus ANC", "find_product_in_text")
    check(rec.find_product_in_text("why not AudioMax 3000", products) is None, "unknown product should not match")

    print("\nEXTRA CHECKS (reviews, images, why-not, alternatives, similar, refinements)")
    for b in bad:
        print(f"        ! {b}")
    print("[PASS] all extra checks" if not bad else f"[FAIL] {len(bad)} extra check(s) failed")
    return len(bad)


def main() -> int:
    config = rec.load_config()
    products = rec.load_products(config=config)
    brands = sorted(products["brand"].unique())
    scenarios = json.loads((BASE / "scenarios.json").read_text(encoding="utf-8"))
    failures = 0

    for s in scenarios:
        prefs = rec.parse_preferences(s["text"], config, brands)
        result = rec.recommend(prefs, products, config)
        top_ids = [r["product"]["id"] for r in result["top"]]
        problems = []

        # 1. parsing
        if prefs["budget"] != s["budget"]:
            problems.append(f"budget parsed {prefs['budget']} != {s['budget']}")
        if set(prefs["must_have"]) != set(s["must_have"]):
            problems.append(f"must_have {sorted(prefs['must_have'])} != {sorted(s['must_have'])}")
        if set(prefs["preferred"]) != set(s["preferred"]):
            problems.append(f"preferred {sorted(prefs['preferred'])} != {sorted(s['preferred'])}")
        if prefs["brand"] != s["brand"]:
            problems.append(f"brand {prefs['brand']} != {s['brand']}")
        for field in ("exclude_brands", "exclude_types", "exclude_features"):
            if set(prefs[field]) != set(s[field]):
                problems.append(f"{field} {prefs[field]} != {s[field]}")

        # 2 + 3. constraint safety / suitability
        for r in result["top"]:
            p = r["product"]
            if not p["in_stock"]:
                problems.append(f"{p['name']} is out of stock")
            if p["price"] > s["budget"]:
                problems.append(f"{p['name']} is over budget")
            if p["id"] not in s["expected_suitable"]:
                problems.append(f"{p['name']} not in expected_suitable")

        # funnel must end at the number of eligible products
        if result["funnel"][-1][1] != result["eligible_count"]:
            problems.append("funnel does not end at eligible_count")

        # 4. count
        want = min(config["top_n"], len(s["expected_suitable"]))
        if len(top_ids) != want:
            problems.append(f"returned {len(top_ids)} products, expected {want}")

        status = "PASS" if not problems else "FAIL"
        failures += bool(problems)
        names = ", ".join(f"{r['product']['name']} ({r['score']})" for r in result["top"]) or "none (see relax hints)"
        print(f"[{status}] {s['id']}: {s['text']}")
        print(f"        suitable={len(s['expected_suitable'])}  top3: {names}")
        for p in problems:
            print(f"        ! {p}")

    print(f"\n{len(scenarios) - failures}/{len(scenarios)} scenarios passed")
    extra_failures = extra_checks(config, products, scenarios)
    return 1 if (failures or extra_failures) else 0


if __name__ == "__main__":
    sys.exit(main())
