"""Generate the synthetic data for SmartPick.

Creates:
  products.csv    - 47 fictional headphone products
  scenarios.json  - 15 shopper scenarios (with expected suitable products)

Run:  python generate_data.py
"""
import csv
import json
from pathlib import Path

BASE = Path(__file__).parent
CONFIG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))

# brand, model, type, price (INR), rating, in_stock, battery_h (0 = wired), weight_g, features
RAW = [
    ("Auralis", "Studio ANC Pro", "over_ear", 11999, 4.7, True, 38, 265, "wireless,active_noise_cancellation,microphone,foldable,fast_charging,multipoint"),
    ("Auralis", "Air Lite", "over_ear", 3499, 4.2, True, 32, 215, "wireless,microphone,foldable"),
    ("Auralis", "Pulse ANC", "over_ear", 4799, 4.4, True, 40, 245, "wireless,active_noise_cancellation,microphone,fast_charging"),
    ("Auralis", "Buds Go", "in_ear", 1999, 4.0, True, 20, 9, "wireless,microphone,water_resistant"),
    ("Auralis", "Buds ANC", "in_ear", 5499, 4.5, False, 28, 10, "wireless,active_noise_cancellation,microphone,water_resistant,fast_charging,multipoint"),
    ("SonicNest", "Rumble 500", "over_ear", 2799, 4.1, True, 45, 290, "wireless,microphone,bass_boost,foldable"),
    ("SonicNest", "Rumble ANC", "over_ear", 4299, 4.3, True, 50, 280, "wireless,active_noise_cancellation,microphone,bass_boost,fast_charging"),
    ("SonicNest", "Wired Studio", "over_ear", 1499, 4.3, True, 0, 240, "microphone,foldable"),
    ("SonicNest", "Sprint Buds", "in_ear", 1299, 3.9, True, 18, 8, "wireless,microphone,water_resistant,low_latency"),
    ("SonicNest", "Rumble Mini", "on_ear", 1899, 4.0, True, 35, 170, "wireless,microphone,bass_boost,foldable"),
    ("BeatForge", "Gamer X1", "over_ear", 3999, 4.2, True, 30, 310, "wireless,microphone,low_latency,bass_boost"),
    ("BeatForge", "Gamer X2 Pro", "over_ear", 6499, 4.5, True, 35, 320, "wireless,active_noise_cancellation,microphone,low_latency,multipoint"),
    ("BeatForge", "Wired Arena", "over_ear", 2199, 4.2, True, 0, 300, "microphone,low_latency,bass_boost"),
    ("BeatForge", "Dash Buds", "in_ear", 2499, 4.1, True, 24, 10, "wireless,microphone,low_latency,water_resistant,fast_charging"),
    ("BeatForge", "Dash Neckband", "in_ear", 1599, 4.0, True, 30, 38, "wireless,microphone,water_resistant,fast_charging"),
    ("Zenwave", "Calm 700 ANC", "over_ear", 8999, 4.6, True, 45, 250, "wireless,active_noise_cancellation,microphone,foldable,multipoint,fast_charging"),
    ("Zenwave", "Calm 300", "over_ear", 2599, 4.0, True, 28, 230, "wireless,foldable"),
    ("Zenwave", "Focus ANC", "over_ear", 5999, 4.4, False, 42, 255, "wireless,active_noise_cancellation,microphone,multipoint"),
    ("Zenwave", "Whisper Buds", "in_ear", 3299, 4.3, True, 22, 9, "wireless,active_noise_cancellation,microphone,water_resistant"),
    ("Zenwave", "Whisper Buds Lite", "in_ear", 999, 3.8, True, 14, 8, "wireless,microphone"),
    ("PulseAudio", "Commuter 200", "on_ear", 2299, 4.1, True, 40, 175, "wireless,microphone,foldable,fast_charging"),
    ("PulseAudio", "Commuter ANC", "over_ear", 5299, 4.4, True, 48, 235, "wireless,active_noise_cancellation,microphone,foldable,fast_charging"),
    ("PulseAudio", "Run 5", "in_ear", 2999, 4.2, True, 16, 12, "wireless,microphone,water_resistant,fast_charging"),
    ("PulseAudio", "Run 5 Sport", "in_ear", 3699, 4.3, True, 20, 13, "wireless,microphone,water_resistant,fast_charging,multipoint"),
    ("PulseAudio", "Basic Wired", "in_ear", 599, 3.6, True, 0, 12, "microphone"),
    ("Echoline", "Horizon 1", "over_ear", 3199, 4.3, True, 36, 205, "wireless,microphone,foldable,fast_charging"),
    ("Echoline", "Horizon ANC", "over_ear", 5799, 4.5, True, 44, 225, "wireless,active_noise_cancellation,microphone,foldable,fast_charging,multipoint"),
    ("Echoline", "Horizon Max", "over_ear", 9499, 4.7, True, 55, 270, "wireless,active_noise_cancellation,microphone,foldable,multipoint,fast_charging"),
    ("Echoline", "Pocket Buds", "in_ear", 1799, 4.0, False, 18, 9, "wireless,microphone,water_resistant"),
    ("Echoline", "Pocket Buds ANC", "in_ear", 3999, 4.3, True, 24, 10, "wireless,active_noise_cancellation,microphone,water_resistant,fast_charging"),
    ("Tunely", "Everyday 100", "on_ear", 1199, 3.9, True, 30, 165, "wireless,microphone,foldable"),
    ("Tunely", "Everyday 200", "over_ear", 1999, 4.0, True, 34, 235, "wireless,microphone,foldable"),
    ("Tunely", "Everyday ANC", "over_ear", 3699, 4.2, True, 38, 240, "wireless,active_noise_cancellation,microphone"),
    ("Tunely", "Studio Wired", "over_ear", 2899, 4.4, True, 0, 255, "microphone,foldable"),
    ("Tunely", "Feather", "on_ear", 3599, 4.3, True, 32, 125, "wireless,microphone,foldable,fast_charging,multipoint"),
    ("Boltbeat", "Volt 1", "in_ear", 799, 3.7, True, 12, 8, "wireless,microphone"),
    ("Boltbeat", "Volt ANC", "in_ear", 2699, 4.0, True, 20, 9, "wireless,active_noise_cancellation,microphone,fast_charging"),
    ("Boltbeat", "Surge Over", "over_ear", 1799, 3.9, True, 30, 260, "wireless,microphone,bass_boost"),
    ("Boltbeat", "Surge ANC", "over_ear", 3299, 4.1, True, 36, 270, "wireless,active_noise_cancellation,microphone,bass_boost,fast_charging"),
    ("Boltbeat", "Surge Pro", "over_ear", 4999, 4.3, False, 42, 275, "wireless,active_noise_cancellation,microphone,bass_boost,multipoint,fast_charging"),
    ("Melodix", "Vinyl 1", "over_ear", 3999, 4.4, True, 28, 300, "wireless,microphone,foldable"),
    ("Melodix", "Vinyl ANC", "over_ear", 7499, 4.6, True, 40, 260, "wireless,active_noise_cancellation,microphone,foldable,multipoint,fast_charging"),
    ("Melodix", "Sprout", "on_ear", 1499, 4.0, True, 28, 160, "wireless,microphone,foldable,water_resistant"),
    ("Melodix", "Sprout ANC", "on_ear", 3399, 4.2, True, 34, 185, "wireless,active_noise_cancellation,microphone,foldable,fast_charging"),
    ("Clearsound", "Office 1", "over_ear", 4499, 4.5, True, 35, 200, "wireless,active_noise_cancellation,microphone,multipoint,fast_charging"),
    ("Clearsound", "Office Lite", "on_ear", 2399, 4.2, True, 32, 150, "wireless,microphone,multipoint,foldable"),
    ("Clearsound", "Office ANC Max", "over_ear", 10499, 4.6, False, 52, 230, "wireless,active_noise_cancellation,microphone,multipoint,fast_charging,foldable"),
]

