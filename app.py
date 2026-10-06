"""SmartPick - conversational headphone recommender (Streamlit UI).

Run:  streamlit run app.py
"""
import streamlit as st

import recommender as rec

st.set_page_config(page_title="SmartPick", page_icon="🎧", layout="wide")

CONFIG = rec.load_config()


@st.cache_data
def get_products():
    return rec.load_products(config=CONFIG)


PRODUCTS = get_products()
BRANDS = sorted(PRODUCTS["brand"].unique())
FEATURE_OPTIONS = [k for k in CONFIG["feature_aliases"] if k not in rec.TYPE_KEYS]
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}

EXAMPLES = [
    "I need wireless headphones under ₹5000 with ANC and good battery life.",
    "Gym earbuds under 3500, must be wireless and water resistant.",
    "Gaming headphones under 4500 with a mic, not Boltbeat.",
]
REFINEMENTS = {
    "💸 Make it cheaper": "make it cheaper",
    "🔋 Better battery": "better battery",
    "⭐ Higher rating": "higher rating",
    "🪶 More lightweight": "more lightweight",
    "✨ More features": "more features",
}

# ------------------------------------------------------------------ state --
if "prefs" not in st.session_state:
    st.session_state.prefs = rec.empty_preferences(CONFIG)
    st.session_state.result = None
    st.session_state.messages = [{
        "role": "assistant",
        "content": "Hi! Tell me what you're looking for in headphones: budget, must-have features, "
                   "brand preferences, or things to avoid. You can also use the sidebar form.",
    }]


def run_and_reply(prefs, notes=None):
    st.session_state.prefs = prefs
    result = rec.recommend(prefs, PRODUCTS, CONFIG)
    st.session_state.result = result

    lines = []
    if notes:
        lines.append("**Updated:** " + "; ".join(notes) + ".")
    lines.append("**I understood:** " + rec.describe_preferences(prefs, CONFIG))
    for w in prefs["warnings"]:
        lines.append(f"⚠️ {w}")
    if result["top"]:
        names = ", ".join(f"{MEDALS[r['rank']]} {r['product']['name']}" for r in result["top"])
        lines.append(f"{result['eligible_count']} products fit. Top picks: {names}.")
    else:
        lines.append("No product fits all of those constraints.")
        lines += [f"- {h}" for h in result["hints"]]
    st.session_state.messages.append({"role": "assistant", "content": "\n\n".join(lines)})


def handle_text(text):
    st.session_state.messages.append({"role": "user", "content": text})
    top_price = None
    if st.session_state.result and st.session_state.result["top"]:
        top_price = float(st.session_state.result["top"][0]["product"]["price"])
    prefs, notes = rec.update_preferences(st.session_state.prefs, text, CONFIG, BRANDS, top_price)
    run_and_reply(prefs, notes)


def reset():
    for key in ("prefs", "result", "messages"):
        st.session_state.pop(key, None)


# ---------------------------------------------------------------- sidebar --
with st.sidebar:
    st.header("Structured input")
    with st.form("structured"):
        budget = st.number_input("Budget (₹, 0 = no limit)", min_value=0, max_value=50000, value=0, step=500)
        must = st.multiselect("Must-have features", FEATURE_OPTIONS + list(rec.TYPE_KEYS),
                              format_func=lambda k: rec.label(k, CONFIG))
        pref = st.multiselect("Preferred features", FEATURE_OPTIONS + ["battery"],
                              format_func=lambda k: rec.label(k, CONFIG))
        brand = st.selectbox("Brand preference", ["(none)"] + BRANDS)
        ex_brands = st.multiselect("Exclude brands", BRANDS)
        ex_types = st.multiselect("Exclude types", list(rec.TYPE_KEYS),
                                  format_func=lambda k: rec.label(k, CONFIG))
        if st.form_submit_button("Apply preferences"):
            prefs = rec.build_preferences(CONFIG, budget, must, pref,
                                          None if brand == "(none)" else brand, ex_brands, ex_types)
            st.session_state.messages.append({"role": "user", "content": "Applied the structured form."})
            run_and_reply(prefs)
    st.button("🔄 Start over", on_click=reset)

    with st.expander("Scoring weights (config.json)"):
        for k, v in CONFIG["weights"].items():
            st.write(f"**{rec.DIM_LABELS[k].capitalize()}**: {v:.0%}")
        if st.session_state.result:
            st.caption("Effective weights after your priorities:")
            for k, v in st.session_state.result["weights"].items():
                st.write(f"{k.replace('_', ' ')}: {v:.0%}")

PRIORITY_NAMES = {
    "battery": "Battery", "rating": "Rating", "price_value": "Price value",
    "feature_match": "Feature match", "extra_features": "Extra features",
}


