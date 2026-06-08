#!/usr/bin/env python3
"""
DrissionPage 官方文档抓取工具
- 从目标前缀路径出发，递归发现所有相关页面
- 抓取每个页面的 <article> 标签内容
- 转换为 Markdown 保存到本地

依赖:
    pip install markdownify

用法:
    python local_jobs/drission_docs_scraper.py
"""

import os
import re
import sys
from urllib.parse import urljoin

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.repo.chrome_utils import connect_chrome

BASE_URL = "https://drissionpage.cn"
TARGET_PATHS = [
    "/browser_control",
    "/SessionPage",
    "/advance",
]
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drission_docs")


class DrissionDocsScraper:
    def __init__(self, page):
        self.page = page
        self.visited = set()
        self.all_links = []

    def is_target_link(self, full_url):
        """只保留本站且匹配目标路径前缀的链接。"""
        if not full_url.startswith(BASE_URL):
            return False
        path = full_url[len(BASE_URL):]
        return any(path.startswith(prefix) for prefix in TARGET_PATHS)

    def get_page_links(self):
        """获取当前页面中的所有链接（绝对 URL，过滤掉纯锚点）。"""
        links = set()
        try:
            for a in self.page.eles("tag:a"):
                href = a.attr("href") or ""
                # 跳过纯锚点跳转（如 #XXX）
                if href.startswith("#"):
                    continue
                if href:
                    full_url = urljoin(self.page.url, href)
                    # 去掉 URL 中的 fragment（#anchor），避免同一页被当作多页
                    if "#" in full_url:
                        full_url = full_url.split("#")[0]
                    links.add(full_url)
        except Exception as e:
            print(f"    提取链接失败: {e}")
        return links

    def discover(self):
        """从首页开始递归发现所有匹配前缀的页面（BFS）。"""
        to_visit = [BASE_URL]

        while to_visit:
            url = to_visit.pop(0)
            if url in self.visited:
                continue

            print(f"  扫描: {url}")
            self.visited.add(url)

            try:
                self.page.get(url)
                self.page.wait.doc_loaded()

                # 只把匹配前缀的页面加入最终列表
                if self.is_target_link(url):
                    if url not in self.all_links:
                        self.all_links.append(url)

                for full_url in self.get_page_links():
                    if not full_url.startswith(BASE_URL):
                        continue
                    path = full_url[len(BASE_URL):]
                    # 只遍历站内的 /browser_control /SessionPage /advance 路径
                    if any(path.startswith(prefix) for prefix in TARGET_PATHS):
                        print(f"      符合前缀: {path}")
                        if full_url not in self.visited and full_url not in to_visit:
                            to_visit.append(full_url)
                            if full_url not in self.all_links:
                                print(f"      发现新页面: {full_url}")
            except Exception as e:
                print(f"  扫描失败 {url}: {e}")

        self.all_links = sorted(list(set(self.all_links)))
        print(f"\n  共发现 {len(self.all_links)} 个目标页面")
        return self.all_links

    def extract_article(self, url):
        """访问 URL，提取 <article> 标签的 outer HTML。"""
        print(f"  抓取: {url}")
        self.page.get(url)
        self.page.wait.doc_loaded()

        try:
            article = self.page.ele("tag:article", timeout=5)
            return article.html
        except Exception:
            print("    未找到 <article> 标签")
            return None

    def run(self):
        """执行完整流程：发现 → 抓取 → 保存。"""
        print("=" * 60)
        print("DrissionPage 官方文档抓取工具")
        print("=" * 60)

        # 1. 递归发现所有目标页面
        print("\n[1/3] 递归发现目标页面...")
        links = self.discover()
        for link in links:
            print(f"      {link}")

        # 2. 逐个抓取 article 并转 Markdown
        print("\n[2/3] 抓取 <article> 并转为 Markdown...")
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        saved = 0
        for url in links:
            html = self.extract_article(url)
            if html:
                md = html_to_md(html)
                path = url[len(BASE_URL):]
                save_md(path, md)
                saved += 1

        print("\n" + "=" * 60)
        print(f"完成！发现 {len(links)} 个页面，成功保存 {saved} 个")
        print(f"输出目录: {OUTPUT_DIR}")
        print("=" * 60)


# ==================== HTML → Markdown ====================

