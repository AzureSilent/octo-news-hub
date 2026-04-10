#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
机器之心RSS生成器 - 获取完整文章内容版本
使用playwright从页面HTML中提取完整文章内容
统一入口：如果文章列表不存在，会自动调用 get_jiqizhixin_articles.py 获取
"""

import os
import sys
import re
import json
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# 导入文章列表获取函数
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from get_jiqizhixin_articles import get_jiqizhixin_articles_robust


class CacheManager:
    """缓存管理器"""
    
    def __init__(self, cache_file: str, max_entries: int = 100):
        self.cache_file = cache_file
        self.max_entries = max_entries
        self.cache: Dict[str, dict] = {}
        self.hits = 0
        self.misses = 0
        self._load_cache()
    
    def _load_cache(self):
        """从文件加载缓存"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
                    for guid, entry in self.cache.items():
                        if 'cached_at' not in entry:
                            entry['cached_at'] = '2000-01-01T00:00:00'
            except (json.JSONDecodeError, IOError):
                self.cache = {}
    
    def _save_cache(self):
        """保存缓存到文件"""
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)
    
    def get(self, guid: str) -> Optional[dict]:
        """获取缓存条目"""
        result = self.cache.get(guid)
        if result is not None:
            self.hits += 1
        else:
            self.misses += 1
        return result
    
    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            'total_requests': total,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': hit_rate,
            'cache_entries': len(self.cache)
        }
    
    def add(self, guid: str, data: dict):
        """添加新条目到缓存"""
        data['cached_at'] = datetime.now().isoformat()
        self.cache[guid] = data
        self._trim_cache()
        self._save_cache()
    
    def _trim_cache(self):
        """清理超过限制的旧条目"""
        if self.max_entries > 0 and len(self.cache) > self.max_entries:
            sorted_items = sorted(
                self.cache.items(),
                key=lambda x: x[1].get('cached_at', '')
            )
            items_to_remove = len(self.cache) - self.max_entries
            for guid, _ in sorted_items[:items_to_remove]:
                del self.cache[guid]


class ContentProcessor:
    """内容处理器"""
    
    def __init__(self, config: dict):
        self.config = config
    
    def clean_html(self, html_content: str) -> str:
        """清理HTML内容"""
        if not html_content:
            return ""
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 移除script和style标签
        for tag in soup(['script', 'style', 'meta', 'link']):
            tag.decompose()
        
        # 展开所有div标签
        for div in soup.find_all('div'):
            div.unwrap()
        
        # 移除所有内联样式
        for tag in soup.find_all(True):
            tag.attrs = {k: v for k, v in tag.attrs.items() 
                       if k != 'style'}
        
        # 转换为HTML字符串
        result = str(soup)
        
        # 清理多余标签
        result = re.sub(r'<\s*/?\s*(h[1-6]|section|span)\s*>', '', result)
        result = re.sub(r'\s+', ' ', result)
        result = re.sub(r'>\s+<', '><', result)
        
        return result.strip()


