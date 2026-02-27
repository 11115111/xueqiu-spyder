"""
Cookie 设置工具
从 Chrome 浏览器开发者工具中复制 Cookie 值，粘贴到此处完成配置。

使用方法:
1. 在 Chrome 中打开 https://xueqiu.com
2. 按 F12 -> Application -> Cookies -> https://xueqiu.com
3. 运行此脚本，按提示粘贴 Cookie 值
"""
import json
import os

COOKIE_FILE = os.path.join(os.path.dirname(__file__), ".cookies.json")

REQUIRED_COOKIES = ["xq_a_token"]
OPTIONAL_COOKIES = ["xq_r_token", "xq_id_token", "u", "cookiesu"]


def main():
    print("=== 雪球 Cookie 设置工具 ===\n")
    print("请在 Chrome 中打开 https://xueqiu.com")
    print("按 F12 -> Application -> Cookies -> https://xueqiu.com\n")

    cookies = {}

    for name in REQUIRED_COOKIES:
        value = input(f"请粘贴 {name} 的值: ").strip()
        if not value:
            print(f"错误: {name} 不能为空")
            return
        cookies[name] = value

    for name in OPTIONAL_COOKIES:
        value = input(f"请粘贴 {name} 的值 (可跳过，直接回车): ").strip()
        if value:
            cookies[name] = value

    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2)

    print(f"\nCookie 已保存到 {COOKIE_FILE}")
    print("现在可以运行: python main.py <股票代码>")


if __name__ == "__main__":
    main()
