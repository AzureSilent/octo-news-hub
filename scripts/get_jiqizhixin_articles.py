"""
获取机器之心网站的文章列表和链接（增强版）
使用多策略选择器和基于内容特征的识别方式，提高稳定性
"""

import asyncio
import json
import re
from playwright.async_api import async_playwright
from datetime import datetime
from typing import List, Dict, Any


class ArticleExtractor:
    """文章列表提取器 - 使用多策略提高稳定性"""
    
    def __init__(self):
        # 多种可能的选择器策略
        self.selector_strategies = {
            'primary': [
                '.home__center-left__list > div',
                '.home__center-left__list .home__article-item',
                '.home__center-left__list article',
                '[class*="article-item"]',
                '[class*="article-card"]',
            ],
            'fallback': [
                # 更精确的fallback选择器，避免选中子元素
                '.home__center-left__list .home__center-card',
                '.home__center-left__list .home-card',
                '.home__center-left__list div[class*="card"]',
                # 查找包含文章标题和时间的大容器
                'div[class*="center-left"] > div[class*="card"]',
                'div[class*="article-item"]',
                # 备用方案
                '.home__center-left article',
                '[class*="center-left"][class*="list"] > div',
            ],
            'generic': [
                # 改进的generic选择器，寻找真正的文章元素
                'div.home__article-item',
                'div[class*="article-item"][class*="home"]',
                'div.home__center-card',
                # 查找包含标题和图片的div
                'div:has(.home__article-item__title):has(img)',
                # 更精确的选择器
                'div[class*="card"][class*="center"]',
                'div[class*="card"][class*="home"]',
                # 最后的通用方案
                'div[class*="article"]',
                'article',
            ]
        }
        
        # 标题元素选择器
        self.title_selectors = [
            '.home__article-item__title',
            '[class*="title"]',
            'h2', 'h3', 'h4',
            '[class*="heading"]',
        ]
        
        # 时间元素选择器
        self.time_selectors = [
            '.home__article-item__time',
            '[class*="time"]',
            '[class*="date"]',
            'time',
            '[class*="publish"]',
        ]
        
        # 图片元素选择器
        self.image_selectors = [
            'img',
            '[class*="image"]',
            '[class*="thumbnail"]',
        ]
        
        # 标签元素选择器
        self.tag_selectors = [
            '.home__article-item__tag-item',
            '[class*="tag"]',
            '[class*="category"]',
            '[class*="label"]',
        ]
    
    async def find_articles_container(self, page) -> str:
        """尝试多种策略找到文章容器"""
        print("正在查找文章容器...")
        
        # 尝试所有策略
        for strategy_name, selectors in self.selector_strategies.items():
            print(f"  尝试 {strategy_name} 策略...")
            for selector in selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    if len(elements) >= 3:  # 至少有3个元素才认为是文章列表
                        print(f"  ✓ 找到 {len(elements)} 个元素，使用选择器: {selector}")
                        return selector
                except Exception:
                    continue
        
        # 如果都失败，尝试查找包含文章标题的容器
        print("  所有策略都失败，尝试基于内容特征查找...")
        try:
            js_result = await page.evaluate('''() => {
                // 寻找包含多个文章卡片的容器
                const allDivs = document.querySelectorAll('div');
                const containerCandidates = [];
                
                for (let div of allDivs) {
                    const children = div.children;
                    if (children.length >= 3) {  // 至少有3个子元素
                        let articleCount = 0;
                        
                        // 检查每个子元素是否包含文章特征
                        for (let child of children) {
                            let hasTitle = false;
                            let hasImage = false;
                            let hasTime = false;
                            
                            // 检查是否有标题元素
                            const titleElements = child.querySelectorAll('.home__article-item__title, [class*="title"], h2, h3');
                            for (let titleEl of titleElements) {
                                if (titleEl.innerText && titleEl.innerText.length > 10 && titleEl.innerText.length < 200) {
                                    hasTitle = true;
                                    break;
                                }
                            }
                            
                            // 检查是否有图片
                            if (child.querySelector('img')) {
                                hasImage = true;
                            }
                            
                            // 检查是否有时间
                            const timeElements = child.querySelectorAll('.home__article-item__time, [class*="time"], [class*="date"], time');
                            for (let timeEl of timeElements) {
                                if (timeEl.innerText && timeEl.innerText.trim()) {
                                    hasTime = true;
                                    break;
                                }
                            }
                            
                            // 如果同时有标题和图片，认为是文章卡片
                            if (hasTitle && hasImage) {
                                articleCount++;
                            }
                        }
                        
                        // 如果容器包含3个或更多文章卡片，认为是文章列表容器
                        if (articleCount >= 3) {
                            containerCandidates.push({
                                element: div,
                                articleCount: articleCount,
                                className: div.className
                            });
                        }
                    }
                }
                
                // 返回文章数量最多的容器
                if (containerCandidates.length > 0) {
                    // 按文章数量排序，取最多的
                    containerCandidates.sort((a, b) => b.articleCount - a.articleCount);
                    const best = containerCandidates[0];
                    
                    // 生成选择器
                    let selector = 'div';
                    if (best.className) {
                        const classes = best.className.split(' ').filter(c => c);
                        if (classes.length > 0) {
                            selector = `.${classes[0]}`;
                        }
                    }
                    
                    return {
                        selector: selector,
                        count: best.articleCount,
                        method: 'content_analysis'
                    };
                }
                
                return null;
            }''')
            
            if js_result:
                print(f"  ✓ 基于内容特征找到容器: {js_result['selector']} ({js_result['count']} 篇文章)")
                return js_result['selector']
        except Exception as e:
            print(f"  ✗ 内容特征查找失败: {e}")
        
        return None
    
    async def extract_field(self, element, selectors: List[str], attribute: str = None) -> Any:
        """从元素中提取字段"""
        for selector in selectors:
            try:
                field_element = await element.query_selector(selector)
                if field_element:
                    if attribute:
                        result = await field_element.get_attribute(attribute)
                    else:
                        result = await field_element.inner_text()
                    
                    if result:
                        return result.strip() if isinstance(result, str) else result
            except Exception:
                continue
        
        return None
    
    async def extract_uuid_from_image(self, image_url: str) -> str:
        """从图片 URL 中提取 UUID"""
        if not image_url:
            return None
        
        # 尝试多种 UUID 模式
        uuid_patterns = [
            r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',  # 标准 UUID
            r'([0-9a-f]{32})',  # 32位十六进制
            r'uploads/article/([^/?]+)',  # 文章路径模式
        ]
        
        for pattern in uuid_patterns:
            match = re.search(pattern, image_url)
            if match:
                return match.group(1)
        
        return None
    
    async def extract_article_info(self, article_element, index: int) -> Dict[str, Any]:
        """提取单个文章的信息"""
        article_info = {
            'index': index + 1,
            'title': '',
            'time': '',
            'image_url': '',
            'uuid': '',
            'link': '',
            'tags': []
        }
        
        try:
            # 提取标题
            title = await self.extract_field(article_element, self.title_selectors)
            if title:
                article_info['title'] = title
            else:
                # 尝试直接从元素文本中提取标题（第一个较长的文本）
                text = await article_element.inner_text()
                if text:
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    if lines:
                        # 选择长度适中的第一行作为标题
                        for line in lines:
                            if 10 < len(line) < 200:
                                article_info['title'] = line
                                break
            
            # 提取时间
            time_text = await self.extract_field(article_element, self.time_selectors)
            if time_text:
                article_info['time'] = time_text
            
            # 提取图片
            image_url = await self.extract_field(article_element, self.image_selectors, 'src')
            if image_url:
                article_info['image_url'] = image_url
                
                # 提取 UUID
                uuid = await self.extract_uuid_from_image(image_url)
                if uuid:
                    article_info['uuid'] = uuid
                    article_info['link'] = f'https://www.jiqizhixin.com/articles/{uuid}'
            
            # 提取标签
            tag_elements = await article_element.query_selector_all(self.tag_selectors[0])
            tags = []
            for tag_elem in tag_elements:
                tag_text = await tag_elem.inner_text()
                if tag_text and tag_text.strip():
                    tags.append(tag_text.strip())
            
            if not tags:
                # 尝试其他标签选择器
                for selector in self.tag_selectors[1:]:
                    tag_elements = await article_element.query_selector_all(selector)
                    for tag_elem in tag_elements:
                        tag_text = await tag_elem.inner_text()
                        if tag_text and tag_text.strip():
                            tags.append(tag_text.strip())
            
            article_info['tags'] = tags
            
            # 尝试查找直接链接
            link_element = await article_element.query_selector('a')
            if link_element:
                href = await link_element.get_attribute('href')
                if href and not article_info['link']:
                    article_info['link'] = href if href.startswith('http') else f'https://www.jiqizhixin.com{href}'
            
        except Exception as e:
            print(f"    提取文章 {index + 1} 信息时出错: {e}")
        
        return article_info
    
    def validate_article(self, article_info: Dict[str, Any]) -> bool:
        """验证文章信息是否有效"""
        # 必须有标题
        if not article_info.get('title'):
            return False
        
        # 标题长度应该合理
        title = article_info['title']
        if len(title) < 5 or len(title) > 300:
            return False
        
        # 至少要有链接（无论是 UUID 构造的还是直接的）
        if not article_info.get('link'):
            return False
        
        return True


