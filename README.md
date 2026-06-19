# xueqiu-spyder

雪球(Xueqiu)爬虫工具，可爬取个股热门讨论、筛选大V观点并生成 Markdown 报告，也可爬取指定用户的全部帖子或专栏。

## 功能

- **股票大V观点** — 爬取某只股票的热门讨论，按评论数筛选大V，汇总观点生成报告
- **用户帖子爬取** — 爬取指定用户的全部帖子/专栏，支持按时间过滤
- **用户搜索** — 按关键词搜索雪球用户，获取用户ID

## 前置条件

- Python 3.9+
- Chrome 浏览器（用于连接调试端口爬取数据）

> 程序会自动在常见安装位置查找 Chrome（Windows 的用户级与系统级目录、macOS 的 Applications、Linux 的 PATH 与常见路径）。
> 如果 Chrome 安装在非默认位置导致找不到，可通过环境变量 `CHROME_PATH` 指定可执行文件完整路径，例如：
>
> ```powershell
> # Windows PowerShell
> $env:CHROME_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
> ```

## 安装

```bash
git clone https://github.com/<your-username>/xueqiu-spyder.git
cd xueqiu-spyder
pip install -r requirements.txt
```

## Cookie 设置

雪球**未登录时只能获取首页/第一页公开数据**，翻页或查看更多会提示「请登录雪球查看更多内容」。
因此爬取用户全部帖子前需配置登录态 Cookie：

```bash
python setup_cookie.py
```

在 Chrome 中打开 https://xueqiu.com 并登录，按 `F12 -> Application -> Cookies -> https://xueqiu.com`，
按提示粘贴 `xq_a_token` 等 Cookie 值，脚本会保存到 `.cookies.json`（已在 .gitignore 中排除，不会被提交）。
爬虫启动时会自动把这些 Cookie 注入浏览器。若 token 过期再次出现登录提示，重新运行本脚本更新即可。

## 使用

### 股票大V观点

```bash
python main.py stock <股票代码> [--min-reply 20] [--max-pages 20] [--output ./output]
```

### 用户帖子爬取

```bash
python main.py user <用户ID或用户名> [--max-pages 10] [--all] [--days 30] [--full-text] [--resume] [--db ./xueqiu.duckdb] [--no-db]
```

> 用户帖子**直接写入 DuckDB，不再生成 Markdown 文件**。需要任何视图/过滤都用 SQL 查询数据库即可。

- `--all` 爬取该用户**全部**帖子，翻到没有更多为止（忽略 `--max-pages`，受 `config.MAX_USER_PAGES` 上限保护）
- `--days N` 只爬最近 N 天，命中时间下限即提前停止翻页，减少请求
- `--full-text` 补全被截断的长文全文（会额外访问详情页，请求量更大）
- `--resume` 断点续爬：从上次被拦截的页码继续（见下）
- `--db PATH` 指定 DuckDB 数据库文件路径（默认 `./xueqiu.duckdb`）
- `--no-db` 本次不写入数据库（仅爬取，不落库）
- 支持直接传用户名，会自动搜索解析为数字ID

#### 断点续爬

每次爬取结束都会把进度记到 DuckDB 的 `users` 表（`resume_page` / `last_status`）：

- 若中途被风控/要求登录而中断，会记录**中断的页码**并提示
- 下次带 `--resume` 即从那一页继续，不必从头重爬：

```bash
python main.py user 治雨 --all            # 假设在第 8 页被拦截中断
python main.py user 治雨 --all --resume    # 从第 8 页继续
```

> 说明：续爬按**页码**定位。若两次运行之间该用户又发了新帖，页码会顺移，
> `--resume` 可能略过最顶部的新帖（已抓的旧帖因主键去重不会重复）。
> 因此 `--resume` 适合「尽快接着把历史抓完」；想顺带补最新内容时，不加 `--resume` 从头跑一遍即可（去重保证不会重复）。
> 已正常抓完后，续爬记录会清空，再次运行将从第 1 页开始。

