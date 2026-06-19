"""情绪周期卡片可视化仪表盘（Streamlit）。

运行：
    streamlit run dashboard.py -- --db ./xueqiu.duckdb

只读 DuckDB，围绕 cards 表展示概念/正反例/周期/标的/置信度/时间线，并支持多维筛选与导出。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import plotly.express as px

from viz import queries as q

POLARITY_COLORS = {"正例": "#2ca02c", "反例": "#d62728", "中性": "#7f7f7f", "不适用": "#c7c7c7"}


def get_db_path():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="./xueqiu.duckdb")
    # streamlit 把 `--` 之后的参数透传到 sys.argv
    args, _ = parser.parse_known_args(sys.argv[1:])
    return args.db


@st.cache_resource
def get_con(db_path):
    return q.connect(db_path, read_only=True)


def sidebar_filters(con):
    opts = q.filter_options(con)
    st.sidebar.header("筛选")
    f = {}
    f["concepts"] = st.sidebar.multiselect("概念", opts["concepts"])
    f["polarities"] = st.sidebar.multiselect("正反例", opts["polarities"])
    f["cycles"] = st.sidebar.multiselect("周期", opts["cycles"])
    f["targets"] = st.sidebar.multiselect("标的", opts["targets"])
    f["confidences"] = st.sidebar.multiselect("置信度", opts["confidences"])
    f["needs_review"] = st.sidebar.checkbox("仅看待复核", value=False)
    if opts["date_min"] and opts["date_max"]:
        f["date_from"] = st.sidebar.text_input("起始日期 (YYYY-MM-DD)", opts["date_min"])
        f["date_to"] = st.sidebar.text_input("结束日期 (YYYY-MM-DD)", opts["date_max"])
    return f


def render(con, f):
    k = q.kpis(con, f)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("卡片数", k["cards"])
    c2.metric("覆盖帖子", k["posts"])
    c3.metric("正例", k["pos"])
    c4.metric("反例", k["neg"])
    c5.metric("待复核", k["review"])

    if not k["cards"]:
        st.info("当前筛选无卡片。")
        return

    st.subheader("概念频次")
    dfc = q.concept_counts(con, f)
    st.plotly_chart(
        px.bar(dfc, x="n", y="concept", orientation="h").update_yaxes(
            categoryorder="total ascending"),
        use_container_width=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("正反例 × 概念")
        dfp = q.polarity_by_concept(con, f)
        st.plotly_chart(
            px.bar(dfp, x="concept", y="n", color="polarity",
                   color_discrete_map=POLARITY_COLORS),
            use_container_width=True,
        )
    with col2:
        st.subheader("周期分布")
        dfy = q.cycle_counts(con, f)
        st.plotly_chart(px.pie(dfy, names="cycle", values="n"), use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        st.subheader("标的 Top")
        dft = q.target_counts(con, f)
        st.plotly_chart(
            px.bar(dft, x="n", y="target", orientation="h").update_yaxes(
                categoryorder="total ascending"),
            use_container_width=True,
        )
    with col4:
        st.subheader("置信度分布")
        dfd = q.confidence_counts(con, f)
        st.plotly_chart(px.bar(dfd, x="confidence", y="n"), use_container_width=True)

    st.subheader("事件时间线")
    dtl = q.timeline(con, f)
    st.plotly_chart(
        px.bar(dtl, x="date", y="n", color="polarity", color_discrete_map=POLARITY_COLORS),
        use_container_width=True,
    )

    st.subheader("卡片明细")
    tbl = q.card_table(con, f)
    tbl["concepts"] = tbl["concepts"].apply(lambda x: "、".join(x) if x is not None else "")
    tbl["targets"] = tbl["targets"].apply(lambda x: "、".join(x) if x is not None else "")
    st.dataframe(
        tbl,
        use_container_width=True,
        column_config={"url": st.column_config.LinkColumn("链接")},
        hide_index=True,
    )
    st.download_button(
        "下载当前结果 CSV",
        tbl.to_csv(index=False).encode("utf-8-sig"),
        file_name="cards.csv",
        mime="text/csv",
    )


def main():
    st.set_page_config(page_title="情绪周期卡片仪表盘", layout="wide")
    st.title("情绪周期卡片仪表盘")
    db_path = get_db_path()
    st.caption(f"数据源：{db_path}")
    con = get_con(db_path)
    if not q.has_cards(con):
        st.warning("数据库中没有 cards 表。请先运行 `python -m extract run` 生成结构化卡片。")
        return
    f = sidebar_filters(con)
    render(con, f)


if __name__ == "__main__":
    main()
