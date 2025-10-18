#!/usr/bin/env python3
import platform
from datetime import datetime
from pathlib import Path

import pytest


def _sample_results() -> dict:
    return {
        "success": True,
        "stock_symbol": "600519",
        "stock_name": "贵州茅台",
        "analysis_date": datetime.now().strftime("%Y-%m-%d"),
        "research_depth": 2,
        "analysts": ["技术分析师", "基本面分析师", "情绪分析师", "新闻分析师"],
        "decision": {
            "action": "BUY",
            "confidence": 0.88,
            "risk_score": 0.22,
            "target_price": "¥2000.00",
            "reasoning": (
                "公司基本面稳健、品牌力强，盈利能力持续提升。"
                "技术面放量突破，支撑位明确；情绪与资金面配合良好。"
            ),
        },
        "state": {
            "market_report": "价格上穿多条均线，成交量温和放大；短期维持强势格局。",
            "fundamentals_report": "营收与净利保持增长，毛利率稳定，ROE 较高。",
            "sentiment_report": "市场舆情偏正面，机构观点一致性较高。",
            "news_report": "行业政策稳定，无重大利空事件。",
            "investment_plan": "分批建仓并设置止损，目标价 2000。",
            "risk_debate_state": {
                "risky_history": "若外部宏观波动上升，估值回撤风险需关注。",
                "safe_history": "现金流稳健，长期风险可控。",
                "neutral_history": "短期或有震荡，中长期趋势维持向上。",
                "judge_decision": "控制仓位，逢回调低吸。",
            },
        },
        "llm_provider": "deepseek",
        "llm_model": "deepseek-chat",
        "is_demo": False,
    }


@pytest.mark.skipif(platform.system() != "Darwin", reason="WeasyPrint PDF export supported on macOS only")
def test_pdf_export_saves_into_tests_dir():
    """导出中文 PDF 到 tests/pdf_outputs 目录，便于查看效果。"""
    # 依赖检查（缺失则跳过，以免误报失败）
    try:
        import weasyprint  # noqa: F401
        import markdown  # noqa: F401
    except Exception as e:  # pragma: no cover - 环境依赖缺失
        pytest.skip(f"missing dependencies for WeasyPrint test: {e}")

    import web.utils.report_exporter as rexp

    exporter = rexp.ReportExporter()
    if not exporter.weasy_available:  # 仅在 macOS 且 weasyprint 可用时运行
        pytest.skip("WeasyPrint not available on this platform/environment")

    results = _sample_results()
    pdf_bytes = exporter.export_report(results, "pdf")

    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert pdf_bytes.startswith(b"%PDF"), "Not a valid PDF header"
    assert len(pdf_bytes) > 800, "PDF too small, likely empty content"

    # 保存到 tests/pdf_outputs 目录
    out_root = Path(__file__).resolve().parent / "pdf_outputs"
    out_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_root / f"TEST_中文导出_{ts}.pdf"
    out_path.write_bytes(pdf_bytes)

    assert out_path.exists() and out_path.stat().st_size == len(pdf_bytes)
    print(f"✅ 中文 PDF 已导出: {out_path}")