> **反封禁说明**：爬取用户全部帖子时内置了节流策略——每次请求带随机抖动间隔、
> 每翻若干页做一次较长休息、检测到限流/风控（HTTP 429/403 或非 JSON 响应）时自动指数退避重试。
> 相关参数可在 `config.py` 中调整：`REQUEST_DELAY`、`REQUEST_DELAY_JITTER`、
> `LONG_REST_EVERY`、`LONG_REST_SECONDS`、`RATE_LIMIT_BACKOFF` 等。
> 如需更稳妥（爬取量大、账号重要），建议调大 `REQUEST_DELAY` 与 `LONG_REST_SECONDS`。

### 搜索用户

```bash
python main.py search <关键词>
```

## 数据存储（DuckDB）

用户帖子的抓取结果会写入 DuckDB（用户命令唯一的输出），便于后续做 SQL 分析或增量积累历史数据：

- 默认数据库文件：`./xueqiu.duckdb`（已在 `.gitignore` 中排除）
- 表 `posts`：以 `post_id` 为主键**幂等去重**，重复爬取只会更新不会重复插入；含清洗后的纯文本 `text`、原始 HTML `description`、是否专栏 `is_column`、互动数据（评论/点赞/转发/收藏/浏览）、`raw_json` 完整原始字段等
- 表 `users`：记录用户名、`post_count`（该用户在 `posts` 表中的累计条数，与 `SELECT count(*) FROM posts WHERE user_id=...` 对齐）、最近抓取时间，以及断点续爬状态 `resume_page` / `last_status`

### 去重

写入采用主键 + `INSERT OR REPLACE`，**反复爬取同一用户不会产生重复数据**，已存在的帖子会用最新数据覆盖（点赞/评论数等随之更新）。

如果是早期遗留、或从其它来源导入、可能含重复的历史库，可手动清理一次（按 `post_id` 保留最近抓取的一条，可安全反复执行）：

```bash
python main.py dedup [--db ./xueqiu.duckdb]
```

需要按时间、专栏等维度筛选时，直接用 SQL 查询，例如：

```bash
python -c "import duckdb; print(duckdb.connect('xueqiu.duckdb').sql('SELECT screen_name, count(*) FROM posts GROUP BY 1'))"
```

```sql
-- 某用户点赞最高的 10 条帖子
SELECT created_at, like_count, reply_count, text
FROM posts WHERE user_id = 9548638136
ORDER BY like_count DESC LIMIT 10;

-- 某用户最近 30 天的专栏文章
SELECT created_at, title, text FROM posts
WHERE user_id = 9548638136 AND is_column
  AND created_at >= now() - INTERVAL 30 DAY
ORDER BY created_at DESC;
```

### 转发关联

被转发的原帖会**作为独立行一并入库**，转发帖通过 `retweeted_post_id` / `retweeted_user_id`
关联到原帖，可直接自关联 `posts` 表：

```sql
-- 转发帖 ↔ 被转发原帖
SELECT p.screen_name AS 转发者, p.text AS 转发语,
       o.screen_name AS 原作者, o.text AS 原帖内容
FROM posts p
JOIN posts o ON p.retweeted_post_id = o.post_id
WHERE p.user_id = 9548638136;
```

> 早期已建的数据库会自动补上这两列（仅对之后新写入的帖子填充转发关联）。

## 结构化抽取管道（`extract/`）

把 `posts` 表里的发帖（纯文本）用 LLM 批量抽成固定 schema 的结构化卡片，落到同库并列的
`cards` 表，支持按「概念 / 周期 / 标的 / 正反例 / 待复核」查询。分类规则全部外置在
`extract/taxonomy.yaml`，改规则不动代码；LLM 走第三方 **OpenAI 兼容** 接口，换厂商只改环境变量。

### 配置

复制 `extract/llm.yaml.example` 为 `extract/llm.yaml` 并填写：

```yaml
llm:
  base_url: https://your-provider/v1   # 兼容端点，需含 /v1
  api_key: sk-xxxx
  model: your-model-name
  temperature: 0      # 可选，默认 0
  concurrency: 5      # 同时在飞的请求数上限
  rpm: 0              # 每分钟请求数上限（客户端限流），0=不限；按厂商配额设
  max_retries: 3
  timeout_s: 60
  prompt_cache: off   # off | on
```

