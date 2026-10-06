"""Run the 15 shopper scenarios through SmartPick and check the results.

For each scenario this verifies:
  1. PARSE   - the free-text request is normalized to the expected structured preferences
  2. FILTER  - no recommended product is out of stock, over budget, or violates a constraint
  3. SUITABLE- every recommended product is in the scenario's expected_suitable list
  4. TOP 3   - exactly min(3, number of suitable products) are returned (0 when nothing fits)

Run:  python evaluate.py
"""
import json
import sys
from pathlib import Path

import recommender as rec

BASE = Path(__file__).parent


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
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
