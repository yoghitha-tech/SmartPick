"""SmartPick - conversational headphone recommender (Streamlit UI).

Run:  streamlit run app.py
"""
import streamlit as st

import recommender as rec
import visuals

st.set_page_config(page_title="SmartPick", page_icon="🎧", layout="wide")

CONFIG = rec.load_config()


@st.cache_data
def get_products():
    return rec.load_products(config=CONFIG)


@st.cache_data
def get_reviews():
    return rec.load_reviews()


PRODUCTS = get_products()
REVIEWS = get_reviews()
BRANDS = sorted(PRODUCTS["brand"].unique())
FEATURE_OPTIONS = [k for k in CONFIG["feature_aliases"] if k not in rec.TYPE_KEYS]
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}

EXAMPLES = [
    "I need wireless headphones under ₹5000 with ANC and good battery life.",
    "Gym earbuds under 3500, must be wireless and water resistant.",
    "Gaming headphones under 4500 with a mic, not Boltbeat.",
]
REFINEMENTS = {
    "💰 Make it cheaper": "make it cheaper",
    "🔋 Better battery": "better battery",
    "⭐ Higher rating": "higher rating",
    "🎧 Better ANC": "better ANC",
    "🪶 Lightweight": "more lightweight",
    "✨ More features": "more features",
}
PRIORITY_NAMES = {
    "battery": "Battery", "rating": "Rating", "price_value": "Price value",
    "feature_match": "Feature match", "extra_features": "Extra features",
}

