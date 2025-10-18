#!/usr/bin/env python3
import os
import sys

import pytest
import platform


def _build_minimal_results() -> dict:
    return {
        "success": True,
        "stock_symbol": "600519",
        "stock_name": "贵州茅台",
        "analysis_date": "2025-10-18",
        "research_depth": 2,
        "analysts": ["market", "fundamentals", "news", "social"],
        "decision": {
            "action": "BUY",
            "confidence": 0.85,
            "risk_score": 0.25,
            "target_price": "2000.00",
            "reasoning": (
                "该公司基本面稳健，品牌力强，现金流充裕。"
                "技术面显示放量突破，情绪与资金面配合良好，短中期具备上行空间。"
            ),
        },
        "state": {
            "market_report": "价格突破重要均线，成交量明显放大；短期支撑与阻力位明确。",
            "fundamentals_report": "营业收入与净利润保持双位数增长，毛利率稳定；ROE 较高。",
            "sentiment_report": "社交媒体与新闻情绪偏正面，机构观点较为一致。",
            "news_report": "近期政策面与行业环境稳定，无重大利空消息。",
            "risk_debate_state": {
                "risky_history": "若宏观波动加剧，估值高位存在回撤风险。",
                "safe_history": "基本面与现金流稳健，长期风险可控。",
                "neutral_history": "短期可能震荡，中长期趋势仍向上。",
                "judge_decision": "控制仓位，分批建仓并设置止损线。",
            },
            "investment_plan": "首批建仓 20%，回调加仓，目标价至 2000。",
        },
    }


def test_chinese_pdf_export_weasyprint(tmp_path):
    """使用 WeasyPrint 生成中文 PDF，并将文件保存到 reports/test_exports 方便查看。"""
    import web.utils.report_exporter as rexp

    # 仅在 macOS 上运行；Linux 暂不支持
    if platform.system() != 'Darwin':
        pytest.skip('WeasyPrint export currently supported on macOS only')

    # 依赖检查
    try:
        import weasyprint  # noqa: F401
        import markdown  # noqa: F401
    except Exception as e:
        pytest.skip(f'missing dependencies for WeasyPrint test: {e}')

    exporter = rexp.ReportExporter()
    if not exporter.weasy_available:
        pytest.skip('WeasyPrint not available on this platform/environment')

    results = _build_minimal_results()
    pdf_bytes = exporter.export_report(results, 'pdf')

    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert pdf_bytes.startswith(b'%PDF'), 'Not a valid PDF header'
    assert len(pdf_bytes) > 800, 'PDF too small, likely empty content'

    # 保存到项目 reports/test_exports 目录，便于手动查看
    from pathlib import Path
    from datetime import datetime
    project_root = Path(__file__).resolve().parents[1]
    out_root = project_root / 'reports' / 'test_exports'
    out_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = out_root / f"TEST_中文导出_{ts}.pdf"
    with open(out_path, 'wb') as f:
        f.write(pdf_bytes)

    # 断言文件存在且可读
    assert out_path.exists() and out_path.stat().st_size == len(pdf_bytes)
    print(f"✅ WeasyPrint 测试 PDF 已保存: {out_path}")
