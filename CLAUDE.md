# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

TradingAgents-CN 是基于多智能体大语言模型的中文金融交易决策框架，专为中文用户优化，提供完整的A股/港股/美股分析能力。

## 核心架构

### 多智能体协作系统
- **分析师团队**: 市场分析师、基本面分析师、新闻分析师、社交媒体分析师
- **研究团队**: 看涨研究员、看跌研究员、交易决策员
- **管理层**: 风险管理员、研究主管
- **架构核心**: `tradingagents/graph/trading_graph.py` 中的 `TradingAgentsGraph` 类

### 数据流架构
- **数据源管理**: `tradingagents/dataflows/data_source_manager.py`
- **统一接口**: `tradingagents/dataflows/interface.py`
- **缓存系统**: Redis + MongoDB 多层缓存
- **智能降级**: API → 缓存 → 本地文件的多层数据源

### LLM适配器架构
- **统一接口**: `tradingagents/llm_adapters/openai_compatible_base.py`
- **支持提供商**: DashScope、DeepSeek、Google AI、OpenRouter、原生OpenAI、百度千帆
- **适配器模式**: 所有LLM提供商使用统一的OpenAI兼容接口

## 开发命令

### 安装和依赖管理
```bash
# 推荐安装方式（使用pyproject.toml）
pip install -e .

# 或使用requirements.txt（已弃用，仅作参考）
pip install -r requirements.txt
```

### 本地开发启动
```bash
# 启动Web界面
python start_web.py

# 或直接使用Streamlit
streamlit run web/app.py

# 命令行测试
python main.py
```

### Docker开发
```bash
# 构建并启动所有服务
docker-compose up -d --build

# 仅启动数据库服务
docker-compose up -d mongodb redis

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f web
```

### 测试和验证
```bash
# 运行特定测试
python tests/test_dashscope_integration.py

# 验证系统状态
python scripts/validation/check_system_status.py

# 检查依赖
python scripts/validation/check_dependencies.py
```

## 配置管理

### 环境变量配置
- **主配置文件**: `.env` (基于 `.env.example`)
- **必需API密钥**:
  - `DASHSCOPE_API_KEY`: 阿里百炼API密钥
  - `FINNHUB_API_KEY`: 金融数据API密钥
  - `TUSHARE_TOKEN`: A股数据API密钥（推荐）
- **可选API密钥**:
  - `GOOGLE_API_KEY`: Google AI
  - `DEEPSEEK_API_KEY`: DeepSeek
  - `OPENAI_API_KEY`: OpenAI

### 数据库配置
- **MongoDB**: 数据持久化存储
- **Redis**: 高速缓存
- **配置位置**: `tradingagents/config/database_config.py`
- **管理界面**:
  - MongoDB Express: http://localhost:8082
  - Redis Commander: http://localhost:8081

## 核心组件

### Web界面架构
- **主应用**: `web/app.py`
- **组件系统**: `web/components/` 目录
- **工具模块**: `web/utils/` 目录
- **认证系统**: `web/utils/auth_manager.py`

### 智能体系统
- **分析师**: `tradingagents/agents/analysts/`
- **研究员**: `tradingagents/agents/researchers/`
- **交易员**: `tradingagents/agents/trader/`
- **风险管理**: `tradingagents/agents/risk_mgmt/`

### 数据流系统
- **数据源**: `tradingagents/dataflows/` 目录
- **统一工具**: `tradingagents/tools/unified_news_tool.py`
- **新闻过滤**: `tradingagents/utils/enhanced_news_filter.py`

## 开发注意事项

### 代码风格
- 使用中文注释和文档
- 遵循Python PEP 8规范
- 使用类型注解
- 统一的日志系统：`tradingagents/utils/logging_manager.py`

### 扩展开发
- 新增LLM提供商：继承 `openai_compatible_base.py`
- 新增数据源：实现 `dataflows/interface.py` 接口
- 新增智能体：在 `agents/` 对应目录添加

### 调试技巧
- 启用调试模式：设置 `DEBUG_MODE=true` 环境变量
- 查看详细日志：`logs/tradingagents.log`
- 使用测试脚本：`tests/` 目录下的测试文件

## 部署说明

### 生产部署
- 推荐使用Docker部署
- 配置反向代理（如Nginx）
- 设置适当的资源限制
- 定期备份数据库

### 性能优化
- 启用Redis缓存
- 配置MongoDB索引
- 使用CDN加速静态资源
- 监控API调用频率

## 故障排除

### 常见问题
- **Windows 10 ChromaDB兼容性问题**: 设置 `MEMORY_ENABLED=false`
- **API密钥配置错误**: 检查 `.env` 文件格式
- **数据库连接失败**: 验证MongoDB和Redis服务状态
- **内存泄漏**: 使用 `scripts/maintenance/cleanup_cache.py` 清理缓存

### 调试工具
- 系统状态检查：`scripts/validation/check_system_status.py`
- 日志分析：`scripts/log_analyzer.py`
- 缓存清理：`scripts/maintenance/cleanup_cache.py`

## 版本管理

- 使用语义化版本号
- 主要版本在 `pyproject.toml` 中定义
- 详细更新日志在 `docs/releases/CHANGELOG.md`

## 贡献指南

- 遵循现有的代码架构和风格
- 添加适当的测试用例
- 更新相关文档
- 使用描述性的提交信息