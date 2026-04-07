#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日文章列表生成器
根据日期生成当天的文章列表页面
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict

# 配置
CACHE_FILE = 'data/cache.json'
OUTPUT_DIR = 'output/pages/daily/ai_era'
BASE_URL = 'https://plink.anyfeeder.com/weixin/AI_era'
RETENTION_DAYS = 60  # 页面保留天数，超过此天数的页面将被删除

# 东8区时区（UTC+8）
TZ_CHINA = timezone(timedelta(hours=8))


class DailyReportGenerator:
    """每日报告生成器"""
    
    def __init__(self, cache_file: str, output_dir: str, retention_days: int = RETENTION_DAYS):
        self.cache_file = cache_file
        self.output_dir = output_dir
        self.retention_days = retention_days
        
    def load_cache(self) -> Dict:
        """加载缓存文件"""
        if not os.path.exists(self.cache_file):
            return {}
        
        with open(self.cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_available_dates(self, cache: Dict) -> set:
        """获取缓存中所有可用的日期"""
        dates = set()
        for guid, entry in cache.items():
            pub_date_str = entry.get('pubDate', '')
            if not pub_date_str:
                continue
            
            try:
                pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %z')
                pub_date_local = pub_date.astimezone(TZ_CHINA)
                dates.add(pub_date_local.date())
            except (ValueError, KeyError):
                continue
        
        return dates
    
    def filter_by_date(self, cache: Dict, target_date: str) -> List[Dict]:
        """根据日期筛选文章"""
        target_date_obj = datetime.strptime(target_date, '%Y-%m-%d').date()
        articles = []
        
        for guid, entry in cache.items():
            pub_date_str = entry.get('pubDate', '')
            if not pub_date_str:
                continue
            
            # 解析日期，格式如 "Thu, 02 Apr 2026 19:00:00 +0800"
            try:
                pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %z')
                # 转换为东8区时间
                pub_date_local = pub_date.astimezone(TZ_CHINA)
                
                # 比较日期
                if pub_date_local.date() == target_date_obj:
                    articles.append({
                        'guid': entry['guid'],
                        'title': entry['title'],
                        'link': entry['link'],
                        'pubDate': pub_date_str,
                        'description': entry.get('description', ''),
                        'categories': entry.get('categories', []),
                        'local_datetime': pub_date_local
                    })
            except (ValueError, KeyError) as e:
                continue
        
        # 按时间逆序排列
        articles.sort(key=lambda x: x['local_datetime'], reverse=True)
        
        return articles
    
    def generate_html(self, articles: List[Dict], target_date: str, available_dates: set) -> str:
        """生成HTML页面"""
        # 转换日期为中文格式
        try:
            date_obj = datetime.strptime(target_date, '%Y-%m-%d')
            date_cn = date_obj.strftime('%Y年%m月%d日')
            date_short = date_obj.strftime('%m-%d')
        except:
            date_cn = target_date
            date_short = target_date[5:10]
        
        # 计算前一天和后一天
        target_date_obj = datetime.strptime(target_date, '%Y-%m-%d').date()
        prev_date = (target_date_obj - timedelta(days=1)).strftime('%Y-%m-%d')
        next_date = (target_date_obj + timedelta(days=1)).strftime('%Y-%m-%d')
        
        # 检查前一天和后一天是否有文章
        prev_date_obj = datetime.strptime(prev_date, '%Y-%m-%d').date()
        next_date_obj = datetime.strptime(next_date, '%Y-%m-%d').date()
        
        # 生成导航HTML（始终显示）
        nav_html = '<div class="nav-links">\n'
        nav_html += f'        <a href="{prev_date}.html" class="nav-link prev-link">← {prev_date}</a>\n'
        nav_html += f'        <a href="{next_date}.html" class="nav-link next-link">{next_date} →</a>\n'
        nav_html += '      </div>\n'
        
        # 生成文章列表HTML
        articles_html = ""
        for i, article in enumerate(articles):
            # 获取完整的HTML内容
            full_content = article['description']
            
            # 格式化时间 MM-DD HH:mm
            try:
                time_str = article['local_datetime'].strftime('%m-%d %H:%M')
            except:
                time_str = article['pubDate']
            
            # 文章序号
            num = len(articles) - i
            
            articles_html += f'''\n    <article class="article" id="article-{i}">
      <div class="article-header" onclick="toggleArticle({i})">
        <h2 class="article-title">{num}. {article['title']}</h2>
        <div class="article-meta">
          <span class="article-time">{time_str}</span>
          <span class="article-link">
            <a href="{article['link']}" target="_blank" onclick="event.stopPropagation()">原文链接</a>
          </span>
        </div>
      </div>
      <div class="article-content" id="content-{i}" style="display: none;">
        {full_content}
      </div>
    </article>'''
        
        # 生成完整HTML
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>新智元 - {date_cn} 文章列表</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }}
        
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 1.8em;
            margin-bottom: 5px;
            font-weight: 600;
        }}
        
        .header p {{
            font-size: 0.95em;
            opacity: 0.9;
        }}
        
        .nav-links {{
            padding: 15px 30px;
            background: #f9fafb;
            border-bottom: 1px solid #e5e7eb;
            display: flex;
            justify-content: space-between;
        }}
        
        .nav-link {{
            padding: 8px 16px;
            background: white;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            text-decoration: none;
            color: #374151;
            transition: all 0.2s ease;
        }}
        
        .nav-link:hover {{
            background: #f3f4f6;
            border-color: #9ca3af;
        }}
        
        .prev-link {{
            margin-right: auto;
        }}
        
        .next-link {{
            margin-left: auto;
        }}
        
        .content {{
            padding: 30px;
        }}
        
        .article {{
            border-bottom: 1px solid #e5e7eb;
            margin-bottom: 20px;
            padding-bottom: 20px;
        }}
        
        .article:last-child {{
            border-bottom: none;
            margin-bottom: 0;
        }}
        
        .article-header {{
            cursor: pointer;
            padding: 10px 0;
            transition: background 0.2s ease;
        }}
        
        .article-header:hover {{
            background: #f9fafb;
            margin: 0 -10px;
            padding: 10px;
            border-radius: 6px;
        }}
        
        .article-title {{
            font-size: 1.2em;
            margin-bottom: 8px;
            font-weight: 600;
            color: #1f2937;
        }}
        
        .article-meta {{
            display: flex;
            gap: 15px;
            font-size: 0.9em;
            color: #6b7280;
            align-items: center;
        }}
        
        .article-time {{
            background: #e5e7eb;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: 500;
        }}
        
        .article-link a {{
            color: #667eea;
            text-decoration: none;
        }}
        
        .article-link a:hover {{
            text-decoration: underline;
        }}
        
        .article-content {{
            margin-top: 15px;
            padding: 15px;
            background: #f9fafb;
            border-radius: 6px;
            border-left: 3px solid #667eea;
        }}
        
        .article-summary {{
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #e5e7eb;
        }}
        
        .article-full {{
            color: #374151;
        }}
        
        .article-full img {{
            max-width: 100%;
            height: auto;
            border-radius: 4px;
            margin: 10px 0;
        }}
        
        .article-full p {{
            margin-bottom: 10px;
        }}
        
        .no-articles {{
            text-align: center;
            padding: 60px 20px;
            color: #6b7280;
        }}
        
        .footer {{
            background: #f9fafb;
            padding: 20px;
            text-align: center;
            color: #6b7280;
            border-top: 1px solid #e5e7eb;
            font-size: 0.9em;
        }}
        
        .footer a {{
            color: #667eea;
            text-decoration: none;
        }}
        
        .footer a:hover {{
            text-decoration: underline;
        }}
        
        @media (max-width: 768px) {{
            .content {{
                padding: 20px;
            }}
            
            .header {{
                padding: 20px;
            }}
            
            .article-title {{
                font-size: 1.1em;
            }}
        }}
    </style>
    <script>
        function toggleArticle(id) {{
            var content = document.getElementById('content-' + id);
            if (content.style.display === 'none') {{
                content.style.display = 'block';
            }} else {{
                content.style.display = 'none';
            }}
        }}
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>新智元 - {date_cn} 文章列表</h1>
            <p>AI前沿技术动态</p>
        </div>
        
        {nav_html}
        
        <div class="content">
            {articles_html if articles else '<div class="no-articles"><p>该日期没有文章</p></div>'}
        </div>
        
        <div class="footer">
            <p>生成时间: {datetime.now(TZ_CHINA).strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
</body>
</html>'''
        
        return html
    
    def generate(self, target_date: str = None) -> str:
        """生成每日报告"""
        # 获取目标日期
        if target_date is None:
            target_date = datetime.now(TZ_CHINA).strftime('%Y-%m-%d')
        
        # 验证日期格式
        try:
            datetime.strptime(target_date, '%Y-%m-%d')
        except ValueError:
            raise ValueError(f"日期格式错误，应为 YYYY-MM-DD，当前值: {target_date}")
        
        # 加载缓存
        cache = self.load_cache()
        if not cache:
            print(f"警告: 缓存文件不存在或为空: {self.cache_file}")
            return None
        
        # 获取可用日期
        available_dates = self.get_available_dates(cache)
        
        # 筛选文章
        articles = self.filter_by_date(cache, target_date)
        
        print(f"找到 {len(articles)} 篇文章")
        
        # 生成HTML
        html = self.generate_html(articles, target_date, available_dates)
        
        # 保存文件
        os.makedirs(self.output_dir, exist_ok=True)
        output_file = os.path.join(self.output_dir, f'{target_date}.html')
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"已生成: {output_file}")
        print(f"文件路径: {os.path.abspath(output_file)}")
        
        return output_file
    
    def cleanup_old_pages(self) -> List[str]:
        """删除超过保留天数的页面"""
        if not os.path.exists(self.output_dir):
            return []
        
        # 计算截止日期
        cutoff_date = datetime.now(TZ_CHINA).date() - timedelta(days=self.retention_days)
        
        deleted_files = []
        
        # 遍历输出目录中的所有HTML文件
        for filename in os.listdir(self.output_dir):
            if not filename.endswith('.html'):
                continue
            
            # 提取日期（文件名格式为 YYYY-MM-DD.html）
            date_str = filename[:-5]  # 移除 .html 扩展名
            
            try:
                file_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                
                # 如果文件日期早于截止日期，删除文件
                if file_date < cutoff_date:
                    file_path = os.path.join(self.output_dir, filename)
                    os.remove(file_path)
                    deleted_files.append(filename)
                    print(f"已删除旧页面: {filename} ({(cutoff_date - file_date).days} 天前)")
            except ValueError:
                # 如果文件名不是有效的日期格式，跳过
                continue
        
        if deleted_files:
            print(f"共删除 {len(deleted_files)} 个旧页面")
        else:
            print("没有需要删除的旧页面")
        
        return deleted_files


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='生成每日文章列表',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  # 使用当前日期（东8区）
  python scripts/generate_daily_report.py
  
  # 指定日期
  python scripts/generate_daily_report.py --date 2026-04-03
  
  # 使用昨天的日期
  python scripts/generate_daily_report.py --date yesterday
        '''
    )
    
    parser.add_argument(
        '--date',
        type=str,
        default=None,
        help='目标日期，格式为 YYYY-MM-DD，或使用 "yesterday" 表示昨天。默认为当前日期（东8区）'
    )
    
    parser.add_argument(
        '--cache',
        type=str,
        default=CACHE_FILE,
        help=f'缓存文件路径，默认为 {CACHE_FILE}'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default=OUTPUT_DIR,
        help=f'输出目录，默认为 {OUTPUT_DIR}'
    )
    
    parser.add_argument(
        '--retention-days',
        type=int,
        default=RETENTION_DAYS,
        help=f'页面保留天数，超过此天数的页面将被删除，默认为 {RETENTION_DAYS} 天'
    )
    
    args = parser.parse_args()
    
    # 处理日期参数
    target_date = args.date
    if target_date == 'yesterday':
        yesterday = datetime.now(TZ_CHINA) - timedelta(days=1)
        target_date = yesterday.strftime('%Y-%m-%d')
    elif target_date and target_date.lower() != 'today':
        # 验证日期格式
        try:
            datetime.strptime(target_date, '%Y-%m-%d')
        except ValueError:
            print(f"错误: 日期格式无效，应为 YYYY-MM-DD，当前值: {target_date}")
            return 1
    
    # 生成报告
    try:
        generator = DailyReportGenerator(args.cache, args.output, args.retention_days)
        output_file = generator.generate(target_date)
        
        if output_file:
            print(f"\n成功！")
            
            # 清理旧页面
            print("\n开始清理旧页面...")
            generator.cleanup_old_pages()
            
            return 0
        else:
            print(f"\n失败：无法生成报告")
            return 1
            
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
