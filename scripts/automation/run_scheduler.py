#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动化调度入口

功能概述：
- 启动时立即执行一次批量分析（基于 tasks 目录配置）
- 每天凌晨定时（默认 00:00，本地时区可通过 global.json 配置）再次执行
- 为每个任务生成 overview.txt，并按配置发送邮件
- PDF 导出与邮件附件可通过 global.json 临时关闭（不删除代码，仅跳过执行）

注意：
- 该脚本不依赖 Web 配置页面，仅使用根目录 global.json 与 tasks/*.json
- 需要在 .env 中配置各数据源与 LLM 提供商的 API Key
"""

from __future__ import annotations

import os
import json
import time
import signal
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    # Python 3.9+
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from dotenv import load_dotenv

# 确保项目根目录在 Python 路径中，以便可导入 tradingagents 包
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 统一日志
from tradingagents.utils.logging_manager import get_logger

# 复用现有分析与导出能力
from web.utils.analysis_runner import run_stock_analysis
from web.utils.report_exporter import ReportExporter

# 邮件发送工具
from scripts.automation.smtp_mailer import MailSender, MailConfig


logger = get_logger("automation")


# ===== 用户到期与任务收件人维护 =====
def _load_user_registry(root: Path) -> Dict[str, Any]:
    """加载根目录 user.json，若不存在则创建默认结构。

    结构示例：
    {
      "users": [
        {"email": "user@example.com", "name": "张三", "expires_on": "2025-12-31"}
      ],
      "expired": [
        {"email": "old@example.com", "name": "李四", "expires_on": "2024-12-31", "expired_on": "2025-10-17"}
      ]
    }
    """
    path = root / "user.json"
    default_data = {"users": [], "expired": []}
    if not path.exists():
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default_data, f, ensure_ascii=False, indent=2)
            logger.info(f"已创建默认的用户注册表: {path}")
        except Exception as e:
            logger.error(f"创建 user.json 失败: {e}")
        return default_data
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 兜底字段
        if not isinstance(data, dict):
            data = default_data
        data.setdefault("users", [])
        data.setdefault("expired", [])
        return data
    except Exception as e:
        logger.error(f"读取 user.json 失败: {e}")
        return default_data


def _save_user_registry(root: Path, data: Dict[str, Any]) -> None:
    path = root / "user.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"已更新用户注册表: {path}")
    except Exception as e:
        logger.error(f"写入 user.json 失败: {e}")


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _parse_date_yyyy_mm_dd(s: Optional[str]):
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def update_users_and_prune_tasks(root: Path, tasks_dir: Path, tz: Optional[ZoneInfo]) -> None:
    """更新 user.json 的到期用户，并清理 tasks/*.json 的收件人列表。

    - 将 user.json 中 "users" 里已过期的邮箱移动到 "expired" 并记录 "expired_on"
    - 遍历 tasks 下所有任务文件，仅保留仍在 user.json 的有效邮箱（非过期）
    """
    registry = _load_user_registry(root)
    users = registry.get("users", []) or []
    expired_list = registry.get("expired", []) or []

    today = (datetime.now(tz).date() if tz else datetime.now().date())

    # 计算过期邮箱集合与仍有效用户
    expired_emails: List[str] = []
    remaining_users: List[Dict[str, Any]] = []

    for u in users:
        email = _normalize_email(u.get("email", ""))
        expires_on = _parse_date_yyyy_mm_dd(u.get("expires_on"))
        if not email:
            continue
        if expires_on and expires_on <= today:
            moved = dict(u)
            moved["expired_on"] = today.strftime("%Y-%m-%d")
            expired_list.append(moved)
            expired_emails.append(email)
        else:
            remaining_users.append(u)

    changed_registry = (len(remaining_users) != len(users))
    if changed_registry:
        registry["users"] = remaining_users
        registry["expired"] = expired_list
        _save_user_registry(root, registry)
        logger.info(f"📋 用户到期更新: 移动 {len(expired_emails)} 个到期邮箱到失效名单")
    else:
        logger.info("📋 用户到期更新: 无到期邮箱")

    # 重新构建仍有效的用户邮箱集合（小写）
    valid_user_set = { _normalize_email(u.get("email", "")) for u in remaining_users if _normalize_email(u.get("email", "")) }
    expired_set = set(expired_emails)

    # 遍历并修正 tasks 下所有任务的收件人：仅保留有效用户（非过期且在 user.json 中）
    if not tasks_dir.exists():
        return
    pruned_tasks = 0
    total_removed = 0
    for p in sorted(tasks_dir.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                task_cfg = json.load(f)
        except Exception as e:
            logger.error(f"读取任务失败，跳过: {p} - {e}")
            continue

        recipients = task_cfg.get("email_recipients", []) or []
        norm_recipients = [_normalize_email(x) for x in recipients if x]
        # 仅保留在有效用户集合中的邮箱
        filtered = [x for x in norm_recipients if x in valid_user_set]

        if filtered != recipients:
            task_cfg["email_recipients"] = filtered
            try:
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(task_cfg, f, ensure_ascii=False, indent=2)
                removed_count = len(recipients) - len(filtered)
                pruned_tasks += 1
                total_removed += removed_count
                logger.info(f"✂️ 更新任务: {p.name} - 移除无效/过期收件人 {removed_count} 个，保留 {len(filtered)} 个有效收件人")
            except Exception as e:
                logger.error(f"写入任务失败: {p} - {e}")

    if pruned_tasks:
        logger.info(f"📬 已更新 {pruned_tasks} 个任务，累计移除 {total_removed} 个无效/过期邮箱")
    else:
        logger.info("📬 所有任务收件人无需更新")


def load_global_config(root: Path) -> Dict[str, Any]:
    """加载根目录 global.json，全局配置。

    返回字段示例：
    {
      "timezone": "Asia/Shanghai",
      "analysis": {"analysts": [...], "research_depth": 3, "market_type": "A股", "llm_provider": "dashscope", "llm_model": "qwen-plus"},
      "smtp": {"host":"", "port":465, "username":"", "password":"", "use_ssl":true, "from_email":"", "from_name":""},
      "reports_dir": "reports",
      "schedule": {"daily_time": "00:00", "run_on_startup": true}
    }
    """
    cfg_path = root / "global.json"
    if not cfg_path.exists():
        raise FileNotFoundError(f"未找到全局配置文件: {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_task_configs(tasks_dir: Path) -> List[Dict[str, Any]]:
    """加载 tasks 目录下的任务配置（以股票代码命名的 json）。"""
    tasks: List[Dict[str, Any]] = []
    if not tasks_dir.exists():
        logger.warning(f"任务目录不存在，自动创建: {tasks_dir}")
        tasks_dir.mkdir(parents=True, exist_ok=True)
        return tasks

    for p in sorted(tasks_dir.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            code = p.stem
            cfg.setdefault("stock_code", code)
            cfg.setdefault("email_recipients", [])
            cfg.setdefault("disabled", False)
            tasks.append(cfg)
        except Exception as e:
            logger.error(f"加载任务配置失败: {p} - {e}")
    return tasks


def ensure_reports_dir(base_dir: Path) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)


def build_overview_text(results: Dict[str, Any]) -> str:
    """根据分析结果生成简要结论，用于 overview.txt 与邮件正文。"""
    stock = results.get("stock_symbol", "N/A")
    decision = results.get("decision", {}) or {}
    state = results.get("state", {}) or {}

    action = str(decision.get("action", "N/A")).upper()
    confidence = decision.get("confidence")
    risk_score = decision.get("risk_score")
    target_price = decision.get("target_price")
    reasoning = decision.get("reasoning") or ""

    # 裁剪推理为短文
    if reasoning:
        reasoning = reasoning.strip()
        if len(reasoning) > 500:
            reasoning = reasoning[:500].rstrip() + "..."

    lines = [
        f"【股票】{stock}",
        f"【建议】{action}",
    ]
    if confidence is not None:
        try:
            lines.append(f"【置信度】{float(confidence)*100:.1f}%")
        except Exception:
            lines.append(f"【置信度】{confidence}")
    if risk_score is not None:
        try:
            lines.append(f"【风险】{float(risk_score)*100:.1f}%")
        except Exception:
            lines.append(f"【风险】{risk_score}")
    if target_price is not None:
        lines.append(f"【目标价】{target_price}")

    if reasoning:
        lines.append("")
        lines.append("【结论摘要】")
        lines.append(reasoning)

    # 简要加入风险管理结论（可选）
    risk_state = state.get("risk_debate_state") or {}
    judge = risk_state.get("judge_decision")
    if judge:
        lines.append("")
        lines.append("【风险管理结论】")
        lines.append(str(judge).strip())

    lines.append("")
    lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("提示：本结果仅供参考，不构成投资建议。")
    return "\n".join(lines)


def save_outputs(
    reports_root: Path,
    stock_code: str,
    results: Dict[str, Any],
    exporter: ReportExporter,
    disable_pdf: bool = False,
) -> Dict[str, str]:
    """保存 overview.txt 和（可选）PDF 到 reports/<code>/<时间>/ 目录。

    返回：{"pdf": <path>, "overview": <path>, "folder": <folder_path>}（若关闭PDF则pdf可能为空路径）
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = reports_root / stock_code / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    # 生成 PDF（可禁用）
    pdf_path = out_dir / f"{stock_code}_analysis_{timestamp}.pdf"
    if disable_pdf:
        logger.info("🛑 PDF 导出已临时关闭，跳过生成PDF")
    else:
        pdf_bytes = exporter.export_report(results, "pdf")
        if pdf_bytes:
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            logger.info(f"保存PDF: {pdf_path}")
        else:
            logger.error("PDF 生成失败")

    # 保存 overview
    overview_text = build_overview_text(results)
    overview_path = out_dir / "overview.txt"
    with open(overview_path, "w", encoding="utf-8") as f:
        f.write(overview_text)
    logger.info(f"保存概览: {overview_path}")

    return {"pdf": str(pdf_path), "overview": str(overview_path), "folder": str(out_dir)}


def run_once(global_cfg: Dict[str, Any], tasks: List[Dict[str, Any]], project_root: Path) -> None:
    """执行一轮批量任务。"""
    # 报告根目录
    reports_dir_name = global_cfg.get("reports_dir", "reports")
    reports_root = project_root / reports_dir_name
    ensure_reports_dir(reports_root)

    # 组装分析默认参数（market_type 仅在任务中指定；全局不限制）
    analysis_cfg = global_cfg.get("analysis", {})
    default_analysts: List[str] = analysis_cfg.get(
        "analysts", ["market", "fundamentals", "news", "social"]
    )
    default_research_depth: int = int(analysis_cfg.get("research_depth", 3))
    # LLM 设置（兼容旧字段 + 新的 llm 配置块）
    llm_block = global_cfg.get("llm", {}) or {}
    # provider 优先级：llm.provider > analysis.llm_provider > 默认 deepseek
    llm_provider: str = (
        str(llm_block.get("provider") or analysis_cfg.get("llm_provider") or "deepseek")
    )
    # 模型：支持 quick/deep 单独配置；若未提供则退回 analysis.llm_model
    llm_model_fallback = str(analysis_cfg.get("llm_model", "deepseek-chat"))
    quick_model_override = llm_block.get("quick_model")
    deep_model_override = llm_block.get("deep_model")
    unified_model = llm_block.get("model") or llm_model_fallback
    # base_url（聊天模型）
    llm_base_url: Optional[str] = llm_block.get("base_url")
    # 自定义OpenAI兼容端点（当 provider == custom_openai 时）
    custom_openai_base_url: Optional[str] = llm_block.get("base_url") if str(llm_provider).lower() == "custom_openai" else None

    # 向量/Embedding 设置（可选）
    embeddings_cfg: Optional[Dict[str, Any]] = global_cfg.get("embeddings")

    # 初始化导出器（保留实现；可通过配置关闭PDF生成）
    exporter = ReportExporter()

    # 初始化邮件发送器
    smtp_cfg = global_cfg.get("smtp", {})
    mailer = MailSender(MailConfig.from_dict(smtp_cfg))

    # 功能开关（通过 global.json 配置）
    disable_pdf_export: bool = bool(global_cfg.get("disable_pdf_export", False))
    disable_email_attachments: bool = bool(global_cfg.get("disable_email_attachments", False))

    total = len(tasks)
    logger.info(f"共发现 {total} 个任务")
    for idx, task in enumerate(tasks, start=1):
        logger.info(f"===== 任务 {idx}/{total} 开始 =====")
        if task.get("disabled"):
            logger.info("任务已禁用，跳过")
            continue

        stock_code = str(task.get("stock_code") or "").strip() or "UNKNOWN"
        recipients_raw = task.get("email_recipients", []) or []
        recipients = [_normalize_email(x) for x in recipients_raw if x]
        if not recipients:
            logger.info(f"收件人为空，跳过分析: {stock_code}")
            logger.info(f"===== 任务 {idx}/{total} 跳过（无收件人） =====")
            continue
        # 股票类型（市场类型）仅在任务中指定；若缺失，回退为 A股
        market_type = task.get("market_type") or "A股"
        analysts = task.get("analysts", default_analysts)
        research_depth = int(task.get("research_depth", default_research_depth))
        # 统一LLM提供商/模型：全局一致（忽略任务级覆盖）
        provider = llm_provider
        model = deep_model_override or quick_model_override or unified_model

        logger.info(f"开始分析: {stock_code} | 市场={market_type} | 深度={research_depth} | 模型={provider}/{model}")

        # 使用今天日期（字符串）传入分析器
        today_str = datetime.now().strftime("%Y-%m-%d")

        # 执行分析
        logger.info("[1/4] 调用分析引擎 ...")
        results = run_stock_analysis(
            stock_symbol=stock_code,
            analysis_date=today_str,
            analysts=analysts,
            research_depth=research_depth,
            llm_provider=provider,
            llm_model=unified_model,
            # 新增：可选的细粒度配置
            quick_model=quick_model_override,
            deep_model=deep_model_override,
            llm_base_url=llm_base_url,
            custom_openai_base_url=custom_openai_base_url,
            embeddings=embeddings_cfg,
            market_type=market_type,
            progress_callback=None,
        )

        if not results or not results.get("success"):
            logger.error(f"分析失败，跳过发送: {stock_code} | 错误={results.get('error') if results else 'unknown'}")
            continue

        # 生成并保存 概览 与（可选）PDF
        logger.info("[2/4] 生成与保存报告 ...")
        paths = save_outputs(
            reports_root,
            stock_code,
            results,
            exporter,
            disable_pdf=disable_pdf_export,
        )

        # 发送邮件（正文为 overview，附件可禁用）
        pdf_path = paths.get("pdf")
        overview_path = paths.get("overview")
        if recipients:
            try:
                with open(overview_path, "r", encoding="utf-8") as f:
                    body = f.read()
            except Exception as e:
                logger.error(f"读取概览失败，跳过发送: {stock_code} - {e}")
                body = None

            if body is not None:
                # 邮件标题: [股票代码] 公司名称 日期 每日分析报告
                company_name = results.get("stock_name") or ""
                date_str = datetime.now().strftime('%Y-%m-%d')
                subject = f"[{stock_code}] {company_name} {date_str} 每日分析报告".strip()

                # 附件策略：若关闭附件，则不附加PDF；若开启，且PDF存在则附加
                attachments: Optional[List[str]] = None
                if not disable_email_attachments and not disable_pdf_export and pdf_path and os.path.exists(pdf_path):
                    attachments = [pdf_path]
                elif not disable_email_attachments and not disable_pdf_export:
                    logger.warning(f"已启用附件但未找到PDF: {stock_code} -> 仅发送正文")

                try:
                    logger.info("[3/4] 发送邮件 ...")
                    mailer.send_email(
                        to_addrs=recipients,
                        subject=subject,
                        body=body,
                        attachments=attachments,
                    )
                    if attachments:
                        logger.info(f"📧 已发送邮件（含附件）: {stock_code} -> {len(recipients)} 位收件人")
                    else:
                        logger.info(f"📧 已发送邮件（正文无附件）: {stock_code} -> {len(recipients)} 位收件人")
                except Exception as e:
                    logger.error(f"邮件发送失败: {stock_code} - {e}")
        else:
            logger.info(f"未配置收件人，跳过邮件发送: {stock_code}")

        logger.info("[4/4] 任务结束")
        logger.info(f"===== 任务 {idx}/{total} 完成 =====")


def parse_daily_time(s: str) -> (int, int):
    """解析 "HH:MM" 时间为 (hour, minute)。"""
    try:
        hh, mm = s.strip().split(":", 1)
        return int(hh), int(mm)
    except Exception:
        return 0, 0


def compute_sleep_seconds(now: datetime, hour: int, minute: int, tz: Optional[ZoneInfo]) -> int:
    """计算从 now 到下次(hour:minute)的休眠秒数。"""
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run = next_run + timedelta(days=1)
    delta = (next_run - now).total_seconds()
    return int(max(1, delta))


def main():
    project_root = Path(__file__).resolve().parents[2]

    # 加载 .env 环境变量
    load_dotenv(project_root / ".env", override=True)

    # 加载配置
    global_cfg = load_global_config(project_root)
    tasks_dir = project_root / "tasks"
    tasks = load_task_configs(tasks_dir)
    if not tasks:
        logger.warning("未在 tasks 目录发现任何任务配置，调度器将空跑。")

    # 时区设置
    tz_name = global_cfg.get("timezone", "Asia/Shanghai")
    tz = ZoneInfo(tz_name) if ZoneInfo else None
    schedule_cfg = global_cfg.get("schedule", {})
    run_on_startup = bool(schedule_cfg.get("run_on_startup", True))
    daily_time = schedule_cfg.get("daily_time", "00:00")
    hh, mm = parse_daily_time(daily_time)

    stop = False

    def handle_sigterm(signum, frame):  # pragma: no cover
        nonlocal stop
        logger.info("收到终止信号，准备安全退出...")
        stop = True
        # 直接终止进程，避免在长时间执行的分析流程中迟迟不退出
        try:
            import sys as _sys2
            _sys2.exit(0)
        except BaseException:
            # 兜底：确保退出
            import os as _os2
            _os2._exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    # 运行模式：支持 RUN_ONCE（环境变量或命令行参数）
    run_once_flag = os.getenv("RUN_ONCE", "false").lower() in ("1", "true", "yes")
    import sys as _sys
    if any(arg in ("--once", "-1", "--run-once") for arg in _sys.argv[1:]):
        run_once_flag = True

    # 启动即运行：先更新用户与任务收件人，再执行
    if run_on_startup:
        logger.info("启动触发：更新用户与任务收件人 -> 执行一次批量分析")
        try:
            update_users_and_prune_tasks(project_root, tasks_dir, tz)
            tasks = load_task_configs(tasks_dir)
        except Exception as e:
            logger.error(f"启动阶段用户/任务更新失败: {e}")
        try:
            run_once(global_cfg, tasks, project_root)
        except Exception as e:
            logger.error(f"启动执行失败: {e}")

    # 若配置为只运行一次，则直接退出，便于外部重建/重启触发下次运行
    if run_once_flag:
        logger.info("RUN_ONCE 启用：本次执行完成后退出进程")
        return

    # 进入每日调度循环
    logger.info(f"进入调度循环：每日 {daily_time} 定时执行，时区={tz_name}")
    while not stop:
        now = datetime.now(tz) if tz else datetime.now()
        sleep_sec = compute_sleep_seconds(now, hh, mm, tz)
        logger.info(f"距离下次执行还有 {sleep_sec} 秒（{sleep_sec/3600:.2f} 小时）")
        # 分段休眠，便于中断
        step = 30
        while sleep_sec > 0 and not stop:
            time.sleep(min(step, sleep_sec))
            sleep_sec -= step
        if stop:
            break
        try:
            # 每次定时运行前，先更新用户与任务收件人
            update_users_and_prune_tasks(project_root, tasks_dir, tz)
            tasks = load_task_configs(tasks_dir)  # 支持动态新增与更新后的任务
            run_once(global_cfg, tasks, project_root)
        except Exception as e:
            logger.error(f"定时执行失败: {e}")


if __name__ == "__main__":
    main()
