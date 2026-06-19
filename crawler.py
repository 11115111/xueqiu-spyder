import time
import re
import random
import logging
import subprocess
import os
import sys
import shutil
import urllib.parse
from playwright.sync_api import sync_playwright

import config

logger = logging.getLogger(__name__)

USER_DATA_DIR = os.path.join(os.path.dirname(__file__), ".chrome-debug-profile")
DEBUG_PORT = 9222


def _find_chrome():
    """跨平台查找 Chrome/Chromium 可执行文件路径"""
    # 1. 允许通过环境变量显式指定
    env_path = os.environ.get("CHROME_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    candidates = []
    if sys.platform.startswith("win"):
        # Windows 常见安装位置（用户级 + 系统级）
        for var in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
            base = os.environ.get(var)
            if base:
                candidates.append(
                    os.path.join(base, r"Google\Chrome\Application\chrome.exe")
                )
                candidates.append(
                    os.path.join(base, r"Google\Chrome Beta\Application\chrome.exe")
                )
                candidates.append(
                    os.path.join(base, r"Microsoft\Edge\Application\msedge.exe")
                )
    elif sys.platform == "darwin":
        candidates += [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    else:
        # Linux：先查 PATH，再查常见绝对路径
        for name in ("google-chrome", "google-chrome-stable", "chromium",
                     "chromium-browser", "microsoft-edge"):
            found = shutil.which(name)
            if found:
                return found
        candidates += [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ]

    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


CHROME_PATH = _find_chrome()


class CrawlerError(Exception):
    pass


class XueqiuCrawler:
    """通过连接本地 Chrome 调试端口来复用真实浏览器环境，绕过 WAF"""

    def __init__(self):
        self._pw = None
        self._browser = None
        self._page = None
        self._connect_chrome()

    def _connect_chrome(self):
        """启动带调试端口的 Chrome 并连接"""
        # 先尝试连接已有的调试端口
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.connect_over_cdp(
                f"http://127.0.0.1:{DEBUG_PORT}"
            )
            logger.info("已连接到运行中的 Chrome")
        except Exception:
            logger.info("未检测到调试端口，正在启动 Chrome...")
            self._launch_chrome()
            time.sleep(3)
            self._browser = self._pw.chromium.connect_over_cdp(
                f"http://127.0.0.1:{DEBUG_PORT}"
            )
            logger.info("Chrome 启动并连接成功")

        # 获取或创建页面
        contexts = self._browser.contexts
        if contexts and contexts[0].pages:
            self._page = contexts[0].pages[0]
        else:
            self._page = self._browser.contexts[0].new_page()

        # 确保在雪球域名下
        if "xueqiu.com" not in self._page.url:
            self._page.goto(config.XUEQIU_HOME, wait_until="domcontentloaded", timeout=15000)

    def _launch_chrome(self):
        """以调试模式启动 Chrome"""
        if not CHROME_PATH:
            raise CrawlerError(
                "未找到 Chrome 可执行文件。请安装 Google Chrome，"
                "或通过环境变量 CHROME_PATH 指定 chrome.exe 的完整路径。\n"
                "例如 (Windows PowerShell):\n"
                r'  $env:CHROME_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"'
            )
        cmd = [
            CHROME_PATH,
            f"--remote-debugging-port={DEBUG_PORT}",
            f"--user-data-dir={USER_DATA_DIR}",
            "--no-first-run",
            "https://xueqiu.com/",
        ]
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            raise CrawlerError(
                f"无法启动 Chrome (路径: {CHROME_PATH})。"
                "请确认 Chrome 已正确安装，或通过环境变量 CHROME_PATH 指定其完整路径。"
            )

    def _fetch_json(self, url, params=None):
        """在浏览器内 fetch API，返回 JSON"""
        query = "&".join(f"{k}={v}" for k, v in (params or {}).items())
        full_url = f"{url}?{query}" if query else url

        for attempt in range(config.MAX_RETRIES):
            time.sleep(config.REQUEST_DELAY)
            try:
                result = self._page.evaluate(
                    """async (url) => {
                        try {
                            const resp = await fetch(url);
                            const ct = resp.headers.get('content-type') || '';
                            if (!ct.includes('json')) {
                                return {ok: false, error: 'not json'};
                            }
                            return {ok: true, data: await resp.json()};
                        } catch(e) {
                            return {ok: false, error: e.message};
                        }
                    }""",
                    full_url,
                )

                if result.get("ok"):
                    return result["data"]

                logger.warning(f"API 请求失败: {result.get('error')} (attempt {attempt + 1})")
            except Exception as e:
                if attempt == config.MAX_RETRIES - 1:
                    raise CrawlerError(f"请求失败 ({full_url}): {e}")
                time.sleep(2 ** attempt)

        raise CrawlerError(f"超过最大重试次数: {full_url}")

    def get_stock_posts(self, symbol, sort="reply", page=1, count=None):
        """获取某只股票的讨论帖"""
        if count is None:
            count = config.POSTS_PER_PAGE
        params = {
            "symbol": symbol,
            "sort": sort,
            "source": "all",
            "count": count,
            "page": page,
        }
        data = self._fetch_json(config.SEARCH_STATUS_URL, params)
        return data.get("list", [])

    def get_user_posts(self, user_id, page=1, count=None):
        """获取用户的动态帖子"""
        if count is None:
            count = config.USER_POSTS_COUNT
        params = {
            "user_id": user_id,
            "page": page,
            "count": count,
        }
        data = self._fetch_json(config.USER_TIMELINE_URL, params)
        if data.get("error_code"):
            logger.warning(f"用户 {user_id} API 错误: {data.get('error_description', data.get('error_code'))}")
            return []
        statuses = data.get("statuses", [])
        return statuses if statuses else data.get("list", [])

    def get_user_all_posts(self, user_id, max_pages=10):
        """通过导航到用户主页来获取其帖子（绕过登录限制）"""
        user_page = self._browser.contexts[0].new_page()
        all_statuses = []
        try:
            user_page.goto(
                f"https://xueqiu.com/u/{user_id}",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            try:
                user_page.wait_for_selector(".user-name", timeout=5000)
            except Exception:
                user_page.wait_for_timeout(1000)

            for page_num in range(1, max_pages + 1):
                time.sleep(config.REQUEST_DELAY)
                result = user_page.evaluate(
                    """async (args) => {
                        try {
                            const resp = await fetch(
                                `/v4/statuses/user_timeline.json?user_id=${args.uid}&page=${args.page}&count=20`
                            );
                            const ct = resp.headers.get('content-type') || '';
                            if (!ct.includes('json')) return {ok: false, error: 'not json'};
                            const data = await resp.json();
                            if (data.error_code) return {ok: false, error: data.error_description};
                            return {ok: true, statuses: data.statuses || [], count: data.count};
                        } catch(e) { return {ok: false, error: e.message}; }
                    }""",
                    {"uid": user_id, "page": page_num},
                )
                if not result.get("ok"):
                    logger.warning(f"用户 {user_id} 第 {page_num} 页失败: {result.get('error')}")
                    break
                statuses = result.get("statuses", [])
                if not statuses:
                    break
                all_statuses.extend(statuses)
                logger.info(f"  第 {page_num} 页获取 {len(statuses)} 条 (共 {len(all_statuses)})")
        finally:
            user_page.close()
        return all_statuses

    def get_post_full_text(self, target):
        """访问帖子详情页获取完整内容，target 如 /5243796549/376934652"""
        detail_page = self._browser.contexts[0].new_page()
        try:
            detail_page.goto(
                f"https://xueqiu.com{target}",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            try:
                detail_page.wait_for_selector(".article__bd__detail", timeout=5000)
            except Exception:
                pass
            text = detail_page.evaluate("""() => {
                const el = document.querySelector('.article__bd__detail');
                return el ? el.textContent.trim() : '';
            }""")
            return text
        except Exception as e:
            logger.warning(f"获取帖子详情失败 {target}: {e}")
            return ""
        finally:
            detail_page.close()

    def enrich_posts_full_text(self, posts):
        """对 description 被截断的帖子，访问详情页补全内容"""
        for post in posts:
            desc = post.get("description", "") or ""
            text = post.get("text", "") or ""
            target = post.get("target", "")
            # 如果 text 为空且 description 以 ... 结尾，说明被截断
            if not text and desc.endswith("...") and target:
                time.sleep(config.REQUEST_DELAY)
                full = self.get_post_full_text(target)
                if full:
                    post["text"] = full
                    logger.info(f"  补全帖子 {target} ({len(full)} 字)")
        return posts

    def get_user_info(self, user_id):
        """获取用户基本信息"""
        user_page = self._browser.contexts[0].new_page()
        try:
            user_page.goto(
                f"https://xueqiu.com/u/{user_id}",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            try:
                user_page.wait_for_selector(".user-name", timeout=5000)
            except Exception:
                pass
            info = user_page.evaluate("""() => {
                let name = document.querySelector('.user-name')?.textContent?.trim() || '';
                if (!name) {
                    const title = document.title || '';
                    if (title.includes(' - 雪球')) name = title.replace(' - 雪球', '').trim();
                }
                return {screen_name: name};
            }""")
            return info
        finally:
            user_page.close()

    def search_user(self, keyword):
        """搜索用户，返回 [{name, href, uid}] 列表"""
        encoded = urllib.parse.quote(keyword)
        url = f"https://xueqiu.com/k?q={encoded}&forceRedirect=1&page=1&type=user"
        search_page = self._browser.contexts[0].new_page()
        try:
            search_page.goto(url, wait_until="domcontentloaded", timeout=15000)
            try:
                search_page.wait_for_selector(
                    ".search__user__card__content, a.user-name", timeout=5000
                )
            except Exception:
                pass
            users = search_page.evaluate("""() => {
                const cards = document.querySelectorAll('.search__user__card__content');
                const result = [];
                for (const card of cards) {
                    const nameEl = card.querySelector('.user-name');
                    const descEl = card.querySelector('p');
                    result.push({
                        name: nameEl ? nameEl.textContent.trim() : '',
                        href: nameEl ? nameEl.getAttribute('href') : '',
                        desc: descEl ? descEl.textContent.trim().substring(0, 80) : ''
                    });
                }
                if (!result.length) {
                    const anchors = document.querySelectorAll('a.user-name');
                    for (const a of anchors) {
                        result.push({
                            name: a.textContent.trim(),
                            href: a.getAttribute('href') || ''
                        });
                    }
                }
                return result;
            }""")
            # 解析 href 中的 uid
            for u in users:
                u["uid"] = self._extract_uid_from_href(u.get("href", ""))
            return users
        finally:
            search_page.close()

    def _extract_uid_from_href(self, href):
        """从 href 中提取数字 uid，如 /u/1234 -> '1234'"""
        if not href:
            return ""
        m = re.match(r"/u/(\d+)", href)
        if m:
            return m.group(1)
        # 虚荣路径如 /zzyandsnow，需要 resolve
        return ""

    def resolve_user_id(self, vanity_path):
        """将虚荣路径（如 /zzyandsnow）解析为数字 user_id"""
        resolve_page = self._browser.contexts[0].new_page()
        try:
            resolve_page.goto(
                f"https://xueqiu.com{vanity_path}",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            try:
                resolve_page.wait_for_selector(".user-name", timeout=5000)
            except Exception:
                pass
            # 从跳转后的 URL 或页面内容提取数字 ID
            final_url = resolve_page.url
            m = re.search(r"/u/(\d+)", final_url)
            if m:
                return m.group(1)
            # 从页面 JS 变量中提取
            uid = resolve_page.evaluate("""() => {
                const m = document.body?.innerHTML?.match(/"id":(\\d{5,})/);
                return m ? m[1] : '';
            }""")
            return uid or ""
        finally:
            resolve_page.close()

    def find_user_id(self, keyword):
        """搜索用户名并返回第一个精确匹配的数字 uid"""
        users = self.search_user(keyword)
        if not users:
            raise CrawlerError(f"未找到用户: {keyword}")
        # 优先精确匹配
        target = None
        for u in users:
            if u["name"] == keyword:
                target = u
                break
        if not target:
            target = users[0]
            logger.info(f"未精确匹配，使用第一个结果: {target['name']}")
        # 如果已有数字 uid 直接返回
        if target.get("uid"):
            return target["uid"], target["name"]
        # 否则解析虚荣路径
        href = target.get("href", "")
        if href:
            uid = self.resolve_user_id(href)
            if uid:
                return uid, target["name"]
        raise CrawlerError(f"无法解析用户ID: {target}")

    def _throttle(self, page_num):
        """请求间隔节流：基础间隔 + 随机抖动，并每隔若干页做一次长休息，模拟真人节奏"""
        delay = config.REQUEST_DELAY + random.uniform(0, config.REQUEST_DELAY_JITTER)
        time.sleep(delay)
        every = getattr(config, "LONG_REST_EVERY", 0)
        if every and page_num > 0 and page_num % every == 0:
            rest = config.LONG_REST_SECONDS + random.uniform(0, config.REQUEST_DELAY_JITTER)
            logger.info(f"  已爬取 {page_num} 页，休息 {rest:.0f}s 以规避风控...")
            time.sleep(rest)

    def _fetch_timeline_page(self, user_page, user_id, page_num, count=20):
        """获取用户 timeline 的某一页，带限流检测与指数退避重试。

        返回 (statuses, status_flag)：
          status_flag 为 'ok' | 'empty' | 'failed'
        """
        for attempt in range(config.RATE_LIMIT_MAX_RETRIES):
            result = user_page.evaluate(
                """async (args) => {
                    try {
                        const resp = await fetch(
                            `/v4/statuses/user_timeline.json?user_id=${args.uid}&page=${args.page}&count=${args.count}`
                        );
                        const status = resp.status;
                        const ct = resp.headers.get('content-type') || '';
                        if (status === 429 || status === 403) return {ok: false, rateLimited: true, status, error: 'rate_limited'};
                        if (!ct.includes('json')) return {ok: false, rateLimited: true, status, error: 'not_json(可能被风控拦截)'};
                        const data = await resp.json();
                        if (data.error_code) return {ok: false, status, error_code: data.error_code, error: data.error_description};
                        return {ok: true, status, statuses: data.statuses || []};
                    } catch(e) { return {ok: false, error: e.message}; }
                }""",
                {"uid": user_id, "page": page_num, "count": count},
            )

            if result.get("ok"):
                statuses = result.get("statuses", [])
                return statuses, ("ok" if statuses else "empty")

            # 限流/被风控：指数退避后重试同一页
            if result.get("rateLimited"):
                backoff = config.RATE_LIMIT_BACKOFF * (2 ** attempt) + random.uniform(0, 5)
                logger.warning(
                    f"  第 {page_num} 页疑似被限流 (status={result.get('status')}, "
                    f"{result.get('error')})，{backoff:.0f}s 后重试 "
                    f"({attempt + 1}/{config.RATE_LIMIT_MAX_RETRIES})"
                )
                time.sleep(backoff)
                continue

            # 其它错误（如用户隐私设置）不重试
            logger.warning(f"  第 {page_num} 页失败: {result.get('error')}")
            return [], "failed"

        logger.error(f"  第 {page_num} 页超过最大重试次数，疑似被持续限流")
        return [], "failed"

    def crawl_user_all_posts(self, user_id, max_pages=None, stop_before_ms=None):
        """爬取指定用户的全部发帖，内置反封禁节流策略。

        参数:
            user_id:        用户数字 ID
            max_pages:      最大翻页数，None 表示一直翻到没有更多（受 config.MAX_USER_PAGES 上限保护）
            stop_before_ms: 若提供（毫秒时间戳），当某页最旧帖子早于该时间时提前停止，
                            避免为了少量旧帖继续翻页而增加被封风险

        返回: (screen_name, all_statuses)
        """
        page_cap = max_pages or getattr(config, "MAX_USER_PAGES", 500)
        user_page = self._browser.contexts[0].new_page()
        all_statuses = []
        screen_name = str(user_id)
        try:
            user_page.goto(
                f"https://xueqiu.com/u/{user_id}",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            try:
                user_page.wait_for_selector(".user-name", timeout=5000)
            except Exception:
                pass

            # 在同一页面获取用户名（复用页面减少导航 = 减少被风控的请求次数）
            screen_name = user_page.evaluate("""() => {
                let name = document.querySelector('.user-name')?.textContent?.trim() || '';
                if (!name) {
                    const title = document.title || '';
                    if (title.includes(' - 雪球')) name = title.replace(' - 雪球', '').trim();
                }
                return name;
            }""") or str(user_id)

            for page_num in range(1, page_cap + 1):
                self._throttle(page_num - 1)
                statuses, flag = self._fetch_timeline_page(user_page, user_id, page_num)

                if flag == "failed":
                    break
                if flag == "empty":
                    logger.info(f"  第 {page_num} 页无更多帖子，爬取结束")
                    break

                all_statuses.extend(statuses)
                logger.info(f"  第 {page_num}/{page_cap} 页获取 {len(statuses)} 条 (共 {len(all_statuses)})")

                # 按时间提前停止：timeline 为倒序，本页最旧帖早于 cutoff 则后续都更旧
                if stop_before_ms is not None:
                    oldest = min((s.get("created_at") or 0) for s in statuses)
                    if oldest < stop_before_ms:
                        logger.info(f"  已到达时间下限，提前停止翻页")
                        break
        finally:
            user_page.close()
        return screen_name, all_statuses

    def get_user_all_posts_with_info(self, user_id, max_pages=10):
        """在同一个页面中获取用户信息和所有帖子（兼容旧接口，内部复用反封禁爬取逻辑）"""
        return self.crawl_user_all_posts(user_id, max_pages=max_pages)

    def close(self):
        """断开浏览器连接"""
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
