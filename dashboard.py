"""情绪周期卡片浏览器（Streamlit）。

运行：
    streamlit run dashboard.py -- --db ./xueqiu.duckdb

聚焦「读卡片」：侧栏多维筛选 + 全文搜索，主区分页展示每张卡的完整字段，
并可展开原帖正文、跳转雪球核对。只读 DuckDB，不影响爬虫/抽取。
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import streamlit as st

from viz import queries as q

POLARITY_BADGE = {"正例": "🟢 正例", "反例": "🔴 反例", "中性": "⚪ 中性", "不适用": "⚪ 不适用"}


def get_db_path():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="./xueqiu.duckdb")
    args, _ = parser.parse_known_args(sys.argv[1:])
    return args.db


@st.cache_resource
def get_con(db_path):
    return q.connect(db_path, read_only=True)


def sidebar_filters(con):
    opts = q.filter_options(con)
    st.sidebar.header("筛选")
    f = {}
    f["search"] = st.sidebar.text_input("全文搜索", placeholder="复述/原文/判断/依据/盘面…")
    f["concepts"] = st.sidebar.multiselect("概念", opts["concepts"])
    f["polarities"] = st.sidebar.multiselect("正反例", opts["polarities"])
    f["cycles"] = st.sidebar.multiselect("周期", opts["cycles"])
    f["targets"] = st.sidebar.multiselect("标的", opts["targets"])
    f["confidences"] = st.sidebar.multiselect("置信度", opts["confidences"])
    f["needs_review"] = st.sidebar.checkbox("仅看待复核", value=False)
    if opts["date_min"] and opts["date_max"]:
        f["date_from"] = st.sidebar.text_input("起始日期", opts["date_min"])
        f["date_to"] = st.sidebar.text_input("结束日期", opts["date_max"])
    f["page_size"] = st.sidebar.selectbox("每页", [10, 20, 50], index=1)
    return f


def _as_list(items):
    """LIST 列经 .df() 可能是 numpy 数组或 NULL(pandas NA 标量)，统一成列表。"""
    if isinstance(items, np.ndarray):
        items = items.tolist()
    elif not isinstance(items, (list, tuple)):
        return []  # None / pd.NA / NaN 等非可迭代值
    return [x for x in items if x]


def _tags(label, items):
    items = _as_list(items)
    if not items:
        return ""
    return f"{label}：" + " ".join(f"`{x}`" for x in items)


def render_card(r):
    with st.container(border=True):
        head = f"**{r['post_date'] or '—'}**　·　{POLARITY_BADGE.get(r['polarity'], r['polarity'])}"
        head += f"　·　置信 {r['confidence']}　·　周期 {r['cycle']}"
        if r["needs_review"]:
            head += "　·　🚩 待复核"
        st.markdown(head)

        tags = [_tags("概念", r["concepts"]), _tags("标的", r["targets"])]
        tags = [t for t in tags if t]
        if tags:
            st.markdown("　　".join(tags))

        if r["behavior_summary"]:
            st.markdown(f"**复述**：{r['behavior_summary']}")
        if r["key_quote"]:
            st.markdown(f"> {r['key_quote']}")
        if r["judgment"]:
            st.markdown(f"**判断**：{r['judgment']}")

        small = []
        if r["polarity_reason"]:
            small.append(f"正反例依据：{r['polarity_reason']}")
        if r["judgment_basis"]:
            small.append(f"判断依据：{r['judgment_basis']}")
        if r["scene"]:
            small.append(f"盘面：{r['scene']}")
        if r["event_date"]:
            small.append(f"事件日期：{r['event_date']}")
        if r["verification"]:
            small.append(f"验证：{r['verification']}")
        if r["error_type"]:
            small.append(f"错误类型：{r['error_type']}")
        if small:
            st.caption("　·　".join(small))

        with st.expander("原帖 / 链接"):
            st.write(r["post_text"] or "（无原文）")
            st.markdown(f"[在雪球查看原帖]({r['url']})　·　post_id `{r['post_id']}`")


def main():
    st.set_page_config(page_title="情绪周期卡片浏览器", layout="wide")
    st.title("情绪周期卡片浏览器")
    db_path = get_db_path()
    st.caption(f"数据源：{db_path}")
    con = get_con(db_path)
    if not q.has_cards(con):
        st.warning("数据库中没有 cards 表。请先运行 `python -m extract run` 生成结构化卡片。")
        return

    f = sidebar_filters(con)
    total = q.count_cards(con, f)
    page_size = f["page_size"]
    pages = max(1, math.ceil(total / page_size))

    top = st.columns([3, 1])
    top[0].markdown(f"**匹配 {total} 张卡**")
    page = top[1].number_input("页", min_value=1, max_value=pages, value=1, step=1)
    st.caption(f"第 {page}/{pages} 页")

    if total == 0:
        st.info("当前筛选无卡片。")
        return

    page_df = q.card_page(con, f, limit=page_size, offset=(page - 1) * page_size)
    for _, r in page_df.iterrows():
        render_card(r)

    csv = q.card_table(con, f)
    csv["concepts"] = csv["concepts"].apply(lambda x: "、".join(_as_list(x)))
    csv["targets"] = csv["targets"].apply(lambda x: "、".join(_as_list(x)))
    st.sidebar.download_button(
        "下载筛选结果 CSV",
        csv.to_csv(index=False).encode("utf-8-sig"),
        file_name="cards.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