def html_to_md(html):
    """将 HTML 转换为 Markdown；优先使用 markdownify。"""
    try:
        from markdownify import markdownify as md
        return md(html, heading_style="ATX", strip=["script", "style"]).strip()
    except ImportError:
        print("    警告: 未安装 markdownify，使用简单降级转换")
        return _simple_html_to_md(html)


def _simple_html_to_md(html):
    """极简 HTML->Markdown 降级方案。"""
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)

    for i in range(6, 0, -1):
        html = re.sub(
            rf"<h{i}[^>]*>(.*?)</h{i}>",
            lambda m: "#" * i + " " + _strip_tags(m.group(1)) + "\n\n",
            html,
            flags=re.DOTALL,
        )

    html = re.sub(
        r"<pre[^>]*>\s*<code[^>]*>(.*?)</code>\s*</pre>",
        lambda m: "```\n" + _strip_tags(m.group(1)) + "\n```\n\n",
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r"<pre[^>]*>(.*?)</pre>",
        lambda m: "```\n" + _strip_tags(m.group(1)) + "\n```\n\n",
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r"<code[^>]*>(.*?)</code>",
        lambda m: "`" + _strip_tags(m.group(1)) + "`",
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r"<p[^>]*>(.*?)</p>",
        lambda m: _strip_tags(m.group(1)) + "\n\n",
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r"<li[^>]*>(.*?)</li>",
        lambda m: "- " + _strip_tags(m.group(1)) + "\n",
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        lambda m: f"[{_strip_tags(m.group(2))}]({m.group(1)})",
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r"<strong[^>]*>(.*?)</strong>",
        lambda m: "**" + _strip_tags(m.group(1)) + "**",
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r"<em[^>]*>(.*?)</em>",
        lambda m: "*" + _strip_tags(m.group(1)) + "*",
        html,
        flags=re.DOTALL,
    )
    html = re.sub(r"<table[^>]*>.*?</table>", lambda m: _table_to_md(m.group(0)), html, flags=re.DOTALL)
    html = _strip_tags(html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def _strip_tags(html):
    return re.sub(r"<[^>]+>", "", html).strip()


def _table_to_md(html):
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.DOTALL)
    lines = []
    for i, row in enumerate(rows):
        cells = re.findall(r"<[tdh][^>]*>(.*?)</[tdh]>", row, flags=re.DOTALL)
        line = "| " + " | ".join(_strip_tags(c) for c in cells) + " |"
        lines.append(line)
        if i == 0:
            lines.append("|" + "|".join(" --- " for _ in cells) + "|")
    return "\n".join(lines) + "\n\n"


def save_md(path, content):
    """保存为 Markdown 文件；路径中的 / 替换为 _ 作为文件名。"""
    filename = path.strip("/").replace("/", "_") or "index"
    if not filename.endswith(".md"):
        filename += ".md"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"    已保存: {filepath}")
    return filepath


def show_menu():
    """显示交互式菜单并返回用户选择。"""
    print("=" * 50)
    print("  DrissionPage 文档抓取工具")
    print("=" * 50)
    print()
    print("  [1] 递归抓取 — 从首页发现所有目标页面")
    print("  [2] 单页抓取 — 指定 URL 抓取单个页面")
    print("  [3] 退出")
    print()
    print("-" * 50)
    choice = input("  请选择: ").strip()
    return choice


def main():
    while True:
        choice = show_menu()

        if choice == "3":
            print("\n  再见！")
            break

        if choice not in ("1", "2"):
            print("\n  无效选项，请重新选择\n")
            continue

        print("\n[连接] 正在连接 Chrome...")
        page = connect_chrome()
        if not page:
            print("  无法连接 Chrome，请确保 Chrome 已在调试模式运行（端口 9222）")
            print()
            continue

        if choice == "1":
            scraper = DrissionDocsScraper(page)
            scraper.run()

        elif choice == "2":
            url = input(f"\n  请输入要抓取的页面 URL（如 {BASE_URL}/browser_control）: ").strip()
            if not url:
                print("  URL 为空，取消操作")
                print()
                continue

            os.makedirs(OUTPUT_DIR, exist_ok=True)
            scraper = DrissionDocsScraper(page)
            html = scraper.extract_article(url)
            if html:
                md = html_to_md(html)
                path = url[len(BASE_URL):] if url.startswith(BASE_URL) else url.replace("://", "_").replace("/", "_")
                save_md(path, md)
                print("\n  完成！")
            else:
                print("\n  抓取失败，未找到 <article> 标签")
            print()


if __name__ == "__main__":

    main()
