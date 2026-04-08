#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSS Cleaner - 清理和优化RSS feed (简化版，无需额外依赖)
将混乱的RSS内容转换为清洁、结构良好的RSS格式
"""

import os
import sys
import re
import json
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

import requests
from bs4 import BeautifulSoup


class CacheManager:
    """缓存管理器 - 使用文章数量限制"""
    
    def __init__(self, cache_file: str, max_entries: int = 100):
        self.cache_file = cache_file
        self.max_entries = max_entries
        self.cache: Dict[str, dict] = {}
        self.hits = 0  # 缓存命中次数
        self.misses = 0  # 缓存未命中次数
        self._load_cache()
    
    def _load_cache(self):
        """从文件加载缓存"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
                    # 为没有 cached_at 的旧条目添加默认值（放在最早）
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
            # 按缓存时间排序，删除最旧的
            sorted_items = sorted(
                self.cache.items(),
                key=lambda x: x[1].get('cached_at', '')
            )
            items_to_remove = len(self.cache) - self.max_entries
            for guid, _ in sorted_items[:items_to_remove]:
                del self.cache[guid]


class ContentProcessor:
    """内容处理器 - 清理和整理HTML内容"""
    
    def __init__(self, config: dict):
        self.config = config
    
    def extract_real_link(self, html_content: str, original_link: str) -> str:
        """从HTML内容中提取真实的微信公众号文章链接"""
        import html
        patterns = [
            r'https?://mp\.weixin\.qq\.com/s/[a-zA-Z0-9_-]+',
            r'https?://mp\.weixin\.qq\.com/s\?[^\s"<>]+',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html_content)
            if match:
                # 提取链接并解码 HTML 实体
                url = match.group(0)
                # 解码 HTML 实体 (如 &amp; -> &)
                url = html.unescape(url)
                # 移除末尾可能的引号
                url = url.rstrip('"').rstrip("'")
                return url
        
        # 如果没有找到，返回原始链接
        return original_link
    
    def extract_original_image_url(self, proxy_url: str) -> str:
        """从代理URL中提取原始图片URL"""
        try:
            # 模式: http://img2.jintiankansha.me/get?src=原始URL
            parsed = urllib.parse.urlparse(proxy_url)
            query_params = urllib.parse.parse_qs(parsed.query)
            if 'src' in query_params:
                return query_params['src'][0]
        except Exception:
            pass
        return proxy_url
    
    def clean_html(self, html_content: str) -> str:
        """清理HTML内容"""
        if not html_content:
            return ""
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 移除script和style标签
        for tag in soup(['script', 'style', 'meta', 'link']):
            tag.decompose()
        
        # 清理section标签，保留内容
        for section in soup.find_all('section'):
            section.unwrap()
        
        # 清理div标签之间的空白文本（如"fff"）
        from bs4 import NavigableString
        for div in soup.find_all('div'):
            # 清理div标签之间的文本节点（只包含空白和简单文本的）
            for child in list(div.children):
                if isinstance(child, NavigableString):
                    # 这是一个文本节点，检查是否只包含简单的文本
                    text = str(child).strip()
                    # 如果文本很短且不包含标点符号，删除它
                    if len(text) < 20 and not any(c in text for c in '，。！？、；：,.!?'):
                        child.extract()
        
        # 展开所有div标签
        for div in soup.find_all('div'):
            div.unwrap()
        
        # 清理div标签之间的空白文本（如"fff"）
        for div in soup.find_all('div'):
            # 清理div标签之间的文本节点（只包含空白和简单文本的）
            for child in list(div.children):
                if hasattr(child, 'strip') and child.strip() and not child.name:
                    # 这是一个文本节点，检查是否只包含简单的文本
                    text = child.strip()
                    # 如果文本很短且不包含标点符号，删除它
                    if len(text) < 20 and not any(c in text for c in '，。！？、；：,.!?'):
                        child.extract()
        
        # 展开所有div标签
        for div in soup.find_all('div'):
            div.unwrap()
        
        # 处理图片
        if self.config.get('extract_original_images', True):
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if 'jintiankansha.me' in src:
                    original_url = self.extract_original_image_url(src)
                    img['src'] = original_url
                
                # 移除不必要的属性
                img.attrs = {k: v for k, v in img.attrs.items() 
                           if k in ['src', 'alt', 'title', 'width', 'height']}
        
        # 清理空段落
        if self.config.get('remove_empty_paragraphs', True):
            for p in soup.find_all('p'):
                if not p.get_text(strip=True) and not p.find('img'):
                    p.decompose()
        
        # 移除所有内联样式
        if self.config.get('remove_inline_styles', True):
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
    
    def organize_content(self, html_content: str) -> dict:
        """组织内容，提取图片和文本"""
        if not html_content:
            return {'text': '', 'images': []}
        
        soup = BeautifulSoup(html_content, 'html.parser')
        images = []
        text_parts = []
        
        # 提取图片
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if src:
                images.append({
                    'url': src,
                    'alt': img.get('alt', ''),
                    'width': img.get('width', ''),
                    'height': img.get('height', '')
                })
        
        # 提取文本
        for element in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            text = element.get_text(strip=True)
            if text:
                text_parts.append(text)
        
        return {
            'text': '\n\n'.join(text_parts),
            'images': images,
            'html': str(soup)
        }


