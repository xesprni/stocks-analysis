# watchlist 模块

## 1. 模块职责

维护用户关注标的列表，提供新增、更新、删除、启用/禁用与关键词维护能力。

## 2. 核心文件

- `market_reporter/modules/watchlist/schemas.py`
- `market_reporter/modules/watchlist/service.py`
- `market_reporter/infra/db/repos.py`（`WatchlistRepo`）

## 3. 数据模型

- 请求：`WatchlistCreateRequest`、`WatchlistUpdateRequest`
- 响应：`WatchlistItem`
- DB 表：`watchlist_items`

字段重点：

- `symbol + market` 唯一约束
- `display_name` 与 `keywords_json` 支持监听模块关键词匹配

## 4. 关键逻辑

- `add_item`：
  - 市场白名单校验（来自 `config.watchlist.default_market_scope`）
  - symbol 规范化（`normalize_symbol`）
  - DB 预查重 + 约束异常兜底
- `update_item`：支持 alias、enabled、display_name、keywords 更新
- `list_enabled_items`：供 news_listener 只读取启用标的

## 5. 与其他模块关系

- 被 `dashboard` 用于监控列表。
- 被 `news_listener` 用于“标的-新闻关键词”匹配。
- 被 API 路由 `/api/watchlist*` 暴露。

## 6. 失败与兼容策略

- 关键词 JSON 反序列化失败时返回空列表，避免列表接口崩溃。
- 重复标的返回明确 ValidationError。

## 7. 配置示例

### 7.1 默认配置（`config/settings.yaml`）

```yaml
watchlist:
  default_market_scope:
    - CN
    - HK
    - US
```

### 7.2 API 使用示例

#### 添加 watchlist 项目

```bash
curl -X POST http://localhost:8000/api/watchlist \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "market": "US",
    "display_name": "Apple Inc.",
    "alias": "苹果",
    "keywords": ["苹果", "iPhone", "iOS"],
    "enabled": true
  }'
```

#### 更新 watchlist 项目

```bash
curl -X PATCH http://localhost:8000/api/watchlist/1 \
  -H "Content-Type: application/json" \
  -d '{
    "alias": "苹果公司",
    "keywords": ["苹果", "iPhone", "iOS", "Apple"],
    "enabled": true
  }'
```

#### 获取启用的 watchlist 项目

```bash
curl -X GET "http://localhost:8000/api/watchlist?enabled_only=true"
```

## 8. 使用场景

### 8.1 个股监控

- 用户添加关注的股票到 watchlist
- Dashboard 实时显示这些股票的行情
- 新闻监听模块监控这些股票的关联新闻

### 8.2 新闻匹配

- 为 watchlist 项目设置关键词（如 "苹果"、"iPhone"）
- news_listener 模块在新闻标题中匹配这些关键词
- 生成告警时关联到对应的 watchlist 项目

### 8.3 自动化策略

- 通过 API 批量导入 watchlist 项目
- 结合定时任务自动更新关键词
- 根据市场表现自动启用/禁用 watchlist 项目