async def get_jiqizhixin_articles_robust():
    """
    获取机器之心网站的文章列表和链接（增强版）
    使用多策略和基于内容特征的识别方式
    """
    extractor = ArticleExtractor()
    articles = []
    
    async with async_playwright() as p:
        # 使用无头模式，添加优化参数避免被检测
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
        
        try:
            print("正在访问机器之心网站...")
            await page.goto('https://www.jiqizhixin.com/', wait_until='networkidle', timeout=60000)
            await asyncio.sleep(8)  # 增加等待时间确保页面完全加载
            
            print("开始查找文章容器...")
            
            # 查找文章容器
            container_selector = await extractor.find_articles_container(page)
            
            if not container_selector:
                print("❌ 无法找到文章容器，尝试使用备用方法...")
                # 最后的备用方法：查找所有可能的文章元素
                container_selector = 'div'
                print("  使用备用方法: 'div'")
            
            # 获取文章元素
            article_elements = await page.query_selector_all(container_selector)
            print(f"找到 {len(article_elements)} 个候选元素")
            
            # 如果只找到1个元素，但它是一个容器，尝试获取它的子元素
            if len(article_elements) == 1:
                print("  只找到1个元素，检查是否为容器...")
                try:
                    # 检查第一个元素是否包含多个子元素
                    first_element = article_elements[0]
                    children_count = await first_element.evaluate('el => el.children.length')
                    print(f"  第一个元素包含 {children_count} 个子元素")
                    
                    if children_count >= 3:
                        print("  似乎是一个容器，获取其直接子元素...")
                        # 只获取直接子元素，使用CSS选择器
                        article_elements = await page.query_selector_all(f'{container_selector} > div')
                        print(f"  获取到 {len(article_elements)} 个直接子元素")
                except Exception as e:
                    print(f"  检查子元素时出错: {e}")
            
            # 提取文章信息
            print("开始提取文章信息...")
            for idx, element in enumerate(article_elements):
                try:
                    article_info = await extractor.extract_article_info(element, idx)
                    
                    # 验证文章信息
                    if extractor.validate_article(article_info):
                        articles.append(article_info)
                        print(f"  [{len(articles)}] {article_info['title'][:50]}...")
                except Exception as e:
                    print(f"  处理元素 {idx + 1} 时出错: {e}")
                    continue
            
            # 去重（基于标题）
            seen_titles = set()
            unique_articles = []
            for article in articles:
                if article['title'] not in seen_titles:
                    seen_titles.add(article['title'])
                    unique_articles.append(article)
            
            articles = unique_articles
            
            print(f"\n成功提取 {len(articles)} 篇有效文章")
            
            # 打印文章信息
            for article_info in articles:
                print(f"\n[{article_info['index']}] {article_info['title']}")
                print(f"    链接: {article_info['link']}")
                print(f"    时间: {article_info['time']}")
                if article_info['tags']:
                    print(f"    标签: {', '.join(article_info['tags'])}")
            
            # 保存结果
            output_file = 'data/cache/jiqizhixin_articles.json'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'fetch_time': datetime.now().isoformat(),
                    'total_articles': len(articles),
                    'articles': articles,
                    'method': 'robust_multi_strategy'
                }, f, ensure_ascii=False, indent=2)
            
            print(f"\n✅ 结果已保存到: {output_file}")
            
        except Exception as e:
            print(f"❌ 发生错误: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path='error_screenshot_robust.png')
        
        finally:
            await browser.close()
    
    return articles


if __name__ == '__main__':
    print("=" * 60)
    print("获取机器之心文章列表和链接")
    print("=" * 60)
    asyncio.run(get_jiqizhixin_articles_robust())
