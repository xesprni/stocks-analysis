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