class RSSCleaner:
    """RSS清理器主类"""
    
    def __init__(self, config_file: str = 'config.yaml'):
        self.config = self._load_config(config_file)
        self.cache_manager = CacheManager(
            self.config['output']['cache_file'],
            self.config['cache']['max_entries']
        )
        self.content_processor = ContentProcessor(self.config['processing'])
    
    def _load_config(self, config_file: str) -> dict:
        """加载配置文件"""
        config = {
            'source_url': 'https://plink.anyfeeder.com/weixin/AI_era',
            'output': {
                'rss_file': 'output/rss/ai_era.xml',
                'cache_file': 'data/cache/ai_era.json'
            },
            'cache': {
                'max_entries': 100
            },
            'processing': {
                'remove_inline_styles': True,
                'remove_empty_paragraphs': True,
                'max_image_width': 800,
                'extract_original_images': True
            },
            'feed': {
                'title': '新智元',
                'description': '智能+中国主平台，致力于推动中国从互联网+迈向智能+新纪元。重点关注人工智能、机器人等前沿领域发展。',
                'language': 'zh-CN',
                'ttl': 60
            }
        }
        return config
    
    def fetch_rss(self) -> ET.Element:
        """获取原始RSS并解析"""
        url = self.config['source_url']
        print(f"正在获取RSS: {url}")
        response = requests.get(url, timeout=30)
        response.encoding = 'utf-8'
        
        # 解析XML
        root = ET.fromstring(response.text)
        
        # 处理命名空间
        self.ns = {'content': 'http://purl.org/rss/1.0/modules/content/'}
        
        return root
    
    def process_entry(self, item_element: ET.Element) -> dict:
        """处理单个RSS条目"""
        # 提取guid
        guid_elem = item_element.find('guid')
        guid = guid_elem.text if guid_elem is not None else ''
        
        # 检查缓存
        cached = self.cache_manager.get(guid)
        if cached:
            return cached
        
        # 提取标题
        title_elem = item_element.find('title')
        title = title_elem.text if title_elem is not None else ''
        
        # 提取链接
        link_elem = item_element.find('link')
        original_link = link_elem.text if link_elem is not None else ''
        
        # 提取发布日期
        pub_date_elem = item_element.find('pubDate')
        pub_date = pub_date_elem.text if pub_date_elem is not None else ''
        
        # 提取内容
        content_elem = item_element.find('content:encoded', self.ns)
        if content_elem is not None:
            html_content = content_elem.text or ''
        else:
            desc_elem = item_element.find('description')
            html_content = desc_elem.text if desc_elem is not None else ''
        
        # 清理HTML
        cleaned_html = self.content_processor.clean_html(html_content)
        
        # 组织内容
        organized = self.content_processor.organize_content(cleaned_html)
        
        # 提取真实链接（从原始HTML内容中提取）
        real_link = self.content_processor.extract_real_link(html_content, original_link)
        
        # 提取分类
        categories = []
        for cat_elem in item_element.findall('category'):
            if cat_elem.text:
                categories.append(cat_elem.text)
        
        # 构建处理后的条目（只缓存必要字段）
        processed_entry = {
            'guid': guid,
            'title': title,
            'link': real_link,
            'pubDate': pub_date,
            'description': cleaned_html,
            'categories': categories
        }
        
        # 保存到缓存
        self.cache_manager.add(guid, processed_entry)
        
        return processed_entry
    
    def _create_description(self, organized: dict) -> str:
        """创建RSS描述，直接使用清理后的HTML内容"""
        return organized['html']
    
    def generate_rss(self, entries: List[dict]) -> str:
        """生成新的RSS XML"""
        feed_config = self.config['feed']
        
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
    
    def run(self):
        """运行清理流程"""
        root = self.fetch_rss()
        
        # 找到channel和items
        channel = root.find('.//channel')
        items = channel.findall('.//item')
        
        print(f"找到 {len(items)} 条文章")
        
        processed_entries = []
        for i, item in enumerate(items, 1):
            title_elem = item.find('title')
            title = title_elem.text if title_elem is not None else ''
            print(f"处理第 {i}/{len(items)} 条: {title[:50]}...")
            
            processed = self.process_entry(item)
            processed_entries.append(processed)
        
        # 生成RSS
        rss_content = self.generate_rss(processed_entries)
        
        # 保存文件
        output_file = self.config['output']['rss_file']
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(rss_content)
        
        print(f"\n完成！生成的新RSS文件: {output_file}")
        
        # 输出缓存统计信息
        stats = self.cache_manager.get_stats()
        print(f"\n缓存统计信息:")
        print(f"  总请求次数: {stats['total_requests']}")
        print(f"  缓存命中: {stats['hits']}")
        print(f"  缓存未命中: {stats['misses']}")
        print(f"  缓存命中率: {stats['hit_rate']:.2f}%")
        print(f"  缓存条目数: {stats['cache_entries']}")
        
        return output_file


def main():
    """主函数"""
    try:
        cleaner = RSSCleaner()
        output_file = cleaner.run()
        print(f"\n成功！请查看: {os.path.abspath(output_file)}")
        return 0
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
