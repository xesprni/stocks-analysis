# news 模块

## 1. 模块职责

提供新闻采集与新闻流聚合能力，当前默认 provider 为 RSS。

## 2. 核心文件

- `market_reporter/modules/news/service.py`
- `market_reporter/modules/news/providers/rss_provider.py`
- `market_reporter/modules/news/schemas.py`

## 3. Provider 架构

- 模块名：`news`
- 当前注册 provider：`rss`
- `NewsService.collect`：用于分析/监听链路
- `NewsService.collect_feed`：用于前端 News Feed 页面

## 4. RSS provider 行为

- 并发抓取所有启用 news source。
- 解析 `title/link/published/content`。
- 按 `title + link` 去重。
- 单源失败转 warning，不阻断整体返回。

## 5. 新闻源来源

- 优先使用注入的 `news_sources`。
- 未注入时从 DB `news_sources` 表读取（兼容旧调用链）。

## 6. 模块输出

- 结构化新闻实体：`NewsItem`
- feed 展示实体：`NewsFeedItem`
- 附带 warning 列表，供上层 UI/任务记录。

## 7. 与 API 关系

- `/api/news-feed`：读取聚合结果。
- `/api/news-sources`：管理 source 元数据（表 `news_sources`）。
- 新闻源长期失败可由 API 层自动禁用。
