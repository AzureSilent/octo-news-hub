#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一RSS生成入口
调用所有网站的RSS生成脚本
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from threading import Lock

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 输出锁，防止多进程输出混乱
print_lock = Lock()

# RSS生成脚本列表
RSS_SCRIPTS = [
    {
        'name': '新智元',
        'script': 'get_ai_era_rss.py',
        'description': '智能+中国主平台，重点关注人工智能、机器人等前沿领域发展'
    },
    {
        'name': '机器之心',
        'script': 'get_jiqizhixin_rss.py',
        'description': '专业的人工智能媒体和产业服务平台'
    }
]


def run_script(script_name: str, base_dir: str = None) -> tuple:
    """
    运行指定的脚本（用于多进程）

    Args:
        script_name: 脚本文件名
        base_dir: 基础目录

    Returns:
        tuple: (script_name, success)
    """
    if base_dir is None:
        base_dir = os.path.dirname(SCRIPT_DIR)

    script_path = os.path.join(SCRIPT_DIR, script_name)

    if not os.path.exists(script_path):
        with print_lock:
            print(f"错误: 脚本不存在: {script_path}")
        return (script_name, False)

    with print_lock:
        print(f"\n{'='*60}")
        print(f"正在运行: {script_name}")
        print(f"{'='*60}")

    try:
        # 检查是否是异步脚本
        if 'jiqizhixin' in script_name.lower():
            # 使用Python直接运行，因为脚本内部已经处理了asyncio
            result = subprocess.run(
                [sys.executable, script_path],
                cwd=base_dir,
                check=True,
                capture_output=False,
                text=True
            )
        else:
            result = subprocess.run(
                [sys.executable, script_path],
                cwd=base_dir,
                check=True,
                capture_output=False,
                text=True
            )

        if result.returncode == 0:
            with print_lock:
                print(f"✅ {script_name} 运行成功")
            return (script_name, True)
        else:
            with print_lock:
                print(f"❌ {script_name} 运行失败，返回码: {result.returncode}")
            return (script_name, False)

    except subprocess.CalledProcessError as e:
        with print_lock:
            print(f"❌ {script_name} 运行出错: {e}")
        return (script_name, False)
    except Exception as e:
        with print_lock:
            print(f"❌ {script_name} 运行异常: {e}")
        return (script_name, False)


def generate_all_rss(sites: list = None, parallel: bool = False) -> dict:
    """
    生成所有RSS

    Args:
        sites: 要生成的网站列表，如果为None则生成所有
        parallel: 是否使用并行处理

    Returns:
        dict: 生成结果统计
    """
    if sites is None:
        sites = RSS_SCRIPTS

    results = {
        'total': len(sites),
        'success': 0,
        'failed': 0,
        'details': []
    }

    print(f"\n开始生成RSS，共 {len(sites)} 个网站")
    if parallel:
        print(f"使用并行处理模式")

    base_dir = os.path.dirname(SCRIPT_DIR)

    if parallel and len(sites) > 1:
        # 并行处理
        with ProcessPoolExecutor(max_workers=len(sites)) as executor:
            # 提交所有任务
            future_to_site = {
                executor.submit(run_script, site['script'], base_dir): site
                for site in sites
            }

            # 收集结果
            for future in as_completed(future_to_site):
                site = future_to_site[future]
                try:
                    script_name, success = future.result()
                    results['details'].append({
                        'name': site['name'],
                        'script': site['script'],
                        'success': success
                    })

                    if success:
                        results['success'] += 1
                    else:
                        results['failed'] += 1
                except Exception as e:
                    print(f"❌ {site['name']} 处理异常: {e}")
                    results['details'].append({
                        'name': site['name'],
                        'script': site['script'],
                        'success': False
                    })
                    results['failed'] += 1
    else:
        # 串行处理
        for site in sites:
            script_name, success = run_script(site['script'], base_dir)

            results['details'].append({
                'name': site['name'],
                'script': site['script'],
                'success': success
            })

            if success:
                results['success'] += 1
            else:
                results['failed'] += 1

    return results


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='统一RSS生成入口 - 生成所有网站的RSS',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
支持的网站:
  新智元    - 智能+中国主平台，重点关注人工智能、机器人等前沿领域发展
  机器之心  - 专业的人工智能媒体和产业服务平台

示例:
  # 生成所有网站的RSS（串行）
  python scripts/generate_all_rss.py

  # 生成所有网站的RSS（并行）
  python scripts/generate_all_rss.py --parallel

  # 只生成新智元的RSS
  python scripts/generate_all_rss.py --site 新智元

  # 生成新智元和机器之心的RSS（并行）
  python scripts/generate_all_rss.py --site 新智元 --site 机器之心 --parallel

  # 列出所有支持的网站
  python scripts/generate_all_rss.py --list
        '''
    )

    parser.add_argument(
        '--site',
        action='append',
        choices=[s['name'] for s in RSS_SCRIPTS],
        help='指定要生成的网站，可以多次使用。默认生成所有网站'
    )

    parser.add_argument(
        '--parallel',
        action='store_true',
        help='启用并行处理，同时运行多个网站的RSS生成（仅适用于多个网站）'
    )

    parser.add_argument(
        '--list',
        action='store_true',
        help='列出所有支持的网站'
    )

    args = parser.parse_args()

    # 列出所有支持的网站
    if args.list:
        print("\n支持的网站:")
        print("-" * 60)
        for site in RSS_SCRIPTS:
            print(f"  {site['name']:10s} - {site['description']}")
        print("-" * 60)
        return 0

    # 确定要生成的网站
    if args.site:
        # 用户指定了网站
        sites = [s for s in RSS_SCRIPTS if s['name'] in args.site]
        print(f"指定的网站: {', '.join(args.site)}")
    else:
        # 生成所有网站
        sites = RSS_SCRIPTS
        print("生成所有网站的RSS")

    # 如果只有一个网站，禁用并行模式
    if len(sites) == 1 and args.parallel:
        print("警告: 只有一个网站，自动禁用并行模式")
        args.parallel = False

    # 生成RSS
    results = generate_all_rss(sites, parallel=args.parallel)

    # 输出结果
    print(f"\n{'='*60}")
    print("RSS生成完成")
    print(f"{'='*60}")
    print(f"总计: {results['total']} 个网站")
    print(f"成功: {results['success']} 个")
    print(f"失败: {results['failed']} 个")

    if results['failed'] > 0:
        print(f"\n失败的网站:")
        for detail in results['details']:
            if not detail['success']:
                print(f"  - {detail['name']} ({detail['script']})")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())