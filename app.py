from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from survey_loader import load_model
from metrics import (
    METRICS,
    compute_matrix,
    drilldown,
    result_direction,
    selected_group_mask,
    score_distribution_counts,
    score_distribution_label,
    sort_matrix_rows,
    team_question_distribution,
)
from evidence import load_evidence, load_status, evidence_for_selection, relation_counts
from ui_helpers import extract_selected_cell

ROOT = Path(__file__).parent
DEFAULT_EXCEL = ROOT / "data" / "survey.xlsx"
EVIDENCE_PATH = ROOT / "data" / "evidence_links.jsonl"
STATUS_PATH = ROOT / "data" / "evidence_status.json"
MIN_GROUP_SIZE = 5

st.set_page_config(page_title="Survey | חוקר שאלות ו-Lineage", page_icon="🔎", layout="wide")
st.markdown("""
<style>
html, body, [class*="css"] { direction: rtl; text-align: right; }
[data-testid="stMetricValue"] { direction: ltr; text-align: right; }
.evidence-card {border:1px solid #d0d5dd; border-radius:12px; padding:12px; margin:8px 0; background:#ffffff;}
.support {border-right:6px solid #2e7d32;}
.contradict {border-right:6px solid #c62828;}
.context {border-right:6px solid #667085;}
.small-note {color:#667085; font-size:0.9rem;}
</style>
""", unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def cached_load(path: str, file_bytes: bytes | None):
    source = file_bytes if file_bytes is not None else path
    return load_model(source)

@st.cache_data(show_spinner=False)
def cached_evidence(path: str, file_bytes: bytes | None):
    return load_evidence(file_bytes if file_bytes is not None else path)


def html_text(value: object) -> str:
    return escape("" if value is None else str(value), quote=True)


def evidence_card_html(row: dict, css_class: str) -> str:
    response_id = "N/A" if pd.isna(row.get("response_id")) else f"R{int(row['response_id']):03d}"
    return (
        f"<div class='evidence-card {css_class}'><b>{html_text(row.get('evidence_span'))}</b><br>"
        f"{html_text(row.get('explanation'))}<br><span class='small-note'>"
        f"משיב {html_text(response_id)} · "
        f"וותק: {html_text(row.get('tenure'))} · "
        f"ציון אישי: {html_text(row.get('score'))} · "
        f"{html_text(row.get('relevance'))} · {html_text(row.get('confidence'))}<br>"
        f"{html_text(row.get('personal_alignment'))}</span></div>"
    )




st.title("🔎 חוקר שאלות, ציונים וסימוכין")
st.caption("בחירת תא מחזירה את הציונים שיצרו אותו, פילוחי ותק, אמירות תומכות/סותרות ו-lineage עד שורת המקור ב-Excel.")

with st.sidebar:
    st.header("מקור נתונים")
    uploaded = st.file_uploader("Excel מתקדם", type=["xlsx"])
    file_bytes = uploaded.getvalue() if uploaded else None
    source_name = uploaded.name if uploaded else DEFAULT_EXCEL.name
    st.caption(f"מקור פעיל: {source_name}")
    uploaded_evidence = st.file_uploader("Evidence JSONL תואם (אופציונלי)", type=["jsonl"])
    evidence_bytes = uploaded_evidence.getvalue() if uploaded_evidence else None
    st.divider()
    st.header("תצוגה")
    view_label = st.radio("רמת הסתכלות", ["כלל הענף", "לפי צוות", "לפי ותק", "צוות לפי ותק"])
    view = {"כלל הענף":"general", "לפי צוות":"team", "לפי ותק":"tenure", "צוות לפי ותק":"team_tenure"}[view_label]
    metric_label = st.selectbox("מדד בתאים", list(METRICS.values()), index=1)
    metric = next(key for key, value in METRICS.items() if value == metric_label)
    domain_label = st.selectbox("תחום", ["הכול", "הערכת ראש צוות", "אפקטיביות צוות", "איכות המשוב"])
    domain = {"הכול":"all", "הערכת ראש צוות":"manager", "אפקטיביות צוות":"team", "איכות המשוב":"feedback_quality"}[domain_label]
    min_group_size = st.number_input("מינימום משיבים", min_value=3, max_value=10, value=MIN_GROUP_SIZE)

if file_bytes is None and not DEFAULT_EXCEL.exists():
    st.info(
        "No private survey workbook was found. Upload an Excel file in the sidebar, "
        "or place the private workbook under data/ for local-only use."
    )
    st.stop()

responses, catalog, numeric, open_answers = cached_load(str(DEFAULT_EXCEL), file_bytes)
teams = sorted(responses["team"].astype(str).unique())
selected_team = None
if view == "team_tenure":
    selected_team = st.sidebar.selectbox("צוות", teams)

# Load the semantic evidence before building the heatmap so hover can show
# supporting and contradicting statement counts for every visible cell.
if uploaded and evidence_bytes is None:
    evidence = load_evidence(b"")
    evidence_status = {
        "status": "missing_for_uploaded_excel",
        "message": "הועלה Excel חלופי ללא evidence תואם; מוצג lineage מספרי בלבד.",
    }
else:
    evidence = cached_evidence(str(EVIDENCE_PATH), evidence_bytes)
    evidence_status = (
        {"status": "uploaded", "message": "נטען קובץ evidence שהועלה ידנית."}
        if evidence_bytes is not None else load_status(STATUS_PATH)
    )

matrix, matrix_stats = compute_matrix(
    numeric, catalog, view, metric, selected_team=selected_team,
    domain=domain, min_group_size=int(min_group_size),
)
question_meta = catalog.set_index("question_id").to_dict("index")

if matrix.empty:
    st.warning("אין נתונים לתצוגה שנבחרה.")
    st.stop()

# Use short labels on the x-axis; full question appears on hover.
x_ids = list(matrix.columns)
x_labels = [question_meta[q]["label"] for q in x_ids]
sort_state = st.session_state.get("matrix_sort")
if not isinstance(sort_state, dict):
    sort_state = {"qid": None, "descending": True}
sort_qid = sort_state.get("qid")
sort_descending = bool(sort_state.get("descending", True))
if sort_qid not in x_ids:
    sort_qid = None
    sort_descending = True
    st.session_state["matrix_sort"] = {"qid": None, "descending": True}

with st.expander("מיון שורות לפי שאלה", expanded=sort_qid is not None):
    if sort_qid is not None:
        direction_label = "יורד" if sort_descending else "עולה"
        st.caption(f"מיון פעיל: {question_meta[sort_qid]['label']} ({direction_label})")
    sort_columns = st.columns(4)
    for index, qid in enumerate(x_ids):
        is_active = sort_qid == qid
        arrow = " ↓" if is_active and sort_descending else (" ↑" if is_active else "")
        if sort_columns[index % 4].button(
            f"{question_meta[qid]['label']}{arrow}",
            key=f"sort_matrix_{qid}",
            use_container_width=True,
        ):
            st.session_state["matrix_sort"] = {
                "qid": qid,
                "descending": (not sort_descending) if is_active else True,
            }
            st.rerun()
    if sort_qid is not None and st.button("נקה מיון", key="clear_matrix_sort"):
        st.session_state["matrix_sort"] = {"qid": None, "descending": True}
        st.rerun()

matrix = sort_matrix_rows(matrix, sort_qid, sort_descending)
y_labels = list(matrix.index)
z = matrix.values.astype(float)


custom = []
for group in y_labels:
    row_custom = []
    for qid in x_ids:
        match = matrix_stats[(matrix_stats["group"] == group) & (matrix_stats["question_id"] == qid)]
        if match.empty:
            row_custom.append([0, np.nan, np.nan, np.nan, False, qid, group, "—", "—", np.nan, "—"])
            continue

        r = match.iloc[0]
        qdata = numeric[numeric["question_id"] == qid]
        group_mask = selected_group_mask(qdata, view, group, selected_team)
        response_ids = set(qdata.loc[group_mask, "response_id"].astype(int))
        counts = relation_counts(evidence, qid, response_ids, result_direction(r["delta"]))
        support_count = "—" if counts["support"] is None else str(counts["support"])
        contradict_count = "—" if counts["contradict"] is None else str(counts["contradict"])
        selected_scores = qdata.loc[group_mask, "score"] if bool(r["display_allowed"]) else []
        std_value = r["std"] if bool(r["display_allowed"]) else np.nan
        distribution_label = score_distribution_label(selected_scores)
        row_custom.append([
            int(r["n"]), r["mean"], r["branch_mean"], r["delta"],
            bool(r["display_allowed"]), qid, group, support_count, contradict_count, std_value, distribution_label,
        ])
    custom.append(row_custom)

if metric == "delta":
    colorscale = [[0, "#b2182b"], [0.5, "#f7f7f7"], [1, "#2166ac"]]
    zmax = max(abs(np.nanmin(z)), abs(np.nanmax(z)), 0.5)
    zmin = -zmax
elif metric in {"high", "low"}:
    colorscale = "RdYlGn" if metric == "high" else "RdYlGn_r"
    zmin, zmax = 0, 1
else:
    colorscale = "RdYlGn"
    zmin, zmax = None, None

fig = go.Figure(go.Heatmap(
    z=z,
    x=x_labels,
    y=y_labels,
    customdata=custom,
    colorscale=colorscale,
    zmin=zmin,
    zmax=zmax,
    colorbar={"title": metric_label},
    hovertemplate=(
        "<b>%{y}</b><br><b>%{x}</b><br>"
        + metric_label + ": %{z:.2f}<br>"
        "N: %{customdata[0]}<br>ממוצע: %{customdata[1]:.2f}<br>"
        "ממוצע ענפי: %{customdata[2]:.2f}<br>פער: %{customdata[3]:+.2f}<br>"
        "אמירות תומכות: %{customdata[7]}<br>"
        "סטיית תקן: %{customdata[9]:.2f}<br>התפלגות ציונים: %{customdata[10]}<br>"
        "אמירות סותרות/מסייגות: %{customdata[8]}<extra></extra>"
    ),
    xgap=1, ygap=1,
))
fig.update_layout(
    height=max(410, 34 * len(y_labels) + 200),
    margin=dict(l=30, r=20, t=30, b=150),
    xaxis={"tickangle": -45, "side": "bottom"},
    yaxis={"autorange": "reversed"},
    clickmode="event+select",
    dragmode=False,
)

st.subheader("מפת שאלות")
st.caption(
    "עמידה על תא מציגה גם את מספר האמירות המסווגות שתומכות או מסייגות את כיוון התוצאה. "
    f"סטטוס שכבת המלל: {evidence_status.get('message', evidence_status.get('status'))}"
)
event = st.plotly_chart(
    fig,
    use_container_width=True,
    on_select="rerun",
    selection_mode="points",
    key="question_heatmap",
)

# Plotly's click event can arrive either as the return value or through
# Streamlit's keyed session state. Parse both shapes and persist the result.
clicked_group, clicked_qid = extract_selected_cell(
    event,
    st.session_state.get("question_heatmap"),
    x_ids=x_ids,
    x_labels=x_labels,
    y_labels=y_labels,
)

valid_cells = [
    (group, qid)
    for group in y_labels
    for qid in x_ids
    if not pd.isna(matrix.loc[group, qid])
]
if not valid_cells:
    st.warning("אין תאים שעומדים בסף הפרטיות בתצוגה זו.")
    st.stop()

current = st.session_state.get("selected_question_cell")
if not isinstance(current, dict) or (current.get("group"), current.get("qid")) not in valid_cells:
    default_cell = valid_cells[0]
    st.session_state["selected_question_cell"] = {"group": default_cell[0], "qid": default_cell[1]}

if clicked_group is not None and clicked_qid is not None and (clicked_group, clicked_qid) in valid_cells:
    st.session_state["selected_question_cell"] = {"group": clicked_group, "qid": clicked_qid}

with st.expander("בחירה ידנית (חלופה ללחיצה על תא)", expanded=clicked_group is None):
    current = st.session_state["selected_question_cell"]
    with st.form("manual_cell_selection"):
        c1, c2 = st.columns(2)
        fallback_group = c1.selectbox(
            "קבוצה",
            y_labels,
            index=y_labels.index(current["group"]) if current["group"] in y_labels else 0,
        )
        available_qids = [qid for qid in x_ids if not pd.isna(matrix.loc[fallback_group, qid])]
        fallback_qid = c2.selectbox(
            "שאלה",
            available_qids,
            index=available_qids.index(current["qid"]) if current["qid"] in available_qids else 0,
            format_func=lambda q: question_meta[q]["label"],
        )
        manual_submit = st.form_submit_button("הצג בחירה")
    if manual_submit:
        st.session_state["selected_question_cell"] = {"group": fallback_group, "qid": fallback_qid}

selected_group = st.session_state["selected_question_cell"]["group"]
selected_qid = st.session_state["selected_question_cell"]["qid"]

meta = question_meta[selected_qid]
detail = drilldown(numeric, selected_qid, view, selected_group, selected_team)

# Keep the relative team comparison visible for the selected question,
# regardless of whether the active heatmap view is team, tenure, or general.
distribution = team_question_distribution(
    numeric,
    selected_qid,
    min_group_size=int(min_group_size),
)
eligible_distribution = distribution[distribution["display_allowed"]].copy()
hidden_teams = distribution.loc[~distribution["display_allowed"], "team"].astype(str).tolist()

if view == "team":
    highlighted_team = selected_group
elif view == "team_tenure":
    highlighted_team = selected_team
else:
    highlighted_team = None

st.subheader(f"השוואת כל הצוותים — {meta['label']}")
st.caption(
    "כל עמודה מייצגת את ממוצע הצוות בשאלה שנבחרה. הקו המקווקו הוא הממוצע הענפי; "
    "הצוות שנבחר מודגש כאשר הבחירה היא ברמת צוות."
)

if eligible_distribution.empty:
    st.info("אין צוותים שעומדים בסף הפרטיות עבור השאלה שנבחרה.")
else:
    support_counts = []
    contradict_counts = []
    qdata = numeric[numeric["question_id"] == selected_qid]
    for team_name in eligible_distribution["team"].astype(str):
        response_ids = set(qdata.loc[qdata["team"].astype(str) == team_name, "response_id"].astype(int))
        team_delta = float(
            eligible_distribution.loc[eligible_distribution["team"].astype(str) == team_name, "delta"].iloc[0]
        )
        counts = relation_counts(evidence, selected_qid, response_ids, result_direction(team_delta))
        support_counts.append("—" if counts["support"] is None else counts["support"])
        contradict_counts.append("—" if counts["contradict"] is None else counts["contradict"])

    eligible_distribution["support_count"] = support_counts
    eligible_distribution["contradict_count"] = contradict_counts
    eligible_distribution["bar_color"] = eligible_distribution["team"].astype(str).map(
        lambda team_name: "#C62828" if highlighted_team and team_name == highlighted_team else "#2F75B5"
    )

    team_fig = go.Figure(go.Bar(
        x=eligible_distribution["mean"],
        y=eligible_distribution["team"].astype(str),
        orientation="h",
        marker_color=eligible_distribution["bar_color"],
        text=eligible_distribution["mean"].map(lambda value: f"{value:.2f}"),
        textposition="outside",
        customdata=np.column_stack([
            eligible_distribution["n"],
            eligible_distribution["delta"],
            eligible_distribution["support_count"],
            eligible_distribution["contradict_count"],
        ]),
        hovertemplate=(
            "<b>%{y}</b><br>ממוצע: %{x:.2f}<br>N: %{customdata[0]}<br>"
            "פער מהענף: %{customdata[1]:+.2f}<br>"
            "אמירות תומכות: %{customdata[2]}<br>"
            "אמירות סותרות/מסייגות: %{customdata[3]}<extra></extra>"
        ),
    ))
    branch_mean_for_chart = float(numeric.loc[numeric["question_id"] == selected_qid, "score"].mean())
    team_fig.add_vline(
        x=branch_mean_for_chart,
        line_dash="dash",
        line_color="#17365D",
        annotation_text=f"ממוצע ענפי {branch_mean_for_chart:.2f}",
        annotation_position="top",
    )
    team_fig.update_layout(
        height=max(420, 31 * len(eligible_distribution) + 120),
        xaxis={"title": "ממוצע צוות", "range": [0, 10.6]},
        yaxis={"title": "", "categoryorder": "array", "categoryarray": eligible_distribution["team"].tolist()},
        margin=dict(l=30, r=60, t=45, b=35),
        showlegend=False,
    )
    st.plotly_chart(team_fig, use_container_width=True, key=f"team_distribution_{selected_qid}")
    if hidden_teams:
        st.caption("צוותים שלא הוצגו בגלל סף הפרטיות: " + ", ".join(hidden_teams))

st.divider()
st.header(f"{selected_group} — {meta['label']}")
st.caption(meta["full_text"])

s = detail["stats"]
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("ממוצע קבוצה", "—" if s["mean"] is None else f"{s['mean']:.2f}")
k2.metric("ממוצע ענפי", "—" if s["branch_mean"] is None else f"{s['branch_mean']:.2f}")
k3.metric("פער", "—" if s["delta"] is None else f"{s['delta']:+.2f}")
k4.metric("N", s["n"])
k5.metric("טווח בין־רבעוני", "—" if s["p25"] is None else f"{s['p25']:.1f}–{s['p75']:.1f}")

if s["n"] < min_group_size:
    st.warning(f"הקבוצה כוללת {s['n']} משיבים בלבד ולכן הגלם והמלל מוסתרים בהתאם לסף הפרטיות ({min_group_size}).")
    st.stop()

numeric_direction = result_direction(s["delta"])
selected_evidence = evidence_for_selection(evidence, selected_qid, detail["response_ids"], numeric_direction, detail["rows"])

raw_tab, split_tab, support_tab, contradict_tab, lineage_tab = st.tabs([
    "ציונים גולמיים", "פילוח נוסף", "אמירות תומכות", "אמירות סותרות/מסייגות", "Lineage",
])

with raw_tab:
    counts = score_distribution_counts(detail["rows"]["score"])
    score_values = sorted(counts.keys())
    count_values = [counts[score] for score in score_values]
    max_count = max(count_values + [0])
    mean_text = "—" if s["mean"] is None else f"{s['mean']:.2f}"
    std_text = "—" if s["std"] is None else f"{s['std']:.2f}"
    st.caption(f"ממוצע {mean_text} · סטיית תקן {std_text} · N={s['n']}")
    dist_fig = go.Figure(go.Bar(
        x=score_values,
        y=count_values,
        text=count_values,
        textposition="outside",
        marker_color="#2F75B5",
        hovertemplate="ציון %{x}<br>מספר משיבים: %{y}<extra></extra>",
    ))
    dist_fig.update_layout(
        height=330,
        xaxis={"title": "ציון", "dtick": 1, "range": [0.5, 10.5]},
        yaxis={"title": "מספר משיבים", "dtick": 1, "range": [0, max_count + 1]},
        bargap=0.12,
        margin=dict(l=35, r=30, t=20, b=40),
        showlegend=False,
    )
    st.plotly_chart(dist_fig, use_container_width=True)
with split_tab:
    split = detail["rows"].groupby("tenure")["score"].agg(N="count", ממוצע="mean", חציון="median").reset_index().rename(columns={"tenure":"וותק"})
    split["פער מהענף"] = split["ממוצע"] - s["branch_mean"]
    split.loc[split["N"] < min_group_size, ["ממוצע", "חציון", "פער מהענף"]] = np.nan
    st.dataframe(split.style.format({"ממוצע":"{:.2f}", "חציון":"{:.2f}", "פער מהענף":"{:+.2f}"}), use_container_width=True, hide_index=True)
    st.caption("כל קבוצת ותק נבדקת שוב מול סף הפרטיות.")

with support_tab:
    st.caption(f"סטטוס שכבת המלל: {evidence_status.get('message', evidence_status.get('status'))}")
    support = selected_evidence[selected_evidence["relation"] == "תומכת"] if not selected_evidence.empty else selected_evidence
    if support.empty:
        st.info("לא נמצאו אמירות מסווגות שתומכות בכיוון התוצאה. ייתכן שה-Batch טרם הושלם או שאין ראיה ישירה במלל.")
    else:
        for row in support.to_dict("records"):
            st.markdown(evidence_card_html(row, "support"), unsafe_allow_html=True)
            with st.expander("הצגת תשובת המקור המלאה"):
                st.write(row["raw_text"])

with contradict_tab:
    contradict = selected_evidence[selected_evidence["relation"] == "סותרת/מסייגת"] if not selected_evidence.empty else selected_evidence
    if contradict.empty:
        st.info("לא נמצאו אמירות מסווגות שסותרות או מסייגות את כיוון התוצאה.")
    else:
        for row in contradict.to_dict("records"):
            st.markdown(evidence_card_html(row, "contradict"), unsafe_allow_html=True)
            with st.expander("הצגת תשובת המקור המלאה"):
                st.write(row["raw_text"])

with lineage_tab:
    source_rows = ", ".join(map(str, detail["rows"]["source_excel_row"].tolist()))
    st.markdown(f"""
1. **תא נבחר:** `{selected_group} × {meta['label']}`  
2. **עמודת המקור ב-Excel:** `נתונים גולמיים!{meta['source_column']}:{meta['source_column']}`  
3. **שורות המקור שנכללו:** `{source_rows}`  
4. **ממוצע הקבוצה:** ממוצע {s['n']} הציונים = **{s['mean']:.4f}**  
5. **ממוצע ענפי:** ממוצע כל הציונים בשאלה = **{s['branch_mean']:.4f}**  
6. **פער:** {s['mean']:.4f} − {s['branch_mean']:.4f} = **{s['delta']:+.4f}**  
7. **ממד:** {meta['dimension']}  
8. **שכבת מלל:** התאמת LLM נעשית ללא חשיפה לציונים; היחס 'תומכת/סותרת' מחושב לאחר מכן באופן דטרמיניסטי לפי כיוון הפער.  
9. **סטטוס evidence:** `{evidence_status.get('status')}`  
""")
    st.dataframe(detail["rows"][["response_id", "source_excel_row", "team", "tenure", "score"]], use_container_width=True, hide_index=True)
