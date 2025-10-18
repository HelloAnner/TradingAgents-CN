#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证 scheduler 最近一次运行日志是否符合预期。

默认读取 logs/tradingagents.log 的末尾若干行，检查关键日志片段：
- "共发现"、"任务 i/N 开始"、"保存PDF"、"已发送邮件"、"任务 i/N 完成"、"RUN_ONCE 启用"

使用：
  python scripts/automation/verify_last_run.py --log logs/tradingagents.log --tail 4000
返回码：0=通过，非0=未通过
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


def tail_lines(path: Path, max_lines: int) -> list[str]:
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    return lines[-max_lines:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--log', default='logs/tradingagents.log', help='日志文件路径')
    ap.add_argument('--tail', type=int, default=4000, help='检查末尾行数')
    args = ap.parse_args()

    path = Path(args.log)
    if not path.exists():
        print(f"❌ 日志文件不存在: {path}")
        return 2

    lines = tail_lines(path, args.tail)
    text = ''.join(lines)

    checks = {
        '发现任务计数': '共发现',
        '任务开始标记': '===== 任务',
        'PDF保存': '保存PDF',
        '邮件发送': '已发送邮件',
        '任务完成标记': '完成 =====',
        '单次运行退出': 'RUN_ONCE 启用'  # 单次运行时需要；守护模式可忽略
    }

    failed = []
    for name, pattern in checks.items():
        if pattern not in text:
            failed.append(name)

    if failed:
        print("❌ 日志验证未通过：缺少关键输出 -> " + ', '.join(failed))
        print("建议：检查 docker-compose logs -f scheduler 输出，或扩大 --tail 行数再试")
        return 1

    print("✅ 日志验证通过：关键输出齐全")
    return 0


if __name__ == '__main__':
    sys.exit(main())

