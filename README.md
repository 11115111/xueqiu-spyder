# xueqiu-spyder

雪球(Xueqiu)爬虫工具，可爬取个股热门讨论、筛选大V观点并生成 Markdown 报告，也可爬取指定用户的全部帖子或专栏。

## 功能

- **股票大V观点** — 爬取某只股票的热门讨论，按评论数筛选大V，汇总观点生成报告
- **用户帖子爬取** — 爬取指定用户的全部帖子/专栏，支持按时间过滤
- **用户搜索** — 按关键词搜索雪球用户，获取用户ID

## 前置条件

- Python 3.9+
- Chrome 浏览器（用于获取 Cookie）

## 安装

```bash
git clone https://github.com/<your-username>/xueqiu-spyder.git
cd xueqiu-spyder
pip install -r requirements.txt
```

## Cookie 设置

爬虫需要雪球登录态 Cookie。首次使用前运行：

```bash
python setup_cookie.py
```

这会打开 Chrome 让你登录雪球，登录后自动保存 Cookie 到 `.cookies.json`（已在 .gitignore 中排除，不会被提交）。

## 使用

### 股票大V观点

```bash
python main.py stock <股票代码> [--min-reply 20] [--max-pages 20] [--output ./output]
```

### 用户帖子爬取

```bash
python main.py user <用户ID或用户名> [--max-pages 10] [--days 30] [--column] [--output ./output]
```

- `--column` 仅抓取专栏文章
- `--days N` 只保留最近 N 天的帖子
- 支持直接传用户名，会自动搜索解析为数字ID

### 搜索用户

```bash
python main.py search <关键词>
```

## 示例

```bash
# 爬取大族激光的大V观点
python main.py stock SZ002738 --min-reply 20 --max-pages 10

# 爬取用户"治雨"的全部专栏
python main.py user 治雨 --column --max-pages 20

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
