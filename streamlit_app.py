import streamlit as st

st.title("🎈 My new app")
"""
Streamlit version of the multi-stage PV / FV valuation tool.

Run with:
    pip install streamlit
    streamlit run app.py

The valuation functions are identical to the CLI script -- only the
input()/print() layer is replaced by Streamlit widgets.
"""

import pandas as pd
import streamlit as st


# ----------------------------------------------------------------------
# Core valuation  (unchanged from the CLI script -- pure functions)
# ----------------------------------------------------------------------

def build_schedule(cf0, start_period, segments):
    schedule = []
    cf_prev = cf0
    j = 0
    for label, g, count in segments:
        for _ in range(count):
            j += 1
            cf = cf_prev * (1 + g)
            schedule.append({"t": start_period + (j - 1),
                             "label": label, "g": g, "cf": cf})
            cf_prev = cf
    cf_last = cf_prev
    node_time = start_period + j - 1
    return schedule, cf_last, node_time


def present_value(schedule, r, cf_last, node_time, perpetuity_g):
    pv = sum(row["cf"] / (1 + r) ** row["t"] for row in schedule)
    terminal_pv = 0.0
    if perpetuity_g is not None:
        cf_next = cf_last * (1 + perpetuity_g)
        tv = cf_next / (r - perpetuity_g)
        terminal_pv = tv / (1 + r) ** node_time
        pv += terminal_pv
    return pv, terminal_pv


def future_value(schedule, r):
    if not schedule:
        return None, None
    horizon = max(row["t"] for row in schedule)
    fv = sum(row["cf"] * (1 + r) ** (horizon - row["t"]) for row in schedule)
    return fv, horizon


# ----------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------

st.title("Multi-stage PV / FV calculator")

# 1) Solve for PV or FV
solve_for = st.radio("Solve for", ["PV", "FV"], horizontal=True)

# 2) CF0 and starting period
col1, col2 = st.columns(2)
cf0 = col1.number_input("CF0 (base cash flow at time 0)", value=100.0, step=1.0)
start_period = col2.number_input("Time index of first cash flow",
                                 min_value=0, value=1, step=1)

# 3) Number of discrete forecast periods
n_periods = st.number_input("Number of discrete forecast periods (N)",
                            min_value=0, value=5, step=1)

# 4) Growth phases (last one is the terminal phase)
n_phases = st.number_input("Number of growth phases (K)",
                           min_value=1, max_value=int(n_periods) + 1,
                           value=min(2, int(n_periods) + 1), step=1)

segments = []
perpetuity_g = None
is_perpetuity = False
used = 0

for i in range(1, int(n_phases) + 1):
    is_last = (i == n_phases)
    label = f"Phase {i}" + ("  (terminal)" if is_last else "")
    with st.expander(label, expanded=True):
        g = st.number_input(f"Phase {i} growth rate (%)",
                            value=10.0 if i == 1 else 3.0,
                            step=0.5, key=f"g{i}") / 100.0

        if not is_last:
            interior_after = (int(n_phases) - 1) - i
            max_len = int(n_periods) - used - interior_after
            length = st.number_input(
                f"Phase {i} length (1 to {max_len})",
                min_value=1, max_value=max(max_len, 1),
                value=min(1, max_len), step=1, key=f"len{i}")
            used += int(length)
            segments.append((str(i), g, int(length)))
        else:
            rem = int(n_periods) - used
            t_type = st.radio(f"Phase {i} type", ["perpetuity", "annuity"],
                              horizontal=True, key=f"type{i}")
            if t_type == "perpetuity":
                is_perpetuity = True
                perpetuity_g = g
                if rem > 0:
                    segments.append(("T", g, rem))
                st.caption(f"{rem} discrete period(s) at {g*100:.4g}%, "
                           f"then grows forever at {g*100:.4g}%.")
            else:  # annuity
                if rem > 0:
                    ann_len = rem
                    st.caption(f"Annuity lasts the remaining {rem} period(s).")
                else:
                    ann_len = int(st.number_input(
                        "Annuity length in periods", min_value=1, value=3,
                        step=1, key=f"annlen{i}"))
                segments.append(("T", g, ann_len))

# 5) Discount rate
r = st.number_input("Discount rate (%)", value=8.0, step=0.5) / 100.0

# ---- validation that widgets can't express on their own ----
if is_perpetuity and r <= perpetuity_g:
    st.error(f"For a growing perpetuity the discount rate must exceed the "
             f"terminal growth rate ({perpetuity_g*100:.4g}%).")
    st.stop()

# ---- compute ----
schedule, cf_last, node_time = build_schedule(cf0, int(start_period), segments)

st.subheader("Cash-flow schedule")
st.write(f"CF0 (seed, not discounted): {cf0:,.2f}  |  "
         f"discrete periods used: {used} of {int(n_periods)}")
if schedule:
    df = pd.DataFrame([
        {"t": row["t"], "stage": row["label"],
         "growth %": round(row["g"] * 100, 3),
         "cash flow": round(row["cf"], 2)}
        for row in schedule
    ])
    st.dataframe(df, hide_index=True, use_container_width=True)
else:
    st.write("No enumerated cash flows; value comes entirely from the perpetuity.")

st.subheader("Result")
if solve_for == "PV":
    pv, terminal_pv = present_value(schedule, r, cf_last, node_time, perpetuity_g)
    if is_perpetuity:
        c1, c2 = st.columns(2)
        c1.metric("PV of cash flows", f"{pv - terminal_pv:,.2f}")
        c2.metric(f"PV of perpetuity (@ t={node_time})", f"{terminal_pv:,.2f}")
    st.metric("Present Value (PV)", f"{pv:,.2f}")
else:
    if is_perpetuity:
        st.warning("A growing perpetuity has infinite Future Value; the "
                   "perpetuity tail is excluded and FV covers the finite "
                   "cash flows only.")
    fv, horizon = future_value(schedule, r)
    if fv is None:
        st.info("No finite cash flows to compound (perpetuity only) -> "
                "FV is undefined/infinite.")
    else:
        st.metric(f"Future Value (FV), compounded to t={horizon}", f"{fv:,.2f}")

with st.expander("Formulas used"):
    st.latex(r"CF_t = CF_{t-1}\,(1+g)")
    st.latex(r"PV_t = \frac{CF_t}{(1+r)^t} \qquad FV_t = CF_t\,(1+r)^{T-t}")
    st.latex(r"TV_M = \frac{CF_M(1+g)}{r-g}, \quad "
             r"PV_{term} = \frac{TV_M}{(1+r)^M} \quad (r>g)")
    st.latex(r"PV_{annuity} = \frac{C}{r-g}\left[1-\left(\frac{1+g}{1+r}\right)^L\right]")
