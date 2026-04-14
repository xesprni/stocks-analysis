---
name: watchlist_report
description: 持仓组合报告，逐个分析 watchlist 中的标的，并汇总组合情绪与风险。
mode: watchlist
require_symbol: false
aliases:
  - watchlist
---

# 持仓报告 Skill

## 分析框架

对 watchlist 中的每个持仓标的，执行以下分析：

1. 个股风险评估：从持仓视角分析风险收益、仓位建议与风控要点。
2. 组合汇总：汇总所有标的的情绪、置信度，生成组合级别观点。
3. 风险联动：识别持仓间是否存在风险联动（行业集中、风格集中等）。

## 输出要求

- 每个标的独立出具分析结论。
- 组合层面提供汇总情绪（bullish/neutral/bearish）和平均置信度。
- 标注失败项并提供兜底建议。
- 使用中文输出。