TYPE_TEXT = {"over_ear": "over-ear", "on_ear": "on-ear", "in_ear": "in-ear"}
FEATURE_PHRASE = {
    "wireless": "Bluetooth connectivity",
    "active_noise_cancellation": "active noise cancellation",
    "microphone": "a built-in mic",
    "foldable": "a foldable frame",
    "fast_charging": "fast charging",
    "multipoint": "multipoint pairing",
    "water_resistant": "a sweat and splash resistant build",
    "bass_boost": "punchy bass tuning",
    "low_latency": "a low-latency mode",
}


def describe(typ, battery, feats):
    pieces = [FEATURE_PHRASE[f] for f in feats if f in FEATURE_PHRASE][:3]
    text = f"A {TYPE_TEXT[typ]} model with " + ", ".join(pieces)
    text += f". About {battery} h of playback." if battery else ". Wired, no charging needed."
    return text


def build_products():
    rows = []
    for i, (brand, model, typ, price, rating, stock, battery, weight, feats) in enumerate(RAW, 1):
        rows.append({
            "id": f"HP-{i:03d}",
            "name": f"{brand} {model}",
            "category": CONFIG["category"],
            "brand": brand,
            "type": typ,
            "price": price,
            "rating": rating,
            "stock_status": "in_stock" if stock else "out_of_stock",
            "battery_hours": battery,
            "weight_g": weight,
            "features": feats,
            "description": describe(typ, battery, feats.split(",")),
        })
    return rows


