#!/usr/bin/env python3
"""
报告导出工具
仅保留 PDF 导出（WeasyPrint，macOS 支持；Linux 暂不支持）
"""

from __future__ import annotations

import streamlit as st
import json
import os
import logging
import platform
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# 日志
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('web')

# 标准日志输出
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 依赖：markdown（md -> html）
try:
    import markdown  # type: ignore
    EXPORT_AVAILABLE = True
except Exception as e:  # pragma: no cover
    EXPORT_AVAILABLE = False
    logger.warning(f"导出功能缺少依赖 markdown: {e}")

# 依赖：WeasyPrint（html+css -> pdf）
_WEASY_IMPORT_ERROR = None
try:
    from weasyprint import HTML, CSS  # type: ignore
    try:  # 新旧版本兼容
        from weasyprint.fonts import FontConfiguration  # type: ignore
    except Exception:  # pragma: no cover
        from weasyprint.text.fonts import FontConfiguration  # type: ignore
    WEASYPRINT_AVAILABLE = True
except Exception as _e:  # pragma: no cover
    WEASYPRINT_AVAILABLE = False
    _WEASY_IMPORT_ERROR = str(_e)


class ReportExporter:
    """报告导出器（仅 PDF，基于 WeasyPrint）。"""

    def __init__(self):
        self.export_available = EXPORT_AVAILABLE
        self.platform = platform.system()
        self.weasy_available = WEASYPRINT_AVAILABLE and self.platform == 'Darwin'

        logger.info("📋 ReportExporter 初始化:")
        logger.info(f"  - export_available: {self.export_available}")
        logger.info(f"  - platform: {self.platform}")
        logger.info(f"  - weasy_available(macOS): {self.weasy_available}")
        if not self.weasy_available and _WEASY_IMPORT_ERROR:
            logger.info(f"  - weasy_import_error: {_WEASY_IMPORT_ERROR}")

    # ========== Markdown 构建 ==========
    def _clean_text_for_markdown(self, text: Any) -> str:
        if text is None:
            return "N/A"
        text = str(text)
        text = (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))
        text = text.replace('---', '—').replace('...', '…')
        return text

    def generate_markdown_report(self, results: Dict[str, Any]) -> str:
        """根据分析结果生成 Markdown 内容。"""
        stock_symbol = self._clean_text_for_markdown(results.get('stock_symbol', 'N/A'))
        decision = results.get('decision', {}) or {}
        state = results.get('state', {}) or {}
        is_demo = results.get('is_demo', False)

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        action = self._clean_text_for_markdown(decision.get('action', 'N/A')).upper()
        target_price = self._clean_text_for_markdown(decision.get('target_price', 'N/A'))
        reasoning = self._clean_text_for_markdown(decision.get('reasoning', '暂无分析推理'))

        md = f"""# {stock_symbol} 股票分析报告

**生成时间**: {timestamp}
**分析状态**: {'演示模式' if is_demo else '正式分析'}

## 🎯 投资决策摘要

| 指标 | 数值 |
|------|------|
| **投资建议** | {action} |
| **置信度** | {decision.get('confidence', 0):.1%} |
| **风险评分** | {decision.get('risk_score', 0):.1%} |
| **目标价位** | {target_price} |

### 分析推理
{reasoning}

---

## 📋 分析配置信息

- **LLM提供商**: {results.get('llm_provider', 'N/A')}
- **AI模型**: {results.get('llm_model', 'N/A')}
- **分析师数量**: {len(results.get('analysts', []))}个
- **研究深度**: {results.get('research_depth', 'N/A')}

### 参与分析师
{', '.join(results.get('analysts', []))}

---

## 📊 详细分析报告

"""

        modules = [
            ('market_report', '📈 市场技术分析', '技术指标、价格趋势、支撑阻力位分析'),
            ('fundamentals_report', '💰 基本面分析', '财务数据、估值水平、盈利能力分析'),
            ('sentiment_report', '💭 市场情绪分析', '投资者情绪、社交媒体情绪指标'),
            ('news_report', '📰 新闻事件分析', '相关新闻事件、市场动态影响分析'),
            ('risk_assessment', '⚠️ 风险评估', '风险因素识别、风险等级评估'),
            ('investment_plan', '📋 投资建议', '具体投资策略、仓位管理建议'),
        ]

        for key, title, desc in modules:
            md += f"\n### {title}\n\n"
            md += f"*{desc}*\n\n"
            content = state.get(key)
            if content:
                if isinstance(content, dict):
                    for sub_key, sub_val in content.items():
                        md += f"#### {str(sub_key).replace('_', ' ').title()}\n\n{sub_val}\n\n"
                else:
                    md += f"{content}\n\n"
            else:
                md += "暂无数据\n\n"

        md = self._add_team_decision_reports(md, state)

        md += f"""
---

## ⚠️ 重要风险提示

**投资风险提示**:
- **仅供参考**: 本分析结果仅供参考，不构成投资建议
- **投资风险**: 股票投资有风险，可能导致本金损失
- **理性决策**: 请结合多方信息进行理性投资决策
- **专业咨询**: 重大投资决策建议咨询专业财务顾问
- **自担风险**: 投资决策及其后果由投资者自行承担

---
*报告生成时间: {timestamp}*
"""
        return md

    def _add_team_decision_reports(self, md: str, state: Dict[str, Any]) -> str:
        # 研究团队决策
        if state.get('investment_debate_state'):
            s = state['investment_debate_state']
            md += "\n---\n\n## 🔬 研究团队决策\n\n"
            md += "*多头/空头研究员辩论分析，研究经理综合决策*\n\n"
            if s.get('bull_history'):
                md += "### 📈 多头研究员分析\n\n" + self._clean_text_for_markdown(s['bull_history']) + "\n\n"
            if s.get('bear_history'):
                md += "### 📉 空头研究员分析\n\n" + self._clean_text_for_markdown(s['bear_history']) + "\n\n"
            if s.get('judge_decision'):
                md += "### 🎯 研究经理综合决策\n\n" + self._clean_text_for_markdown(s['judge_decision']) + "\n\n"

        # 交易计划
        if state.get('trader_investment_plan'):
            md += "\n---\n\n## 💼 交易团队计划\n\n"
            md += "*专业交易员制定的具体交易执行计划*\n\n"
            md += self._clean_text_for_markdown(state['trader_investment_plan']) + "\n\n"

        # 风险管理团队
        if state.get('risk_debate_state'):
            s = state['risk_debate_state']
            md += "\n---\n\n## ⚖️ 风险管理团队决策\n\n"
            md += "*激进/保守/中性分析师风险评估，投资组合经理最终决策*\n\n"
            if s.get('risky_history'):
                md += "### 🚀 激进分析师评估\n\n" + self._clean_text_for_markdown(s['risky_history']) + "\n\n"
            if s.get('safe_history'):
                md += "### 🛡️ 保守分析师评估\n\n" + self._clean_text_for_markdown(s['safe_history']) + "\n\n"
            if s.get('neutral_history'):
                md += "### ⚖️ 中性分析师评估\n\n" + self._clean_text_for_markdown(s['neutral_history']) + "\n\n"
            if s.get('judge_decision'):
                md += "### 🎯 投资组合经理最终决策\n\n" + self._clean_text_for_markdown(s['judge_decision']) + "\n\n"

        # 最终交易决策
        if state.get('final_trade_decision'):
            md += "\n---\n\n## 🎯 最终交易决策\n\n"
            md += "*综合所有团队分析后的最终投资决策*\n\n"
            md += self._clean_text_for_markdown(state['final_trade_decision']) + "\n\n"
        return md

    # ========== PDF 生成（WeasyPrint） ==========
    def _render_pdf_via_cli(self, html_content: str, css_content: str, title: str) -> bytes:
        """通过 weasyprint 命令行生成 PDF（兜底）。"""
        # 检查 weasyprint 可执行文件
        weasy_bin = shutil.which("weasyprint")
        if not weasy_bin:
            raise Exception("系统未找到 weasyprint 可执行文件（命令 'weasyprint' 不存在）")

        # 将 CSS 内联进 HTML，减少 CLI 传参复杂度
        html_with_style = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset=\"UTF-8\" />
  <title>{title} 分析报告</title>
  <style>
  {css_content}
  </style>
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <meta http-equiv=\"X-UA-Compatible\" content=\"IE=edge\" />
  <meta name=\"format-detection\" content=\"telephone=no\" />
  <meta name=\"format-detection\" content=\"email=no\" />
  <meta name=\"apple-mobile-web-app-capable\" content=\"yes\" />
  <meta name=\"apple-mobile-web-app-status-bar-style\" content=\"black-translucent\" />
  <meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'self' 'unsafe-inline' data: blob:; img-src 'self' data:;\" />
  <meta http-equiv=\"cache-control\" content=\"max-age=0\" />
  <meta http-equiv=\"cache-control\" content=\"no-cache\" />
  <meta http-equiv=\"expires\" content=\"0\" />
  <meta http-equiv=\"expires\" content=\"Tue, 01 Jan 1980 1:00:00 GMT\" />
  <meta http-equiv=\"pragma\" content=\"no-cache\" />
  <meta name=\"color-scheme\" content=\"light only\" />
  <meta name=\"supported-color-schemes\" content=\"light\" />
  <meta http-equiv=\"X-Content-Type-Options\" content=\"nosniff\" />
  <meta http-equiv=\"Referrer-Policy\" content=\"no-referrer\" />
  <meta name=\"referrer\" content=\"no-referrer\" />
