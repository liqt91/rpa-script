"""
DrissionPage 文档爬虫 - 有头浏览器模式
针对指定路径：/browser_control, /SessionPage, /advance
"""

import os
import re
import time
from urllib.parse import urljoin, urlparse
from DrissionPage import ChromiumPage


class DrissionPageCrawler:
    """有头模式爬虫 - 只爬取指定路径的文档"""
    
    def __init__(self, output_dir="drissionpage_docs", headless=False):
        """
        初始化爬虫
        :param output_dir: 输出目录
        :param headless: 是否使用无头模式（False = 有头，可以看到浏览器）
        """
        self.base_url = "https://drissionpage.cn"
        self.output_dir = output_dir
        self.headless = headless
        self.page = None
        self.visited = set()
        self.target_paths = [
            '/browser_control',
            '/SessionPage', 
            '/advance'
        ]
        self.all_links = []
        
    def start_browser(self):
        """启动浏览器"""
        print("正在启动浏览器...")
        self.page = ChromiumPage()
        # 可选：设置超时时间
        self.page.set.timeouts(base=30)
        print("浏览器已启动")
        
    def run(self):
        """运行爬虫"""
        print("=" * 60)
        print("DrissionPage 文档爬虫（有头模式）")
        print(f"目标网站: {self.base_url}")
        print(f"目标路径: {', '.join(self.target_paths)}")
        print(f"保存目录: {self.output_dir}")
        print("=" * 60)
        
        # 1. 启动浏览器
        self.start_browser()
        
        # 2. 创建保存目录
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 3. 发现目标页面
        print("\n[步骤1] 正在扫描目标路径下的所有页面...")
        self.discover_target_pages()
        
        # 4. 爬取所有发现的页面
        print(f"\n[步骤2] 开始爬取，共发现 {len(self.all_links)} 个页面...")
        self.crawl_all_pages()
        
        # 5. 生成索引文件
        print("\n[步骤3] 生成索引文件...")
        self.generate_index()
        
        # 6. 关闭浏览器
        self.page.quit()
        
        print("\n" + "=" * 60)
        print(f"✅ 爬取完成！文档已保存到: {self.output_dir}")
        print(f"   共处理 {len(self.all_links)} 个页面")
        print("=" * 60)
    
    def discover_target_pages(self):
        """从目标路径开始，递归发现所有相关页面"""
        # 构建起始URL列表
        start_urls = [self.base_url + path for path in self.target_paths]
        
        to_visit = start_urls.copy()
        
        while to_visit:
            url = to_visit.pop(0)
            if url in self.visited:
                continue
                
            print(f"  扫描: {url}")
            self.visited.add(url)
            
            try:
                # 访问页面
                self.page.get(url)
                time.sleep(1)  # 等待页面加载
                
                # 添加当前URL到列表
                if url not in self.all_links:
                    self.all_links.append(url)
                
                # 获取页面中的所有链接
                all_links = self.get_all_links()
                
                for full_url in all_links:
                    # 只保留本站且匹配目标路径的链接
                    if self.is_target_link(full_url):
                        if full_url not in self.visited and full_url not in to_visit:
                            to_visit.append(full_url)
                            if full_url not in self.all_links:
                                print(f"      发现新页面: {full_url}")
                                
            except Exception as e:
                print(f"  扫描失败 {url}: {e}")
        
        # 去重并排序
        self.all_links = sorted(list(set(self.all_links)))
        print(f"\n  共发现 {len(self.all_links)} 个目标页面")
    
    def get_all_links(self):
        """获取当前页面中的所有链接"""
        links = set()
        
        try:
            # 获取所有 a 标签
            a_tags = self.page.eles('tag:a')
            if a_tags:
                for a in a_tags:
                    href = a.link
                    if href:
                        full_url = urljoin(self.page.url, href)
                        links.add(full_url)
        except Exception as e:
            print(f"    提取链接失败: {e}")
        
        return links
    
    def is_target_link(self, url):
        """
        判断链接是否为需要爬取的目标
        只保留匹配 target_paths 的页面
        """
        if not url.startswith(self.base_url):
            return False
        
        # 解析路径
        parsed = urlparse(url)
        path = parsed.path
        
        # 排除文件类型
        exclude_extensions = ['.jpg', '.png', '.gif', '.pdf', '.zip', '.ico', '.svg', '.css', '.js']
        for ext in exclude_extensions:
            if path.lower().endswith(ext):
                return False
        
        # 检查是否匹配目标路径
        for target_path in self.target_paths:
            # 匹配路径本身或其子路径
            if path == target_path or path.startswith(target_path + '/'):
                return True
        
        return False
    
    def crawl_all_pages(self):
        """爬取所有页面并保存"""
        success_count = 0
        
        for idx, url in enumerate(self.all_links, 1):
            print(f"\n  [{idx:3d}/{len(self.all_links)}] {url}")
            
            try:
                # 访问页面
                self.page.get(url)
                time.sleep(0.5)  # 礼貌等待
                
                # 等待页面主要内容加载
                self.wait_for_content()
                
                # 提取页面内容
                content_data = self.extract_content(url)
                
                if content_data and content_data['content']:
                    self.save_as_markdown(content_data, idx)
                    success_count += 1
                    print(f"      ✅ 已保存: {content_data['title']} ({len(content_data['content'])} 字符)")
                else:
                    print(f"      ⚠️ 未提取到内容")
                    
            except Exception as e:
                print(f"      ❌ 错误: {e}")
        
        print(f"\n  成功爬取 {success_count}/{len(self.all_links)} 个页面")
    
    def wait_for_content(self):
        """等待页面主要内容加载完成"""
        try:
            # 等待 article 或 main 标签出现
            self.page.wait.ele_display('tag:article', timeout=10)
        except:
            try:
                self.page.wait.ele_display('tag:main', timeout=5)
            except:
                pass
    
    def extract_content(self, url):
        """提取页面标题和正文内容"""
        # 获取标题
        title = self.get_title()
        
        # 尝试多种内容容器选择器
        content = ""
        container = None
        
        # 优先级从高到低
        selectors = [
            ('tag:article', 'article'),
            ('tag:main', 'main'),
            ('div.article-content', 'div.article-content'),
            ('div.post-content', 'div.post-content'),
            ('div.content', 'div.content'),
            ('div.markdown-body', 'div.markdown-body'),
            ('#main-content', '#main-content'),
            ('#content', '#content'),
        ]
        
        for selector, name in selectors:
            try:
                elem = self.page(selector)
                if elem and len(elem.text) > 200:
                    container = elem
                    print(f"      使用容器: {name}")
                    break
            except:
                continue
        
        # 提取内容
        if container:
            # 尝试获取HTML并转换为Markdown
            try:
                html_content = container.html
                content = self.html_to_markdown(html_content)
            except:
                content = container.text
        else:
            # 降级：获取整个body，但过滤掉导航
            body = self.page('tag:body')
            if body:
                content = self.filter_main_content(body.text)
        
        # 清理内容
        if content:
            content = self.clean_content(content)
        
        return {
            'url': url,
            'title': title,
            'content': content
        }
    
    def get_title(self):
        """获取页面标题"""
        # 优先从 h1 获取
        h1 = self.page('tag:h1')
        if h1:
            title = h1.text.strip()
            if title and len(title) < 200:
                return title
        
        # 从 title 标签获取
        title_elem = self.page('tag:title')
        if title_elem:
            title = title_elem.text.strip()
            # 移除网站名称后缀
            title = re.sub(r'\s*[-|]\s*DrissionPage.*$', '', title)
            if title:
                return title
        
        # 从 URL 获取
        path = urlparse(self.page.url).path
        if path and path != '/':
            return path.strip('/').replace('-', ' ').replace('_', ' ').title()
        
        return "文档页面"
    
    def filter_main_content(self, text):
        """从 body 文本中筛选主要内容"""
        if not text or len(text) < 100:
            return text or ""
        
        lines = text.split('\n')
        filtered = []
        
        # 跳过明显的导航和页脚
        skip_keywords = [
            '导航', '菜单', 'footer', 'copyright', '备案号', 
            '京ICP备', '关于我们', '联系我们', '友情链接'
        ]
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 跳过过短的行（可能是导航项）
            if len(line) < 20:
                skip = False
                for kw in skip_keywords:
                    if kw.lower() in line.lower():
                        skip = True
                        break
                if skip:
                    continue
            
            filtered.append(line)
        
        result = '\n'.join(filtered)
        return result if len(result) > 100 else text
    
    def html_to_markdown(self, html_content):
        """简单的 HTML 转 Markdown"""
        if not html_content:
            return ""
        
        # 移除脚本和样式
        html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # 移除导航和页脚
        html_content = re.sub(r'<nav[^>]*>.*?</nav>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<footer[^>]*>.*?</footer>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<aside[^>]*>.*?</aside>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # 转换标题
        html_content = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\n# \1\n', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<h4[^>]*>(.*?)</h4>', r'\n#### \1\n', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # 转换代码块
        html_content = re.sub(
            r'<pre><code[^>]*class="language-([^"]+)"[^>]*>(.*?)</code></pre>',
            r'\n```\1\n\2\n```\n',
            html_content,
            flags=re.DOTALL | re.IGNORECASE
        )
        html_content = re.sub(
            r'<pre><code[^>]*>(.*?)</code></pre>',
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
        
        # 转换段落
        html_content = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # 移除剩余的HTML标签
        html_content = re.sub(r'<[^>]+>', '', html_content)
        
        # 清理空白
        html_content = re.sub(r'\n\s*\n\s*\n', '\n\n', html_content)
        html_content = re.sub(r' +\n', '\n', html_content)
        
        return html_content.strip()
    
    def clean_content(self, content):
        """清理和格式化内容"""
        if not content:
            return ""
        
        # 移除过短的行（可能是噪音）
        lines = content.split('\n')
        cleaned = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if len(line) < 10 and not line.startswith('#') and not line.startswith('-') and not line.startswith('*'):
                continue
            cleaned.append(line)
        
        content = '\n'.join(cleaned)
        
        # 限制长度
        max_len = 100000
        if len(content) > max_len:
            content = content[:max_len] + "\n\n...(内容已截断)"
        
        return content
    
    def save_as_markdown(self, data, index):
        """保存为 Markdown 文件"""
        title = data['title']
        safe_title = re.sub(r'[\\/*?:"<>|]', '-', title)
        safe_title = safe_title.strip()[:80]
        
        # 生成文件名
        path = urlparse(data['url']).path
        path_slug = path.strip('/').replace('/', '_')
        filename = f"{index:03d}_{path_slug}.md" if path_slug else f"{index:03d}_index.md"
        
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
    
    def generate_index(self):
        """生成索引文件"""
        index_path = os.path.join(self.output_dir, "README.md")
        
        lines = [
            "# DrissionPage 文档全集\n",
            f"> 爬取日期：{time.strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"> 来源：{self.base_url}\n",
            f"> 目标路径：{', '.join(self.target_paths)}\n",
            f"> 页面数：{len(self.all_links)}\n",
            "\n## 📚 文档列表\n"
        ]
        
        for idx, url in enumerate(self.all_links, 1):
            parsed = urlparse(url)
            path = parsed.path if parsed.path else "/"
            name = path.strip('/').split('/')[-1] if path != '/' else "首页"
            name = name.replace('-', ' ').replace('_', ' ').title()
            lines.append(f"{idx}. [{name}]({url})")
        
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))


def main():
    """主函数"""
    crawler = DrissionPageCrawler(
        output_dir="drissionpage_docs",
        headless=False  # False = 有头模式，可以看到浏览器
    )
    crawler.run()


if __name__ == "__main__":
    main()