class JiqizhixinRSSGenerator:
    """机器之心RSS生成器"""
    
    def __init__(self, articles_file: str, output_file: str, cache_file: str):
        self.articles_file = articles_file
        self.output_file = output_file
        self.cache_file = cache_file
        self.cache_manager = CacheManager(cache_file, max_entries=100)
        self.content_processor = ContentProcessor({})
        
        self.feed_config = {
            'title': '机器之心',
            'description': '专业的人工智能媒体和产业服务平台',
            'language': 'zh-CN',
            'ttl': 60
        }
    
    def _parse_date(self, date_str: str) -> str:
        """解析日期字符串为RSS格式"""
        # 东8区时区（UTC+8）
        TZ_CHINA = timezone(timedelta(hours=8))
        
        if not date_str:
            return datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')
        
        # 尝试解析 "04月09日" 格式
        match = re.match(r'(\d{2})月(\d{2})日', date_str)
        if match:
            month, day = match.groups()
            # 假设是当前年份
            year = datetime.now().year
            try:
                # 创建东8区的 datetime 对象
                dt = datetime(year, int(month), int(day), 0, 0, 0, tzinfo=TZ_CHINA)
                # 转换为 UTC
                dt_utc = dt.astimezone(timezone.utc)
                return dt_utc.strftime('%a, %d %b %Y %H:%M:%S +0000')
            except:
                pass
        
        return datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')
    
    async def fetch_article_content(self, article: dict) -> dict:
        """使用playwright从页面HTML中提取完整文章内容"""
        guid = article.get('uuid', article.get('link', ''))
        
        # 检查缓存
        cached = self.cache_manager.get(guid)
        if cached:
            print(f"  ✓ [缓存] {article['title'][:50]}...")
            return cached
        
        link = article.get('link', '')
        if not link:
            print(f"  ✗ [跳过] 无链接: {article['title'][:50]}...")
            return None
        
        try:
            print(f"  → [获取] {article['title'][:50]}...")
            
            async with async_playwright() as p:
                # 使用无头模式，但添加更多选项来模拟真实浏览器
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-web-security',
                    ]
                )
                
                # 创建context，设置user agent和视口
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='zh-CN'
                )
                
                page = await context.new_page()
                
                # 设置额外的headers
                await page.set_extra_http_headers({
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                })
                
                # 访问文章页面
                await page.goto(link, wait_until='networkidle', timeout=60000)
                
                # 等待页面完全加载
                await asyncio.sleep(8)
                
                # 滚动页面以触发懒加载
                for _ in range(6):
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    await asyncio.sleep(1)
                
                # 滚动回顶部
                await page.evaluate('window.scrollTo(0, 0)')
                await asyncio.sleep(4)
                
                # 尝试点击可能的内容加载按钮
                try:
                    # 查找可能的展开按钮
                    await page.evaluate('''() => {
                        const buttons = document.querySelectorAll('button, [role="button"], .expand');
                        for (let btn of buttons) {
                            if (btn.textContent.includes('展开') || btn.textContent.includes('加载') || btn.textContent.includes('更多')) {
                                btn.click();
                            }
                        }
                    }''')
                    await asyncio.sleep(3)
                except:
                    pass
                
                # 获取页面HTML
                html_content = await page.content()
                
                # 使用BeautifulSoup解析HTML
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # 查找文章内容 - 使用精确的选择器
                article_content = None
                
                # 方法1: 查找 detail__info-body 元素
                content_selectors = [
                    '.detail__info-body',
                    '.detail__info',
                    '.article-layout__body .detail__content',
                ]
                
                for selector in content_selectors:
                    elements = soup.select(selector)
                    if elements:
                        article_content = elements[0]
                        text_len = len(article_content.get_text(strip=True))
                        print(f"    找到选择器: {selector} ({text_len} 字符)")
                        break
                    else:
                        print(f"    未找到选择器: {selector}")
                
                # 如果没有找到，尝试查找所有可能的元素
                if not article_content:
                    print(f"    尝试查找其他元素...")
                    all_divs = soup.find_all('div')
                    for div in all_divs:
                        classes = div.get('class', [])
                        text = div.get_text(strip=True)
                        if len(text) > 1000 and len(text) < 5000:
                            print(f"    找到可能的内容容器: class={classes}, 长度={len(text)}")
                            # 使用第一个找到的
                            if not article_content:
                                article_content = div
                                break
                
                if article_content:
                    # 获取HTML内容
                    raw_html = str(article_content)
                    
                    # 清理HTML内容
                    cleaned_content = self.content_processor.clean_html(raw_html)
                    
                    # 检查清理后的内容长度
                    if len(cleaned_content) > 500:
                        processed_entry = {
                            'guid': guid,
                            'title': article.get('title', ''),
                            'link': link,
                            'pubDate': self._parse_date(article.get('time', '')),
                            'description': cleaned_content,
                            'categories': article.get('tags', [])
                        }
                        
                        self.cache_manager.add(guid, processed_entry)
                        print(f"    ✓ 成功 ({len(cleaned_content)} 字符)")
                        await browser.close()
                        return processed_entry
                
                # 如果无法获取完整内容，使用API摘要
                print(f"    ⚠ 使用API摘要")
                
                # 尝试从文章列表API获取摘要
                api_url = "https://www.jiqizhixin.com/api/article_library/articles.json?page=1&per=100"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Referer': 'https://www.jiqizhixin.com/articles/',
                    'Accept': 'application/json',
                }
                
                try:
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                            if response.status == 200:
                                text = await response.text()
                                data = json.loads(text)
                                
                                if 'articles' in data:
                                    for api_article in data['articles']:
                                        if api_article.get('id') == guid:
                                            content = api_article.get('content', '')
                                            if content:
                                                description = f"<p>{content}</p>"
                                                processed_entry = {
                                                    'guid': guid,
                                                    'title': article.get('title', ''),
                                                    'link': link,
                                                    'pubDate': self._parse_date(article.get('time', '')),
                                                    'description': description,
                                                    'categories': article.get('tags', [])
                                                }
                                                self.cache_manager.add(guid, processed_entry)
                                                await browser.close()
                                                return processed_entry
                except:
                    pass
                
                # 最后的fallback - 使用标题和标签
                tags_text = ', '.join(article.get('tags', []))
                if tags_text:
                    description = f"<p>{article.get('title', '')}</p><p>标签: {tags_text}</p>"
                else:
                    description = f"<p>{article.get('title', '')}</p>"
                
                processed_entry = {
                    'guid': guid,
                    'title': article.get('title', ''),
                    'link': link,
                    'pubDate': self._parse_date(article.get('time', '')),
                    'description': description,
                    'categories': article.get('tags', [])
                }
                
                self.cache_manager.add(guid, processed_entry)
                await browser.close()
                return processed_entry
                    
        except asyncio.TimeoutError:
            print(f"    ✗ 超时")
            return None
        except Exception as e:
            print(f"    ✗ 错误: {e}")
            return None
    
    def generate_rss(self, entries: List[dict]) -> str:
        """生成RSS XML"""
        feed_config = self.feed_config
        
        rss_items = []
        for entry in entries:
            pub_date = entry['pubDate'] or datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
            
            categories = ''.join([f'      <category>{cat}</category>\n' for cat in entry['categories']])
            
            item = f'''    <item>
      <title><![CDATA[{entry['title']}]]></title>
      <link>{xml_escape(entry['link'])}</link>
      <guid>{entry['guid']}</guid>
      <pubDate>{pub_date}</pubDate>
      <description><![CDATA[{entry['description']}]]></description>
{categories}    </item>'''
            rss_items.append(item)
        
        rss_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title><![CDATA[{feed_config['title']}]]></title>
    <description><![CDATA[{feed_config['description']}]]></description>
    <language>{feed_config['language']}</language>
    <lastBuildDate>{datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')}</lastBuildDate>
    <ttl>{feed_config['ttl']}</ttl>
{chr(10).join(rss_items)}
  </channel>
</rss>'''
        
        return rss_xml
    
    async def run(self):
        """运行RSS生成器"""
        print("=" * 60)
        print("机器之心RSS生成器")
        print("=" * 60)


        print("正在自动获取文章列表...")
        await get_jiqizhixin_articles_robust()
        print()

        # 加载文章列表
        print(f"正在加载文章列表: {self.articles_file}")
        with open(self.articles_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        articles = data.get('articles', [])
        print(f"找到 {len(articles)} 篇文章")
        
        # 处理文章
        print(f"\n开始处理文章 (无头模式，并发处理，模拟真实浏览器行为)...")
        
        processed_entries = []
        semaphore = asyncio.Semaphore(2)  # 无头模式可以使用并发
        
        async def process_with_semaphore(article):
            async with semaphore:
                result = await self.fetch_article_content(article)
                return result
        
        tasks = [process_with_semaphore(article) for article in articles]
        results = await asyncio.gather(*tasks)
        
        for result in results:
            if result:
                processed_entries.append(result)
        
        print(f"\n成功处理 {len(processed_entries)} 篇文章")
        
        # 生成RSS
        print("正在生成RSS...")
        rss_content = self.generate_rss(processed_entries)
        
        # 保存文件
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write(rss_content)
        
        print(f"✅ RSS文件已保存: {self.output_file}")
        
        # 输出缓存统计信息
        stats = self.cache_manager.get_stats()
        print(f"\n缓存统计信息:")
        print(f"  总请求次数: {stats['total_requests']}")
        print(f"  缓存命中: {stats['hits']}")
        print(f"  缓存未命中: {stats['misses']}")
        print(f"  缓存命中率: {stats['hit_rate']:.2f}%")
        print(f"  缓存条目数: {stats['cache_entries']}")
        
        return self.output_file


async def main():
    """主函数"""
    try:
        generator = JiqizhixinRSSGenerator(
            articles_file='data/cache/jiqizhixin_articles.json',
            output_file='output/rss/jiqizhixin.xml',
            cache_file='data/cache/jiqizhixin.json'
        )
        output_file = await generator.run()
        print(f"\n成功！请查看: {os.path.abspath(output_file)}")
        return 0
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