st.markdown("""
<style>
.hero {background: linear-gradient(120deg,#1e1b4b,#4338ca 55%,#0ea5e9); padding: 26px 32px;
       border-radius: 18px; color: #fff; margin-bottom: 14px;}
.hero h1 {margin: 0; font-size: 2.1rem; color: #fff; padding: 0;}
.hero p {margin: 6px 0 0; opacity: .92; font-size: 1.02rem;}
.stars {color: #f59e0b; letter-spacing: 1px;}
</style>
<div class="hero">
  <h1>🎧 SmartPick</h1>
  <p>Tell me what you need in plain English. I filter, score and explain the best headphones for you,
     and tell you why the others didn't make it.</p>
</div>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------ state --
if "prefs" not in st.session_state:
    st.session_state.prefs = rec.empty_preferences(CONFIG)
    st.session_state.result = None
    st.session_state.messages = [{
        "role": "assistant",
        "content": "Hi! Tell me what you're looking for in headphones: budget, must-have features, "
                   "brand preferences, or things to avoid. You can also use the sidebar form, or ask "
                   "things like *\"why not Auralis Studio ANC Pro?\"*.",
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
        lines.append("No product fits all of those constraints, but the **Top picks** tab shows the closest options.")
        lines += [f"- {h}" for h in result["hints"]]
    st.session_state.messages.append({"role": "assistant", "content": "\n\n".join(lines)})


def answer_why_not(text):
    result = st.session_state.result
    product = rec.find_product_in_text(text, PRODUCTS)
    if product is None:
        msg = ("I couldn't find that product in the catalogue. Try the full name, e.g. "
               "*why not Zenwave Calm 700 ANC?* (the **Why not?** tab also has a picker).")
    elif result is None:
        msg = "Run a search first, then I can tell you why a product wasn't picked."
    else:
        w = rec.why_not(product, result, CONFIG)
        msg = f"**{w['headline']}**" + "".join(f"\n\n- {d}" for d in w["details"])
    st.session_state.messages.append({"role": "assistant", "content": msg})


def handle_text(text):
    st.session_state.messages.append({"role": "user", "content": text})
    if rec.is_why_not(text):
        answer_why_not(text)
        return
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
    st.caption("Fictional catalogue. Product images and customer reviews are generated for this demo.")


# ---------------------------------------------------------------- helpers --
def stars_html(value: float) -> str:
    full = int(round(value))
    return f'<span class="stars">{"★" * full}{"☆" * (5 - full)}</span>'


def product_mini(p, caption_lines):
    """Small product card: image, name, price, rating and a few caption lines."""
    st.markdown(visuals.image_html(p), unsafe_allow_html=True)
    st.markdown(f"**{p['name']}**")
    st.markdown(f"{rec.inr(p['price'])} · {stars_html(p['rating'])} {p['rating']}", unsafe_allow_html=True)
    for line in caption_lines:
        st.caption(line)


def reviews_block(p):
    s = rec.review_summary(REVIEWS, p["id"])
    if not s["count"]:
        st.caption("No reviews yet.")
        return
    st.markdown(f"{stars_html(s['mean'])} **{s['mean']}** from {s['count']} reviews "
                f"· {s['verified_pct']}% verified purchases", unsafe_allow_html=True)
    for star in (5, 4, 3, 2, 1):
        c1, c2 = st.columns([1, 5])
        c1.caption(f"{star} ★ ({s['dist'][star]})")
        c2.progress(s["dist"][star] / s["count"])
    for r in s["featured"]:
        st.markdown(f"{stars_html(r['stars'])} **{r['title']}**", unsafe_allow_html=True)
        st.write(r["text"])
        tag = " · Verified purchase" if r["verified_purchase"] else ""
        st.caption(f"{r['reviewer']} · {r['date']}{tag} · {r['helpful_votes']} found this helpful")
    st.caption("Sample reviews generated for this demo catalogue.")


def top_pick_card(col, r, result):
    p = r["product"]
    with col.container(border=True):
        st.markdown(visuals.image_html(p), unsafe_allow_html=True)
        st.markdown(f"### {MEDALS[r['rank']]} {p['name']}")
        n = rec.review_summary(REVIEWS, p["id"], featured=0)["count"]
        st.caption(f"{p['brand']} · {rec.label(p['type'], CONFIG)} · ID {p['id']}"
                   + (f" · {n} reviews" if n else ""))
        c1, c2, c3 = st.columns(3)
        c1.metric("Price", rec.inr(p["price"]))
        c2.metric("Rating", f"{p['rating']} ★")
        c3.metric("Score", f"{r['score']}")
        st.progress(min(r["score"], 100) / 100)
        st.markdown("**Why this product?**")
        for ok, text in r["checks"]:
            st.write(f"{'✅' if ok else '⚠️'} {text}")
        for t in r["tradeoffs"]:
            if t.startswith("No significant"):
                st.write(f"👍 {t}")
            else:
                st.write(f"⚠️ {t}")
        if r["also_has"]:
            st.caption("Also has: " + ", ".join(r["also_has"]))
        with st.expander("Score breakdown"):
            st.caption(r["reason"])
            for k, pts in r["points"].items():
                st.write(f"{rec.DIM_LABELS[k]}: **{pts:.1f}** pts "
                         f"(sub-score {r['subscores'][k]:.2f} × weight {result['weights'][k]:.0%})")
            if r["brand_points"]:
                st.write(f"preferred brand bonus: **{r['brand_points']:.1f}** pts")
        with st.expander("⭐ Customer reviews"):
            reviews_block(p)
        st.caption(p["description"])


def refine_buttons():
    st.markdown("**Refine your search**")
    cols = st.columns(len(REFINEMENTS))
    for col, (text, cmd) in zip(cols, REFINEMENTS.items()):
        col.button(text, on_click=handle_text, args=(cmd,))


def render_alternatives(result):
    alts = rec.smart_alternatives(result, PRODUCTS, CONFIG)
    shown = False

    if alts["relaxed"]:
        shown = True
        st.markdown("#### 🧭 Closest matches if you relax one requirement")
        st.caption("Nothing met every requirement, so here are the best products that miss only one.")
        cols = st.columns(len(alts["relaxed"]))
        for col, a in zip(cols, alts["relaxed"]):
            with col.container(border=True):
                product_mini(a["product"], [a["note"], f"Score {a['score']}"])
    if alts["stretch"]:
        shown = True
        where = ("Better-rated options just above your budget" if result["top"]
                 else "The cheapest options that meet everything, above your budget")
        st.markdown(f"#### 🚀 {where}")
        cols = st.columns(len(alts["stretch"]))
        for col, a in zip(cols, alts["stretch"]):
            with col.container(border=True):
                product_mini(a["product"], [a["note"]])
    if alts["saver"]:
        shown = True
        st.markdown("#### 💰 Smart budget alternative")
        st.caption("Want to spend less? This is the best option at least 15% cheaper than your #1 pick.")
        with st.container(border=True):
            c1, c2 = st.columns([1, 3])
            p = alts["saver"]["product"]
            with c1:
                st.markdown(visuals.image_html(p), unsafe_allow_html=True)
            with c2:
                st.markdown(f"**{p['name']}** · {rec.inr(p['price'])} · {p['rating']} ★ · score {alts['saver']['score']}")
                st.write(alts["saver"]["note"])
    if not shown:
        st.info("No cheaper or nearby alternatives found for these requirements.")


def render_similar(result):
    if not result["top"]:
        return
    best = result["top"][0]["product"]
    st.markdown(f"#### 🔁 Similar to your #1 pick, {best['name']}")
    sims = rec.similar_products(best, PRODUCTS, CONFIG, result["prefs"])
    cols = st.columns(len(sims))
    for col, s in zip(cols, sims):
        with col.container(border=True):
            lines = [f"{s['similarity']}% similar", s["note"]]
            if s["within_budget"] is False:
                lines.append("Above your budget")
            product_mini(s["product"], lines)


def render_why_not(result):
    st.markdown("#### ❓ Why not this product?")
    st.caption("Pick any product, or type *why not <product name>?* in the chat.")
    names = ["(choose a product)"] + [f"{r['name']}  ({rec.inr(r['price'])})" for _, r in PRODUCTS.iterrows()]
    choice = st.selectbox("Product", names, label_visibility="collapsed")
    if choice != names[0]:
        product = PRODUCTS.iloc[names.index(choice) - 1]
        w = rec.why_not(product, result, CONFIG)
        box = st.success if w["status"] == "recommended" else st.warning
        box(w["headline"])
        for d in w["details"]:
            st.write(f"• {d}")

    misses = rec.near_misses(result, PRODUCTS, CONFIG)
    if misses:
        st.markdown("##### Almost made it")
        cols = st.columns(len(misses))
        for col, m in zip(cols, misses):
            with col.container(border=True):
                product_mini(m["product"], [m["reason"]])


def pipeline_view(result):
    """User need -> filtering funnel -> scoring weights -> result."""
    prefs = result["prefs"]
    with st.container(border=True):
        st.markdown("##### 1 · Your requirements")
        boosted = [PRIORITY_NAMES[k] for k, v in prefs["priorities"].items() if v > 1 and k in PRIORITY_NAMES]
        excluded = list(prefs["exclude_brands"]) + [rec.label(k, CONFIG) for k in prefs["exclude_types"]]
        need = {
            "Budget": rec.inr(prefs["budget"]) if prefs["budget"] else "No limit",
            "Must have": ", ".join(rec.label(k, CONFIG) for k in prefs["must_have"]) or "None",
            "Preference": ", ".join(rec.label(k, CONFIG) for k in prefs["preferred"]) or "None",
            "Priority": ", ".join(boosted) or "Balanced",
            "Brand": prefs["brand"] or "Any",
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
        st.markdown("##### 3 · Ranking weights")
        for k, w in sorted(result["weights"].items(), key=lambda kv: -kv[1]):
            arrow = " ⬆️" if prefs["priorities"].get(k, 1.0) > 1 else ""
            st.write(f"{PRIORITY_NAMES[k]}{arrow}: **{w:.0%}**")
            st.progress(min(w, 1.0))

        st.markdown("⬇️")
        st.markdown("##### 4 · Top 3")
        if result["top"]:
            for r in result["top"]:
                st.write(f"{MEDALS[r['rank']]} **{r['product']['name']}**: {r['score']:.0f}%")
        else:
            st.write("No product passed every filter.")

    with st.expander(f"Why were {len(result['rejected'])} products filtered out?"):
        rows = []
        for _, row in PRODUCTS.iterrows():
            reasons = rec.reject_reasons(row, prefs, CONFIG)
            if reasons:
                rows.append({"Product": row["name"], "Price": rec.inr(row["price"]), "Why not": "; ".join(reasons)})
        st.dataframe(rows, hide_index=True)
    with st.expander("Normalized filter object"):
        st.json({k: v for k, v in prefs.items() if k != "warnings"})


# ------------------------------------------------------------------- main --
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
    tab_top, tab_cmp, tab_why, tab_alt, tab_how = st.tabs(
        ["🏆 Top picks", "⚖️ Compare", "❓ Why not?", "💡 Alternatives & similar", "🧠 How we decided"])

    with tab_top:
        if not result["top"]:
            st.warning("Nothing matches every constraint right now.")
            for h in result["hints"]:
                st.write("• " + h)
            render_alternatives(result)
        else:
            cols = st.columns(len(result["top"]))
            for col, r in zip(cols, result["top"]):
                top_pick_card(col, r, result)
        refine_buttons()

    with tab_cmp:
        if result["top"]:
            st.dataframe(rec.comparison_table(result["top"], CONFIG))
            st.caption("★ = best value in that row")
        else:
            st.info("Nothing to compare yet.")

    with tab_why:
        render_why_not(result)

    with tab_alt:
        render_alternatives(result)
        render_similar(result)

    with tab_how:
        pipeline_view(result)

if prompt := st.chat_input("e.g. wireless headphones under 5k with ANC, avoid Boltbeat"):
    handle_text(prompt)
    st.rerun()
