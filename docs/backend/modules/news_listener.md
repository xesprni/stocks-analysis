# news_listener 模块

## 1. 模块职责

定时或手动执行“新闻命中 + 价格异动”监听，生成告警并可调用分析模型补充摘要。

## 2. 核心文件

- `market_reporter/modules/news_listener/service.py`
- `market_reporter/modules/news_listener/matcher.py`
- `market_reporter/modules/news_listener/scheduler.py`
- `market_reporter/modules/news_listener/schemas.py`

## 3. 执行流程

1. 读取启用 watchlist。
2. 拉取新闻（`NewsService.collect`）。
3. `find_symbol_news_matches` 做标题关键词匹配。
4. 拉取曲线/报价，计算窗口涨跌幅（`calculate_window_change_percent`）。
5. 超阈值生成 `MatchedAlertCandidate`，评估严重度。
6. 调用 `AnalysisService.analyze_news_alert_batch`（可降级）。
7. 持久化 run 与 alerts 到 DB。

## 4. 调度机制

- `NewsListenerScheduler` 基于 APScheduler。
- 间隔由 `config.news_listener.interval_minutes` 控制。
- `max_instances=1 + coalesce` 防止积压并发。

## 5. 数据落库

- 运行记录：`news_listener_runs`
- 告警记录：`watchlist_news_alerts`

告警状态：`UNREAD/READ/DISMISSED`。

## 6. 降级策略

- 监听过程错误不影响调度器存活。
- 分析模型失败时写入规则降级摘要（非空 markdown）。
- 历史 malformed JSON 告警读取时自动回退为空对象。

## 7. 关键配置

- `move_window_minutes`
- `move_threshold_percent`
- `max_news_per_cycle`
- `analysis_provider` / `analysis_model`