> **prompt 缓存**：抽取走「单帖单调用」，但那段又长又固定的 system prompt 每次都一样，
> 作为**可缓存前缀**能大幅降本提速。
> - `off`：不注入缓存声明。OpenAI / DeepSeek 等仍会按相同前缀**自动**缓存（无需设置，off 也照样命中）；
> - `on`：给 system 注入 `cache_control`（Anthropic 等需要显式声明的端点用；`anthropic` 是其别名）。
>
> 说明：自动缓存型厂商没有「客户端开关」，`on` 能做的就是注入 `cache_control`；用这类厂商保持 `off` 即可。
> 运行结束会打印 token 用量与缓存命中率（`prompt / 缓存命中 / completion`），可据此确认缓存是否生效。

> **限流**：`concurrency` 控制并发在飞数，`rpm` 控制每分钟请求总数（跨线程平滑起始时刻）。
> 命中 `429/5xx` 会优先按服务端 `Retry-After` 退避、否则指数退避，重试本身也受 `rpm` 约束。
> 厂商有 RPM 配额时设 `rpm`（如每分钟 60 就填 60），可显著减少被限流。

`llm.yaml` 含密钥，已在 `.gitignore` 中排除。优先级 **环境变量 > llm.yaml > 默认值**——
想让密钥不落盘，可只在文件里写 `base_url`/`model`，`api_key` 用环境变量 `LLM_API_KEY` 提供。
也可用 `--llm-config 路径` 指定其它配置文件。

分类口径见 `extract/taxonomy.yaml`（概念枚举 + 口语线索 + few-shot）。

### 运行

```bash
# 小批校准：先跑 30 条，人工看 needs_review 再调 taxonomy.yaml
python -m extract run --limit 30

# 全量抽取（只处理未完成/失败的，幂等可重跑）
python -m extract run

# 只重试失败的；或全量重抽（覆盖已完成）
python -m extract run --only-failed
python -m extract run --reset

# 进度与概念分布
python -m extract stats

# 导出待复核队列（或按维度查询）
python -m extract review --out ./output/review.md
python -m extract review --concept 转点卡位 --polarity 反例 --all --out ./output/卡位反例.md
```

- 一条帖 → 一次 LLM 调用 → 0..N 张卡（长复盘帖含多个「标的×节点」事件）。
- 幂等：以 `post_id` 为键，重跑先删旧卡再插；断点续跑按 `extract_status` 只处理未完成/失败的。
- 解析失败/超时不崩，落 `failed` 表可重试。

### 查询卡片

```sql
-- 某概念的所有反例
SELECT post_id, targets, key_quote, judgment FROM cards
WHERE list_contains(concepts, '转点卡位') AND polarity = '反例';

-- 待人工复核队列
SELECT * FROM cards WHERE needs_review;

-- 某标的的全部出现
SELECT * FROM cards WHERE list_contains(targets, '合富');
```

> 抽取的判断是对原帖观点的结构化，不构成投资建议；低置信度项（`needs_review`）须人工复核。

## 示例

```bash
# 爬取大族激光的大V观点
python main.py stock SZ002738 --min-reply 20 --max-pages 10

# 爬取用户"治雨"的全部帖子并存入 DuckDB（含长文全文）
python main.py user 治雨 --all --full-text

# 爬取用户最近30天的帖子
python main.py user 9548638136 --days 30

# 搜索用户
python main.py search 治雨
```

## 作为 Claude Code Skill 使用

本项目也是一个 [Claude Code Skill](https://docs.anthropic.com/en/docs/claude-code)。将本仓库克隆到 `~/.claude/skills/` 目录下即可在 Claude Code 中直接调用：

```
~/.claude/skills/xueqiu-spyder/
```

## 输出

在 `./output/` 目录下生成 Markdown 格式的报告。

## 免责声明

本工具仅供学习和研究使用。请遵守雪球的使用条款，合理控制爬取频率。