def pipeline_view(result):
    """User need -> filtering funnel -> scoring weights -> result."""
    prefs = result["prefs"]
    st.subheader("How we got these results")
    with st.container(border=True):
        st.markdown("##### 1 · User need")
        boosted = [PRIORITY_NAMES[k] for k, v in prefs["priorities"].items() if v > 1 and k in PRIORITY_NAMES]
        excluded = list(prefs["exclude_brands"]) + [rec.label(k, CONFIG) for k in prefs["exclude_types"]]
        need = {
            "Budget": rec.inr(prefs["budget"]) if prefs["budget"] else "No limit",
            "Must-have": ", ".join(rec.label(k, CONFIG) for k in prefs["must_have"]) or "None",
            "Priority": ", ".join(boosted) or "Balanced",
            "Excluded": ", ".join(excluded) or "None",
        }
        for k, v in need.items():
            st.write(f"**{k}:** {v}")

        st.markdown("⬇️")
        st.markdown("##### 2 · Filtering")
        funnel = result["funnel"]
        total = max(funnel[0][1], 1)
        for step, count in funnel:
            st.write(f"**{count}** · {step}")
            st.progress(count / total)

        st.markdown("⬇️")
        st.markdown("##### 3 · Scoring")
        for k, w in sorted(result["weights"].items(), key=lambda kv: -kv[1]):
            arrow = " ⬆️" if prefs["priorities"].get(k, 1.0) > 1 else ""
            st.write(f"{PRIORITY_NAMES[k]}{arrow}: **{w:.0%}**")
            st.progress(min(w, 1.0))

        st.markdown("⬇️")
        st.markdown("##### 4 · Result")
        if result["top"]:
            for r in result["top"]:
                st.write(f"{MEDALS[r['rank']]} **{r['product']['name']}** — {r['score']}")
        else:
            st.write("No product passed every filter.")


# ------------------------------------------------------------------- main --
st.title("🎧 SmartPick")
st.caption("A conversational headphone recommender with transparent scoring. "
           "Fictional catalogue, prices in ₹. No profiling, no dynamic pricing, no health claims.")

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

if st.session_state.result is None:
    st.write("Try an example:")
    cols = st.columns(len(EXAMPLES))
    for col, ex in zip(cols, EXAMPLES):
        col.button(ex, on_click=handle_text, args=(ex,))

result = st.session_state.result
if result:
    st.divider()
    st.subheader("Your top picks")
    if not result["top"]:
        st.warning("Nothing matches every constraint right now.")
        for h in result["hints"]:
            st.write("• " + h)
    else:
        cols = st.columns(len(result["top"]))
        for col, r in zip(cols, result["top"]):
            p = r["product"]
            with col.container(border=True):
                st.markdown(f"### {MEDALS[r['rank']]} {p['name']}")
                st.caption(f"{p['brand']} · {rec.label(p['type'], CONFIG)} · ID {p['id']}")
                c1, c2, c3 = st.columns(3)
                c1.metric("Price", rec.inr(p["price"]))
                c2.metric("Rating", f"{p['rating']} ★")
                c3.metric("Score", f"{r['score']}")
                st.progress(min(r["score"], 100) / 100)
                if r["budget_left"] is not None:
                    st.caption(f"{rec.inr(r['budget_left'])} under your budget")
                st.markdown("**Why it was picked**")
                st.write(r["reason"])
                st.markdown("**Matched features**")
                st.write(" ".join(f"✅ {m}" for m in r["matched"]) or "—")
                if r["also_has"]:
                    st.caption("Also has: " + ", ".join(r["also_has"]))
                st.markdown("**Trade-offs**")
                for t in r["tradeoffs"]:
                    st.write(f"⚠️ {t}")
                with st.expander("Score breakdown"):
                    for k, pts in r["points"].items():
                        st.write(f"{rec.DIM_LABELS[k]}: **{pts:.1f}** pts "
                                 f"(sub-score {r['subscores'][k]:.2f} × weight {result['weights'][k]:.0%})")
                    if r["brand_points"]:
                        st.write(f"preferred brand bonus: **{r['brand_points']:.1f}** pts")
                st.caption(p["description"])

        st.markdown("**Refine your search**")
        cols = st.columns(len(REFINEMENTS))
        for col, (text, cmd) in zip(cols, REFINEMENTS.items()):
            col.button(text, on_click=handle_text, args=(cmd,))

        if st.toggle("Show side-by-side comparison card", value=True):
            st.subheader("Comparison")
            st.dataframe(rec.comparison_table(result["top"], CONFIG))
            st.caption("★ = best value in that row")

    pipeline_view(result)

    with st.expander(f"Why were {len(result['rejected'])} products filtered out?"):
        rows = [{"Product": r["name"], "Price": rec.inr(r["price"]), "Reason": r["reason"]}
                for r in result["rejected"]]
        st.dataframe(rows, hide_index=True)
    with st.expander("Normalized filter object"):
        st.json({k: v for k, v in result["prefs"].items() if k != "warnings"})

if prompt := st.chat_input("e.g. wireless headphones under 5k with ANC, avoid Boltbeat"):
    handle_text(prompt)
    st.rerun()
