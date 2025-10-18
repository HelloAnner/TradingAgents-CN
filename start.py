#!/usr/bin/env python3
"""
TradingAgents-CN 自动化启动脚本（终端版）

本脚本不依赖 Docker 与 Web 配置页面，
基于根目录 global.json 与 tasks/*.json 启动自动化调度：
  - 启动时立即执行一轮任务
  - 每天凌晨定时执行（可在 global.json.schedule 中配置时间与是否开机即跑）

用法：
  python start.py        # 终端应用入口

测试建议：
  观察首个任务是否完成，并在 reports/<code>/<时间>/ 下生成 PDF 与 overview.txt
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def main():
    # 项目根目录
    project_root = Path(__file__).resolve().parent

    print("🚀 TradingAgents-CN 自动化调度启动器（终端应用）")
    print("=" * 64)
    print("✅ 单机模式 | 不依赖 MongoDB | 忽略 Web 配置页面")
    print("📁 项目目录:", project_root)
    print("📄 全局配置:", project_root / "global.json")
    print("📂 任务目录:", project_root / "tasks")
    print("📂 报告输出:", project_root / "reports")
    print("=" * 64)

    # 建议在虚拟环境中运行
    in_venv = (
        hasattr(sys, 'real_prefix') or
        (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    )
    if not in_venv:
        print("⚠️ 建议在虚拟环境中运行：")
        print("   Windows: .\\env\\Scripts\\activate")
        print("   Linux/macOS: source env/bin/activate")

    # 加载 .env 环境变量（用于数据源与 LLM API Key）
    load_dotenv(project_root / ".env", override=True)

    # 运行内置调度器（启动即执行 + 每日定时）
    try:
        # 延迟导入，确保 PYTHONPATH 就绪
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        from scripts.automation.run_scheduler import main as scheduler_main

        # 直接进入调度器主循环：
        # - 会在启动时运行一轮（由 global.json.schedule.run_on_startup 控制）
        # - 随后按 daily_time 定时运行
        scheduler_main()
    except KeyboardInterrupt:
        print("\n⏹️ 已停止自动化调度")
    except Exception as e:
        print(f"\n❌ 启动自动化调度失败: {e}")
        print("💡 请检查 global.json 与 tasks/*.json 配置是否有效，以及依赖是否安装齐全")


if __name__ == "__main__":
    main()

