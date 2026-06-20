"""把 cards 导出为单文件离线 HTML 卡片浏览器（可拷到手机浏览器离线使用）。

用法：
    python -m viz.export_html --db ./xueqiu.duckdb --out ./output/cards.html

数据内嵌进 HTML，筛选/搜索全在浏览器端 JS 完成，无需 Python/网络。
仅依赖 duckdb。
"""
import os
import json
import html
import argparse
from datetime import datetime

import duckdb

SQL = """
SELECT c.post_id, c.source_post_date AS post_date, c.event_date, c.behavior_summary,
       c.concepts, c.targets, c.cycle, c.polarity, c.polarity_reason,
       c.polarity_confidence AS confidence, c.scene, c.key_quote, c.judgment,
       c.judgment_basis, c.verification, c.error_type, c.needs_review,
       p.text AS post_text,
       'https://xueqiu.com' || coalesce(p.target, '') AS url
FROM cards c LEFT JOIN posts p ON c.post_id = p.post_id
ORDER BY c.source_post_date DESC NULLS LAST, c.post_id, c.card_idx
"""

PAGE_TEMPLATE = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>情绪周期卡片浏览器</title>
<style>
:root{--bd:#e2e2e2;--mut:#888;--pos:#2ca02c;--neg:#d62728;--neu:#888}
*{box-sizing:border-box}
body{margin:0;font:16px/1.6 -apple-system,system-ui,"PingFang SC","Microsoft YaHei",sans-serif;color:#1a1a1a;background:#fafafa}
header{padding:14px 16px;background:#fff;border-bottom:1px solid var(--bd);position:sticky;top:0;z-index:5}
header h1{margin:0;font-size:18px}
.muted{color:var(--mut);font-size:13px}
.filters{display:flex;flex-wrap:wrap;gap:8px;padding:12px 16px;background:#fff;border-bottom:1px solid var(--bd);position:sticky;top:52px;z-index:4}
.filters input[type=search],.filters select{padding:8px;border:1px solid var(--bd);border-radius:8px;font-size:15px;background:#fff}
.filters input[type=search]{flex:1 1 100%;min-width:0}
.filters label{display:flex;align-items:center;gap:4px;font-size:14px}
.filters button{padding:8px 12px;border:1px solid var(--bd);border-radius:8px;background:#fff}
#count{padding:8px 16px;color:var(--mut);font-size:13px}
#list{padding:0 12px}
.card{background:#fff;border:1px solid var(--bd);border-radius:12px;padding:14px;margin:10px 0}
.head{font-size:14px;color:#333;margin-bottom:6px}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;color:#fff;font-size:13px}
.badge.pos{background:var(--pos)}.badge.neg{background:var(--neg)}.badge.neu,.badge.na{background:var(--neu)}
.tags{margin:4px 0;font-size:14px;color:#555}
.tag{display:inline-block;background:#eef;border-radius:6px;padding:1px 7px;margin:2px;font-size:13px}
.sum{margin:6px 0}
blockquote{margin:8px 0;padding:6px 12px;border-left:3px solid #ccc;background:#f6f6f6;color:#333}
.smalls{margin-top:6px;color:var(--mut);font-size:13px}
.smalls .s{margin-right:4px}
details{margin-top:8px}
details .post{white-space:pre-wrap;background:#f6f6f6;border-radius:8px;padding:10px;margin:6px 0;font-size:14px}
a{color:#1a73e8}
#more{display:block;width:calc(100% - 24px);margin:12px;padding:12px;border:1px solid var(--bd);border-radius:10px;background:#fff;font-size:15px}
</style>
</head>
<body>
<header>
  <h1>情绪周期卡片浏览器</h1>
  <div class="muted">共 <span id="total">0</span> 张卡 · 生成于 __GENERATED__ · 离线可用</div>
</header>
<div class="filters">
  <input id="q" type="search" placeholder="全文搜索：复述/原文/判断/依据/盘面/标的…">
  <select id="concept"></select>
  <select id="cycle"></select>
  <select id="polarity"></select>
  <select id="confidence"></select>
  <label><input type="checkbox" id="review"> 仅看待复核</label>
  <button id="reset">重置</button>
</div>
<div id="count"></div>
<div id="list"></div>
<button id="more" style="display:none">加载更多</button>
<script>
const DATA = __DATA__;
const POL = {'正例':'pos','反例':'neg','中性':'neu','不适用':'na'};
const PAGE = 50;
let filtered = [], shown = 0;

function uniq(a){return [...new Set(a)].filter(Boolean).sort();}
function esc(s){const d=document.createElement('div');d.textContent=(s==null?'':String(s));return d.innerHTML;}
function fill(id,label,vals){document.getElementById(id).innerHTML='<option value="">'+label+'</option>'+vals.map(v=>'<option>'+esc(v)+'</option>').join('');}
fill('concept','全部概念',uniq(DATA.flatMap(d=>d.concepts||[])));
fill('cycle','全部周期',uniq(DATA.map(d=>d.cycle)));
fill('polarity','全部正反例',uniq(DATA.map(d=>d.polarity)));
fill('confidence','全部置信度',uniq(DATA.map(d=>d.confidence)));

function tags(label,arr){arr=(arr||[]).filter(Boolean);if(!arr.length)return'';return '<div class="tags">'+label+'：'+arr.map(x=>'<span class="tag">'+esc(x)+'</span>').join('')+'</div>';}
function sm(label,v){return v?'<span class="s"><b>'+label+'：</b>'+esc(v)+'</span>':'';}
function cardHtml(d){
  let h='<div class="card">';
  h+='<div class="head">'+esc(d.post_date||'—')+' · <span class="badge '+(POL[d.polarity]||'na')+'">'+esc(d.polarity)+'</span> · 置信 '+esc(d.confidence)+' · 周期 '+esc(d.cycle)+(d.needs_review?' · 🚩待复核':'')+'</div>';
  h+=tags('概念',d.concepts)+tags('标的',d.targets);
  if(d.behavior_summary)h+='<div class="sum"><b>复述：</b>'+esc(d.behavior_summary)+'</div>';
  if(d.key_quote)h+='<blockquote>'+esc(d.key_quote)+'</blockquote>';
  if(d.judgment)h+='<div><b>判断：</b>'+esc(d.judgment)+'</div>';
  const s=[sm('正反例依据',d.polarity_reason),sm('判断依据',d.judgment_basis),sm('盘面',d.scene),sm('事件日期',d.event_date),sm('验证',d.verification),sm('错误类型',d.error_type)].filter(Boolean).join(' · ');
  if(s)h+='<div class="smalls">'+s+'</div>';
  h+='<details><summary>原帖 / 链接</summary><div class="post">'+esc(d.post_text||'（无原文）')+'</div><a href="'+esc(d.url)+'" target="_blank" rel="noopener">在雪球查看原帖</a> · post_id '+esc(d.post_id)+'</details>';
  return h+'</div>';
}
function renderMore(){
  const slice=filtered.slice(shown,shown+PAGE);
  document.getElementById('list').insertAdjacentHTML('beforeend',slice.map(cardHtml).join(''));
  shown+=slice.length;
  document.getElementById('more').style.display = shown<filtered.length ? 'block':'none';
}
function apply(){
  const q=document.getElementById('q').value.trim().toLowerCase();
  const c=document.getElementById('concept').value, cy=document.getElementById('cycle').value;
  const p=document.getElementById('polarity').value, cf=document.getElementById('confidence').value;
  const rv=document.getElementById('review').checked;
  filtered=DATA.filter(d=>{
    if(c && !(d.concepts||[]).includes(c))return false;
    if(cy && d.cycle!==cy)return false;
    if(p && d.polarity!==p)return false;
    if(cf && d.confidence!==cf)return false;
    if(rv && !d.needs_review)return false;
    if(q){
      const hay=[d.behavior_summary,d.key_quote,d.judgment,d.judgment_basis,d.scene,d.polarity_reason,(d.concepts||[]).join(' '),(d.targets||[]).join(' '),d.post_text].join(' ').toLowerCase();
      if(!hay.includes(q))return false;
    }
    return true;
  });
  shown=0;document.getElementById('list').innerHTML='';
  document.getElementById('count').textContent='匹配 '+filtered.length+' 张卡';
  renderMore();
}
['q','concept','cycle','polarity','confidence','review'].forEach(id=>{
  const el=document.getElementById(id);
  el.addEventListener('input',apply);el.addEventListener('change',apply);
});
document.getElementById('more').addEventListener('click',renderMore);
document.getElementById('reset').addEventListener('click',()=>{
  document.getElementById('q').value='';
  ['concept','cycle','polarity','confidence'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('review').checked=false;apply();
});
document.getElementById('total').textContent=DATA.length;
apply();
</script>
</body>
</html>
"""


def export_html(db_path, out_path):
    con = duckdb.connect(db_path, read_only=True)
    try:
        exists = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name='cards'"
        ).fetchone()[0]
        if not exists:
            raise SystemExit("数据库中没有 cards 表，请先运行 `python -m extract run`。")
        cur = con.execute(SQL)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()

    data_json = json.dumps(rows, ensure_ascii=False, default=str).replace("</", "<\\/")
    page = (PAGE_TEMPLATE
            .replace("__DATA__", data_json)
            .replace("__GENERATED__", html.escape(datetime.now().strftime("%Y-%m-%d %H:%M"))))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)
    return out_path, len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description="导出离线 HTML 卡片浏览器")
    parser.add_argument("--db", default="./xueqiu.duckdb", help="DuckDB 路径")
    parser.add_argument("--out", default="./output/cards.html", help="输出 HTML 路径")
    args = parser.parse_args(argv)
    out, n = export_html(args.db, args.out)
    size_kb = os.path.getsize(out) / 1024
    print(f"已导出 {n} 张卡到 {out}（{size_kb:.0f} KB）。拷到手机用浏览器打开即可离线使用。")


if __name__ == "__main__":
    main()