</head>
<body>
  {html_content}
</body>
</html>
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = os.path.join(tmpdir, "report.html")
            pdf_path = os.path.join(tmpdir, "report.pdf")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_with_style)

            logger.info(f"🖨️ 使用 weasyprint CLI 生成 PDF: {weasy_bin}")
            try:
                cmd = [weasy_bin, html_path, pdf_path]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                if result.stdout:
                    logger.debug(f"weasyprint 输出: {result.stdout.strip()}")
                if result.stderr:
                    logger.debug(f"weasyprint 警告: {result.stderr.strip()}")
            except subprocess.CalledProcessError as e:
                err = e.stderr or e.stdout or str(e)
                raise Exception(f"weasyprint CLI 生成失败: {err}")

            if not os.path.exists(pdf_path):
                raise Exception("weasyprint CLI 未生成 PDF 文件")
            with open(pdf_path, "rb") as f:
                return f.read()

    def generate_pdf_report(self, results: Dict[str, Any]) -> bytes:
        """生成 PDF：优先 Python WeasyPrint，失败时兜底到 weasyprint CLI。"""

        md_content = self.generate_markdown_report(results)
        logger.info(f"✅ Markdown内容长度: {len(md_content)}")

        # Markdown -> HTML
        try:
            html_body = markdown.markdown(md_content, extensions=["extra", "tables", "nl2br"])  # type: ignore
        except Exception:
            html_body = markdown.markdown(md_content)  # type: ignore

        title = self._clean_text_for_markdown(results.get('stock_symbol', '分析报告'))
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset=\"UTF-8\" />
  <title>{title} 分析报告</title>
