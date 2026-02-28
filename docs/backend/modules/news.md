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

## 8. 配置示例

### 8.1 默认配置（`config/settings.yaml`）

```yaml
modules:
  news:
    providers:
      - id: rss
        enabled: true
```

### 8.2 RSS 源配置示例

```yaml
# 在 news_sources 表中添加的 RSS 源
- name: "财联社"
  url: "https://www.cls.cn/rss"
  source_type: "rss"
  enabled: true
  priority: 10

- name: "华尔街见闻"
  url: "https://wallstreetcn.com/rss"
  source_type: "rss"
  enabled: true
  priority: 8

- name: "Reuters"
  url: "https://www.reutersagency.com/feed/?best-topics=finance"
  source_type: "rss"
  enabled: true
  priority: 5
```

### 8.3 API 使用示例

#### 添加 RSS 源

```bash
curl -X POST http://localhost:8000/api/news-sources \
  -H "Content-Type: application/json" \
  -d '{
    "name": "财联社",
    "url": "https://www.cls.cn/rss",
    "enabled": true,
    "priority": 10
  }'
```

#### 获取新闻流

```bash
curl -X GET "http://localhost:8000/api/news-feed?limit=20"
```

#### 获取特定来源的新闻

```bash
curl -X GET "http://localhost:8000/api/news-feed?source_id=1"
```

## 9. 新闻格式说明

### 9.1 RSS 源解析字段

| 字段 | 说明 | 示例 |
|------|------|------|
| `title` | 新闻标题 | "苹果发布新款 iPhone" |
| `link` | 新闻链接 | "https://example.com/news/1" |
| `published` | 发布时间 | "2024-01-15T10:30:00Z" |
| `content` | 新闻内容摘要 | "苹果公司今日发布了..." |
| `source_name` | 新闻源名称 | "财联社" |

### 9.2 输出格式（`NewsItem`）

```json
{
  "id": "abc123",
  "title": "Apple announces new product",
  "link": "https://example.com/news/1",
  "source_name": "Reuters",
  "published": "2024-01-15T10:30:00Z",
  "summary": "Apple Inc. announced..."
}
```

### 9.3 输出格式（`NewsFeedItem`）

```json
{
  "id": "abc123",
  "title": "Apple announces new product",
  "link": "https://example.com/news/1",
  "source_name": "Reuters",
  "published": "2024-01-15T10:30:00Z",
  "summary": "Apple Inc. announced...",
  "age_minutes": 45
}
```

## 10. 失败处理策略

- 单个 RSS 源解析失败：记录 warning，继续处理其他源
- RSS 源网络超时：重试 2 次，失败后标记为不可用
- RSS 源返回非 XML 内容：记录 warning，跳过该源
- 持续失败的源：API 层自动禁用（3次连续失败）
- 无可用源：返回空列表，不报错
