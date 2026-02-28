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

## 8. 配置示例

### 8.1 完整配置（`config/settings.yaml`）

```yaml
modules:
  news_listener:
    enabled: true
    interval_minutes: 30
    move_window_minutes: 60
    move_threshold_percent: 2.0
    max_news_per_cycle: 100
    analysis_provider: openai_compatible
    analysis_model: gpt-4
```

### 8.2 配置项说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | `true` | 是否启用定时监听 |
| `interval_minutes` | `30` | 监听间隔（分钟） |
| `move_window_minutes` | `60` | 价格变动计算窗口（分钟） |
| `move_threshold_percent` | `2.0` | 触发告警的价格变动阈值（%） |
| `max_news_per_cycle` | `100` | 每轮最大处理新闻数 |
| `analysis_provider` | `mock` | 分析模型 provider |
| `analysis_model` | - | 分析模型名称 |

## 9. 匹配规则说明

### 9.1 关键词匹配流程

```text
1. 遍历所有启用的 watchlist 项目
2. 获取每个项目的关键词列表（keywords_json）
3. 在新闻标题中搜索关键词（不区分大小写）
4. 记录匹配的关键词列表
5. 计算匹配得分（匹配关键词数量）
```

### 9.2 匹配规则示例

| watchlist 项目 | 关键词 | 新闻标题 | 匹配结果 |
|---------------|--------|---------|---------|
| AAPL | ["苹果", "iPhone", "Apple"] | "苹果发布新款 iPhone" | 匹配：苹果, iPhone |
| TSLA | ["特斯拉", "Tesla", "马斯克"] | "特斯拉股价大涨" | 匹配：特斯拉 |
| 0700 | ["腾讯", "微信", "QQ"] | "阿里巴巴财报发布" | 不匹配 |

### 9.3 价格异动计算

```python
def calculate_window_change_percent(curve_points, window_minutes):
    """
    计算指定时间窗口内的价格变动百分比
    
    Args:
        curve_points: 分时曲线数据点列表
        window_minutes: 时间窗口（分钟）
    
    Returns:
        变动百分比（正数表示上涨，负数表示下跌）
    """
    # 取窗口起始价格和当前价格
    start_price = curve_points[-window_minutes].price
    end_price = curve_points[-1].price
    return (end_price - start_price) / start_price * 100
```

### 9.4 严重度评估规则

| 条件 | 严重度 |
|------|--------|
| 价格变动 >= 5% 或 匹配关键词 >= 3 | `high` |
| 价格变动 >= 3% 或 匹配关键词 >= 2 | `medium` |
| 其他匹配情况 | `low` |

## 10. API 使用示例

### 10.1 手动触发监听

```bash
curl -X POST http://localhost:8000/api/news-listener/run
```

### 10.2 获取监听历史

```bash
curl -X GET "http://localhost:8000/api/news-listener/runs?limit=10"
```

### 10.3 获取告警列表

```bash
# 获取未读告警
curl -X GET "http://localhost:8000/api/news-alerts?status=UNREAD"

# 获取高严重度告警
curl -X GET "http://localhost:8000/api/news-alerts?severity=high"
```

### 10.4 更新告警状态

```bash
# 标记已读
curl -X PATCH http://localhost:8000/api/news-alerts/1 \
  -H "Content-Type: application/json" \
  -d '{"status": "READ"}'

# 批量标记已读
curl -X POST http://localhost:8000/api/news-alerts/mark-all-read
```

## 11. 告警输出格式

```json
{
  "id": 1,
  "run_id": "20240115_103000",
  "symbol": "AAPL",
  "market": "US",
  "display_name": "Apple Inc.",
  "severity": "high",
  "matched_keywords": ["苹果", "iPhone"],
  "price_change_percent": 3.5,
  "news_title": "苹果发布新款 iPhone，股价大涨",
  "news_link": "https://example.com/news/1",
  "news_published": "2024-01-15T10:30:00Z",
  "analysis_summary": "正面利好消息，新产品发布通常带动股价上涨...",
  "analysis_markdown": "## 分析摘要\n\n苹果公司发布新款 iPhone...",
  "status": "UNREAD",
  "created_at": "2024-01-15T10:35:00Z"
}
```

## 12. 调度器管理

### 12.1 启动/停止调度器

```python
# 通过配置 API 动态控制
PUT /api/config
{
  "news_listener": {
    "enabled": false  # 停止调度器
  }
}
```

### 12.2 调度器状态

- 运行中：定时任务按间隔执行
- 已停止：不执行定时任务，但可手动触发
- 单实例：同一时刻只有一个监听任务运行