</head>
<body>
  {html_body}
</body>
</html>
"""

        css_content = """
@page { size: A4; margin: 20mm; }
body { font-family: 'PingFang SC', 'Noto Sans CJK SC', 'Heiti SC', 'Helvetica', 'Arial', sans-serif; font-size: 12pt; line-height: 1.6; color: #222; }
h1, h2, h3 { color: #333; border-bottom: 1px solid #eee; padding-bottom: 4px; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 16px; }
th, td { border: 1px solid #ddd; padding: 6px 8px; }
th { background: #f8f8f8; }
code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace; }
"""

        # 优先尝试 Python WeasyPrint（macOS 优先；Linux 也尝试，但失败会自动回退）
        if WEASYPRINT_AVAILABLE:
            try:
                font_config = FontConfiguration()
                html = HTML(string=html_content)
                css = CSS(string=css_content, font_config=font_config)
                pdf_bytes = html.write_pdf(stylesheets=[css], font_config=font_config)
                logger.info(f"✅ PDF 生成成功（python-weasyprint），大小: {len(pdf_bytes)} 字节")
                return pdf_bytes
            except Exception as e:
                logger.warning(f"⚠️ python-weasyprint 生成失败，尝试 CLI 兜底: {e}")
        else:
            logger.info("python-weasyprint 不可用，尝试 CLI 兜底")

        # CLI 兜底：不依赖 Python 包导入
        title = self._clean_text_for_markdown(results.get('stock_symbol', '分析报告'))
        return self._render_pdf_via_cli(html_body, css_content, title)

    def export_report(self, results: Dict[str, Any], format_type: str) -> Optional[bytes]:
        """仅支持导出为 PDF。"""
        logger.info(f"🚀 开始导出报告: format={format_type}")
        if not self.export_available:
            st.error("❌ 导出功能不可用，请安装 markdown 依赖")
            return None
        if format_type != 'pdf':
            st.error("❌ 仅支持导出 PDF")
            return None
        try:
            content = self.generate_pdf_report(results)
            return content
        except Exception as e:
            logger.error(f"❌ 导出失败: {e}", exc_info=True)
            st.error(f"❌ 导出失败: {e}")
            return None


# ========== CLI 结果存档（与现有使用保持一致） ==========
def _format_team_decision_content(content: Dict[str, Any], module_key: str) -> str:
    formatted = ""
    if module_key == 'investment_debate_state':
        if content.get('bull_history'):
            formatted += "## 📈 多头研究员分析\n\n" + str(content['bull_history']) + "\n\n"
        if content.get('bear_history'):
            formatted += "## 📉 空头研究员分析\n\n" + str(content['bear_history']) + "\n\n"
        if content.get('judge_decision'):
            formatted += "## 🎯 研究经理综合决策\n\n" + str(content['judge_decision']) + "\n\n"
    elif module_key == 'risk_debate_state':
        if content.get('risky_history'):
            formatted += "## 🚀 激进分析师评估\n\n" + str(content['risky_history']) + "\n\n"
        if content.get('safe_history'):
            formatted += "## 🛡️ 保守分析师评估\n\n" + str(content['safe_history']) + "\n\n"
        if content.get('neutral_history'):
            formatted += "## ⚖️ 中性分析师评估\n\n" + str(content['neutral_history']) + "\n\n"
        if content.get('judge_decision'):
            formatted += "## 🎯 投资组合经理最终决策\n\n" + str(content['judge_decision']) + "\n\n"
    return formatted


def save_modular_reports_to_results_dir(results: Dict[str, Any], stock_symbol: str) -> Dict[str, str]:
    """保存分模块报告到 results/<code>/<date>/reports 目录。"""
    try:
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent

        results_dir_env = os.getenv("TRADINGAGENTS_RESULTS_DIR")
        if results_dir_env:
            results_dir = project_root / results_dir_env if not os.path.isabs(results_dir_env) else Path(results_dir_env)
        else:
            results_dir = project_root / "results"

        analysis_date = datetime.now().strftime('%Y-%m-%d')
        stock_dir = results_dir / stock_symbol / analysis_date
        reports_dir = stock_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        # touch message_tool.log
        (stock_dir / "message_tool.log").touch(exist_ok=True)

        state = results.get('state', {}) or {}
        saved: Dict[str, str] = {}

        report_modules = {
            'market_report': {
                'filename': 'market_report.md',
                'title': f'{stock_symbol} 股票技术分析报告',
                'state_key': 'market_report'
            },
            'sentiment_report': {
                'filename': 'sentiment_report.md',
                'title': f'{stock_symbol} 市场情绪分析报告',
                'state_key': 'sentiment_report'
            },
            'news_report': {
                'filename': 'news_report.md',
                'title': f'{stock_symbol} 新闻事件分析报告',
                'state_key': 'news_report'
            },
            'fundamentals_report': {
                'filename': 'fundamentals_report.md',
                'title': f'{stock_symbol} 基本面分析报告',
                'state_key': 'fundamentals_report'
            },
            'investment_plan': {
                'filename': 'investment_plan.md',
                'title': f'{stock_symbol} 投资决策报告',
                'state_key': 'investment_plan'
            },
            'trader_investment_plan': {
                'filename': 'trader_investment_plan.md',
                'title': f'{stock_symbol} 交易计划报告',
                'state_key': 'trader_investment_plan'
            },
            'final_trade_decision': {
                'filename': 'final_trade_decision.md',
                'title': f'{stock_symbol} 最终投资决策',
                'state_key': 'final_trade_decision'
            },
            'investment_debate_state': {
                'filename': 'research_team_decision.md',
                'title': f'{stock_symbol} 研究团队决策报告',
                'state_key': 'investment_debate_state'
            },
            'risk_debate_state': {
                'filename': 'risk_management_decision.md',
                'title': f'{stock_symbol} 风险管理团队决策报告',
                'state_key': 'risk_debate_state'
            }
        }

        for module_key, info in report_modules.items():
            content = state.get(info['state_key'])
            if not content:
                continue

            if isinstance(content, str):
                report_content = content if content.strip().startswith('#') else f"# {info['title']}\n\n{content}"
            elif isinstance(content, dict):
                if module_key in ['investment_debate_state', 'risk_debate_state']:
                    report_content = f"# {info['title']}\n\n" + _format_team_decision_content(content, module_key)
                else:
                    report_content = f"# {info['title']}\n\n" + "\n\n".join(
                        f"## {k.replace('_', ' ').title()}\n\n{v}" for k, v in content.items()
                    ) + "\n\n"
            else:
                report_content = f"# {info['title']}\n\n{str(content)}"

            file_path = reports_dir / info['filename']
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            saved[module_key] = str(file_path)
            logger.info(f"✅ 保存模块报告: {file_path}")

        # 额外保存元数据
        metadata = {
            'stock_symbol': stock_symbol,
            'analysis_date': analysis_date,
            'timestamp': datetime.now().isoformat(),
            'research_depth': results.get('research_depth', 1),
            'analysts': results.get('analysts', []),
            'status': 'completed',
            'reports_count': len(saved),
            'report_types': list(saved.keys()),
        }
        metadata_file = reports_dir.parent / "analysis_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ 保存分析元数据: {metadata_file}")

        return saved
    except Exception as e:  # pragma: no cover
        logger.error(f"❌ 保存分模块报告失败: {e}")
        return {}


def save_report_to_results_dir(content: bytes, filename: str, stock_symbol: str) -> str:
    """保存 PDF 到 results/<code>/<date>/reports/ 目录，返回路径。"""
    try:
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent
        results_dir_env = os.getenv("TRADINGAGENTS_RESULTS_DIR")
        if results_dir_env:
            results_dir = project_root / results_dir_env if not os.path.isabs(results_dir_env) else Path(results_dir_env)
        else:
            results_dir = project_root / "results"

        analysis_date = datetime.now().strftime('%Y-%m-%d')
        stock_dir = results_dir / stock_symbol / analysis_date / "reports"
        stock_dir.mkdir(parents=True, exist_ok=True)

        file_path = stock_dir / filename
        with open(file_path, 'wb') as f:
            f.write(content)
        logger.info(f"✅ 报告已保存到: {file_path}")
        return str(file_path)
    except Exception as e:  # pragma: no cover
        logger.error(f"❌ 保存报告到results目录失败: {e}")
        return ""


# ========== Web 按钮 ==========
def render_export_buttons(results: Dict[str, Any]):
    """渲染导出按钮（仅 PDF / WeasyPrint）。"""
    if not results:
        return

    st.markdown("---")
    st.subheader("📤 导出报告（PDF / WeasyPrint）")

    if platform.system() == 'Linux':
        st.warning("⚠️ 当前 Linux 系统暂不支持 WeasyPrint 导出（后续提供支持）")
        return
    if not WEASYPRINT_AVAILABLE:
        st.error("❌ 未检测到 WeasyPrint。请先安装：pip install weasyprint")
        return

    stock_symbol = results.get('stock_symbol', 'analysis')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if st.button("📊 导出 PDF", help="WeasyPrint 导出为 PDF"):
        logger.info(f"🖱️ 用户点击PDF导出按钮 - 股票: {stock_symbol}")
        with st.spinner("正在生成PDF，请稍候..."):
            try:
                logger.info("🔄 开始PDF导出流程 (WeasyPrint)...")
                modular_files = save_modular_reports_to_results_dir(results, stock_symbol)
                content = report_exporter.export_report(results, 'pdf')
                if content:
                    filename = f"{stock_symbol}_analysis_{timestamp}.pdf"
                    saved_path = save_report_to_results_dir(content, filename, stock_symbol)

                    if modular_files and saved_path:
                        st.success(f"✅ 已保存 {len(modular_files)} 个分模块报告 + 1个PDF汇总报告")
                        with st.expander("📁 查看保存的文件"):
                            st.write("**分模块报告:**")
                            for module, path in modular_files.items():
                                st.write(f"- {module}: `{path}`")
                            st.write("**PDF汇总报告:**")
                            st.write(f"- PDF报告: `{saved_path}`")
                    elif saved_path:
                        st.success(f"✅ PDF已保存到: {saved_path}")
                    else:
                        st.success("✅ PDF生成成功！")

                    st.download_button(
                        label="📥 下载 PDF",
                        data=content,
                        file_name=filename,
                        mime="application/pdf"
                    )
                else:
                    logger.error("❌ PDF导出失败，content为空")
                    st.error("❌ PDF生成失败")
            except Exception as e:
                logger.error(f"❌ PDF导出异常: {e}", exc_info=True)
                st.error("❌ PDF生成失败")
                with st.expander("🔍 查看详细错误信息"):
                    st.text(str(e))
                st.info("💡 macOS 推荐使用 WeasyPrint；Linux 暂不支持。")


# 全局导出器实例
report_exporter = ReportExporter()
