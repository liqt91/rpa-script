"""
DrissionPage 文档定向爬虫（有头模式）- 修正版
- 使用指定的 Chrome 浏览器和用户目录
- 从首页发现所有页面，但只下载指定路径下的文档
- 保存为 Markdown 格式，适合导入 Dify 知识库
"""

import os
import re
import time
from urllib.parse import urljoin, urlparse
from DrissionPage import ChromiumPage, ChromiumOptions  # 导入 ChromiumOptions


class DrissionPageDocsCrawler:
    """定向爬取指定路径下的文档"""
    
    def __init__(self, chrome_path, user_data_path, output_dir="drissionpage_docs", delay=1):
        # 浏览器配置
        self.chrome_path = chrome_path
        self.user_data_path = user_data_path
        
        # 目标路径前缀（只下载这些路径下的页面）
        self.target_paths = [
            '/browser_control/',
            '/SessionPage/',
            '/advance/'
        ]
        
        self.base_url = "https://drissionpage.cn"  # 改为主流 https
        self.output_dir = output_dir
        self.delay = delay
        self.page = None
        self.visited = set()
        self.target_links = []  # 只保存目标路径下的链接
        
    def init_browser(self):
        """初始化有头浏览器"""
        print("正在启动 Chrome 浏览器...")
        print(f"  浏览器路径: {self.chrome_path}")
        print(f"  用户数据目录: {self.user_data_path}")
        
        # 创建 ChromiumOptions 对象来配置浏览器
        # 注意：参数名是 binary_location 和 user_data_dir，在 ChromiumOptions 中使用点号设置
        co = ChromiumOptions()
        co.set_browser_path(self.chrome_path)  # 设置浏览器可执行文件路径
        co.set_user_data_path(self.user_data_path)  # 设置用户数据目录
        co.set_headless(False)  # 有头模式
        co.set_argument('--no-sandbox')  # 添加启动参数
        
        # 可选：添加更多参数避免被检测
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.set_argument('--disable-gpu')
        
        # 启动浏览器
        self.page = ChromiumPage(addr_or_opts=co)
        print("浏览器启动成功\n")
    
    def run(self):
        """运行爬虫"""
        print("=" * 60)
        print("DrissionPage 文档定向爬虫启动")
        print(f"目标网站: {self.base_url}")
        print(f"保存目录: {self.output_dir}")
        print(f"限定路径: {', '.join(self.target_paths)}")
        print("=" * 60)
        
        # 1. 初始化浏览器
        self.init_browser()
        
        # 2. 创建保存目录
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 3. 从首页发现所有目标链接
        print("\n[步骤1] 正在从首页扫描并筛选目标页面...")
        self.discover_target_links()
        
        # 4. 爬取所有目标页面
        print(f"\n[步骤2] 开始爬取目标页面，共 {len(self.target_links)} 个...")
        self.crawl_target_pages()
        
        # 5. 生成索引文件
        print("\n[步骤3] 生成索引文件...")
        self.generate_index()
        
        # 6. 关闭浏览器
        if self.page:
            self.page.quit()
        
        print("\n" + "=" * 60)
        print(f"✅ 爬取完成！文档已保存到: {self.output_dir}")
        print(f"   共下载 {len(self.target_links)} 个页面")
        print("=" * 60)
    
    def discover_target_links(self):
        """从首页递归发现所有链接，但只记录目标路径下的"""
        start_url = self.base_url
        to_visit = [start_url]
        
        while to_visit:
            url = to_visit.pop(0)
            if url in self.visited:
                continue
                
            print(f"  扫描: {url}")
            self.visited.add(url)
            
            try:
                self.page.get(url)
                time.sleep(self.delay)
                
                # 获取当前页面所有链接
                links = self.page.eles('tag:a')
                if not links:
                    continue
                
                for link in links:
                    href = link.link
                    if not href:
                        continue
                    
                    full_url = urljoin(url, href)
                    
                    # 只处理本站链接
                    if not full_url.startswith(self.base_url):
                        continue
                    
                    # 如果链接在目标路径下，记录下来
                    if self.is_target_path(full_url):
                        if full_url not in self.target_links:
                            self.target_links.append(full_url)
                            print(f"    发现目标: {full_url}")
                    
                    # 继续递归发现新链接（不限路径）
                    if full_url not in self.visited and full_url not in to_visit:
                        to_visit.append(full_url)
                        
            except Exception as e:
                print(f"  扫描失败 {url}: {e}")
        
        # 去重并排序
        self.target_links = sorted(list(set(self.target_links)))
        print(f"\n共发现 {len(self.target_links)} 个目标页面")
    
    def is_target_path(self, url):
        """判断 URL 是否属于目标路径"""
        parsed = urlparse(url)
        path = parsed.path
        
        # 确保路径以 / 结尾进行比较
        if not path.endswith('/'):
            path = path + '/'
        
        for target in self.target_paths:
            if path.startswith(target):
                return True
        return False
    
    def crawl_target_pages(self):
        """爬取所有目标页面并保存"""
        if not self.target_links:
            print("警告：没有发现任何目标页面！")
            return
        
        for idx, url in enumerate(self.target_links, 1):
            print(f"\n  [{idx:3d}/{len(self.target_links)}] 爬取: {url}")
            
            try:
                self.page.get(url)
                time.sleep(self.delay)
                
                # 提取页面内容（优先使用 article）
                content_data = self.extract_content(url)
                
                if content_data and content_data['content']:
                    self.save_as_markdown(content_data, idx)
                    print(f"      ✅ 已保存: {content_data['title']} ({len(content_data['content'])} 字符)")
                else:
                    print(f"      ⚠️ 未能提取到有效内容")
                    
            except Exception as e:
                print(f"      ❌ 错误: {e}")
    
    def extract_content(self, url):
        """提取页面内容，优先使用 article 标签"""
        # 获取标题
        title = self.get_page_title()
        
        # 提取主要内容
        content = ""
        
        # 优先查找 article 标签
        article = self.page('tag:article')
        if article:
            # 获取 article 内部的 HTML 并转换
            if hasattr(article, 'html'):
                content = self.html_to_markdown(article.html)
            else:
                content = article.text
            if len(content) > 200:
                return {'url': url, 'title': title, 'content': content}
        
        # 备选：查找 main 标签
        main_elem = self.page('tag:main')
        if main_elem:
            if hasattr(main_elem, 'html'):
                content = self.html_to_markdown(main_elem.html)
            else:
                content = main_elem.text
            if len(content) > 200:
                return {'url': url, 'title': title, 'content': content}
        
        # 备选：查找 div.main-content 或 div.content
        for selector in ['div.main-content', 'div.content', '.markdown-body']:
            elem = self.page(selector)
            if elem:
                if hasattr(elem, 'html'):
                    content = self.html_to_markdown(elem.html)
                else:
                    content = elem.text
                if len(content) > 200:
                    return {'url': url, 'title': title, 'content': content}
        
        # 最后尝试：获取 body 并过滤
        body = self.page('tag:body')
        if body:
            content = self.filter_main_content(body.text)
            if content and len(content) > 100:
                return {'url': url, 'title': title, 'content': content}
        
        return None
    
    def get_page_title(self):
        """获取页面标题"""
        title_elem = self.page('tag:title')
        if title_elem:
            title = title_elem.text.strip()
            title = re.sub(r'\s*[-|]\s*DrissionPage.*$', '', title)
            if title:
                return title
        
        h1 = self.page('tag:h1')
        if h1:
            return h1.text.strip()
        
        path = urlparse(self.page.url).path
        name = path.strip('/').split('/')[-1].replace('-', ' ').title()
        return name if name else "未命名"
    
    def html_to_markdown(self, html_content):
        """简单但有效的 HTML 转 Markdown"""
        if not html_content:
            return ""
        
        # 移除干扰标签及其内容
        for tag in ['script', 'style', 'nav', 'footer', 'aside', 'header']:
            html_content = re.sub(f'<{tag}[^>]*>.*?</{tag}>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # 转换标题
        html_content = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\n# \1\n', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<h4[^>]*>(.*?)</h4>', r'\n#### \1\n', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<h5[^>]*>(.*?)</h5>', r'\n##### \1\n', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<h6[^>]*>(.*?)</h6>', r'\n###### \1\n', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # 转换代码块（保留语言标识）
        # 匹配 <pre><code class="language-python">...</code></pre>
        html_content = re.sub(
            r'<pre><code[^>]*class="language-([^"]+)"[^>]*>(.*?)</code></pre>',
            r'\n```\1\n\2\n```\n',
            html_content,
            flags=re.DOTALL | re.IGNORECASE
        )
        # 匹配普通 <pre><code>...</code></pre>
        html_content = re.sub(
            r'<pre><code[^>]*>(.*?)</code></pre>',
            r'\n```\n\1\n```\n',
            html_content,
            flags=re.DOTALL | re.IGNORECASE
        )
        # 匹配独立的 <pre> 标签
        html_content = re.sub(
            r'<pre[^>]*>(.*?)</pre>',
            r'\n```\n\1\n```\n',
            html_content,
            flags=re.DOTALL | re.IGNORECASE
        )
        
        # 转换行内代码
        html_content = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # 转换链接
        html_content = re.sub(
            r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
            r'[\2](\1)',
            html_content,
            flags=re.DOTALL | re.IGNORECASE
        )
        
        # 转换粗体
        html_content = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # 转换斜体
        html_content = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # 转换列表
        html_content = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # 转换段落
        html_content = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # 转换表格（简单处理）
        html_content = re.sub(r'<tr[^>]*>(.*?)</tr>', r'\1\n', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<td[^>]*>(.*?)</td>', r'\1\t', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<th[^>]*>(.*?)</th>', r'\1\t', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # 移除剩余的 HTML 标签
        html_content = re.sub(r'<[^>]+>', '', html_content)
        
        # 清理多余空白
        html_content = re.sub(r'\n\s*\n\s*\n', '\n\n', html_content)
        html_content = re.sub(r' +\n', '\n', html_content)
        html_content = html_content.strip()
        
        return html_content
    
    def filter_main_content(self, text):
        """从纯文本中过滤主要内容"""
        if not text:
            return ""
        
        lines = text.split('\n')
        filtered = []
        skip_keywords = ['导航', '菜单', 'footer', 'copyright', '备案号', '京ICP备']
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 跳过过短的行（可能是导航项）
            if len(line) < 20:
                skip = False
                for kw in skip_keywords:
                    if kw in line:
                        skip = True
                        break
                if skip:
                    continue
            
            filtered.append(line)
        
        return '\n'.join(filtered)
    
    def save_as_markdown(self, data, index):
        """保存为 Markdown 文件"""
        title = data['title']
        safe_title = re.sub(r'[\\/*?:"<>|]', '-', title)
        safe_title = safe_title.strip()[:80]
        
        # 使用路径作为文件名的一部分，便于识别
        parsed = urlparse(data['url'])
        path_part = parsed.path.strip('/').replace('/', '_')
        if path_part:
            filename = f"{index:03d}_{path_part}_{safe_title}.md"
        else:
            filename = f"{index:03d}_{safe_title}.md"
        
        filepath = os.path.join(self.output_dir, filename)
        
        md_content = [
            f"# {title}\n",
            "---",
            f"source_url: {data['url']}",
            f"crawl_date: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "---\n",
            data['content'],
            "\n---",
            f"📖 原文：[{title}]({data['url']})\n"
        ]
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_content))
        
        # 同时保存一份纯文本版本用于对比（可选，调试用）
        # txt_path = filepath.replace('.md', '.txt')
        # with open(txt_path, 'w', encoding='utf-8') as f:
        #     f.write(data['content'])
    
    def generate_index(self):
        """生成索引文件"""
        index_path = os.path.join(self.output_dir, "README.md")
        
        lines = [
            "# DrissionPage 文档定向抓取\n",
            f"> 抓取日期：{time.strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"> 来源：{self.base_url}\n",
            f"> 限定路径：{', '.join(self.target_paths)}\n",
            f"> 抓取页面数：{len(self.target_links)}\n",
            "\n## 📚 页面列表\n"
        ]
        
        for idx, url in enumerate(self.target_links, 1):
            parsed = urlparse(url)
            name = parsed.path.strip('/').replace('/', ' / ') or "首页"
            lines.append(f"{idx}. [{name}]({url})")
        
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))


def main():
    # 配置路径（请根据你的实际路径调整）
    chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    user_data_path = r'D:\Chrome_Work'
    
    # 检查路径是否存在
    if not os.path.exists(chrome_path):
        print(f"⚠️ 警告：未找到 Chrome 浏览器，路径: {chrome_path}")
        print("请确认路径是否正确")
        response = input("是否继续？(y/n): ")
        if response.lower() != 'y':
            return
    
    if not os.path.exists(user_data_path):
        print(f"⚠️ 警告：用户数据目录不存在，将自动创建: {user_data_path}")
        os.makedirs(user_data_path, exist_ok=True)
    
    # 创建爬虫并运行
    crawler = DrissionPageDocsCrawler(
        chrome_path=chrome_path,
        user_data_path=user_data_path,
        output_dir="drissionpage_docs",
        delay=1  # 请求间隔（秒）
    )
    
    crawler.run()


if __name__ == "__main__":
    main()