def derived_features(row):
    feats = set(row["features"].split(","))
    feats.add(row["type"])
    if row["weight_g"] <= CONFIG["lightweight_max_g"][row["type"]]:
        feats.add("lightweight")
    return feats


# Shopper scenarios. `text` is what a shopper would type; the structured fields
# are the ground-truth preferences that text should be normalized into.
SCENARIOS = [
    dict(text="I need wireless headphones under ₹5000 with ANC and good battery life.",
         budget=5000, must_have=["wireless", "active_noise_cancellation"], preferred=["battery"]),
    dict(text="Budget 3000, wireless over-ear headphones with a mic for calls.",
         budget=3000, must_have=["wireless", "over_ear", "microphone"], preferred=[]),
    dict(text="Gym earbuds under 3500, must be wireless and water resistant, lightweight preferred.",
         budget=3500, must_have=["in_ear", "wireless", "water_resistant"], preferred=["lightweight"]),
    dict(text="Gaming headphones under 4500 with a mic, not Boltbeat.",
         budget=4500, must_have=["low_latency", "microphone"], preferred=[], exclude_brands=["Boltbeat"]),
    dict(text="Best noise cancelling headphones under ₹10000, prefer Zenwave.",
         budget=10000, must_have=["active_noise_cancellation"], preferred=[], brand="Zenwave"),
    dict(text="Cheap wired headphones under 1500.",
         budget=1500, must_have=[], preferred=[], exclude_features=["wireless"]),
    dict(text="Wireless travel headphones under 4000, must be foldable and must have multipoint, lightweight is a bonus.",
         budget=4000, must_have=["wireless", "foldable", "multipoint"], preferred=["lightweight"]),
    dict(text="Wireless on-ear headphones under ₹2500 with a mic.",
         budget=2500, must_have=["wireless", "on_ear", "microphone"], preferred=[]),
    dict(text="Under 6000, ANC, over-ear, long battery, avoid Boltbeat and BeatForge.",
         budget=6000, must_have=["active_noise_cancellation", "over_ear"], preferred=["battery"],
         exclude_brands=["Boltbeat", "BeatForge"]),
    dict(text="Wireless earbuds with ANC under 4000, prefer water resistant, prefer Echoline.",
         budget=4000, must_have=["wireless", "in_ear", "active_noise_cancellation"], preferred=["water_resistant"], brand="Echoline"),
    dict(text="I want bass heavy wireless headphones under 3000.",
         budget=3000, must_have=["wireless"], preferred=["bass_boost"]),
    dict(text="Best rated wireless ANC headphones up to ₹12000, must have multipoint and fast charging.",
         budget=12000, must_have=["wireless", "active_noise_cancellation", "multipoint", "fast_charging"], preferred=[]),
    dict(text="Wireless headphones with ANC under ₹1000.",
         budget=1000, must_have=["wireless", "active_noise_cancellation"], preferred=[]),
    dict(text="Student on a tight budget: wireless headphones under 1500 with a mic.",
         budget=1500, must_have=["wireless", "microphone"], preferred=[]),
    dict(text="Wireless headphones under 5000 with ANC, but no in-ear.",
         budget=5000, must_have=["wireless", "active_noise_cancellation"], preferred=[], exclude_types=["in_ear"]),
]


def expected_suitable(scn, products):
    """Independent, deliberately simple hard-constraint check used as ground truth."""
    ok = []
    for p in products:
        feats = derived_features(p)
        if p["stock_status"] != "in_stock":
            continue
        if p["price"] > scn["budget"]:
            continue
        if not set(scn["must_have"]) <= feats:
            continue
        if p["brand"] in scn.get("exclude_brands", []):
            continue
        if p["type"] in scn.get("exclude_types", []):
            continue
        if any(f in feats for f in scn.get("exclude_features", [])):
            continue
        ok.append(p["id"])
    return ok


def main():
    products = build_products()
    with open(BASE / "products.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(products[0].keys()))
        writer.writeheader()
        writer.writerows(products)

    scenarios = []
    for i, s in enumerate(SCENARIOS, 1):
        s = {"id": f"S{i:02d}", **s}
        s.setdefault("brand", None)
        s.setdefault("exclude_brands", [])
        s.setdefault("exclude_types", [])
        s.setdefault("exclude_features", [])
        s["expected_suitable"] = expected_suitable(s, products)
        scenarios.append(s)
    (BASE / "scenarios.json").write_text(json.dumps(scenarios, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(products)} products and {len(scenarios)} scenarios.")


if __name__ == "__main__":
    main()
