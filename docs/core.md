# Core — 核心抽象层

`market_reporter/core/` 定义了整个系统的公共类型、接口协议、Provider 注册机制和共享工具函数。所有上层模块（market_data、news、analysis 等）都依赖此层。

## 代码结构

```
core/
├── contracts.py    # 5 个 Protocol 接口（Provider 契约）
├── types.py        # Pydantic 数据模型（Quote, KLineBar, NewsItem 等）
├── registry.py     # ProviderRegistry（模块 → provider_id → 工厂函数）
├── errors.py       # 异常层级
└── utils.py        # JSON 解析工具
```

## Provider 契约（contracts.py）

使用 Python `typing.Protocol` 定义 5 类数据提供者接口，所有 Provider 实现者只需满足方法签名即可，无需显式继承。

```python
class NewsProvider(Protocol):
    provider_id: str
    async def collect(self, limit: int) -> List[NewsItem]: ...

class FundFlowProvider(Protocol):
    provider_id: str
    async def collect(self, periods: int) -> Dict[str, List[FlowPoint]]: ...

class MarketDataProvider(Protocol):
    provider_id: str
    async def get_quote(self, symbol: str, market: str) -> Quote: ...
    async def get_kline(self, symbol: str, market: str, interval: str, limit: int) -> List[KLineBar]: ...
    async def get_curve(self, symbol: str, market: str, window: str) -> List[CurvePoint]: ...

class AnalysisProvider(Protocol):
    provider_id: str
    async def analyze(self, payload: AnalysisInput, model: str, api_key: Optional[str] = None) -> AnalysisOutput: ...

class SymbolSearchProvider(Protocol):
    provider_id: str
    async def search(self, query: str, market: str, limit: int) -> List[dict]: ...
```

**核心语法**：`Protocol` 是 Python 的结构化子类型机制（PEP 544），任何拥有匹配方法签名的类自动被视为该 Protocol 的实现者。

## 数据模型（types.py）

所有模型继承 `pydantic.BaseModel`，用于跨层数据传输。

| 模型 | 用途 | 关键字段 |
|------|------|----------|
| `NewsItem` | 新闻条目 | source_id, category, source, title, link, published, content |
| `FlowPoint` | 资金流数据点 | market, series_key, series_name, date, value, unit |
| `Quote` | 实时报价 | symbol, market, ts, price, change, change_percent, volume, currency |
| `KLineBar` | K 线数据 | symbol, market, interval, ts, open, high, low, close, volume |
| `CurvePoint` | 分时数据点 | symbol, market, ts, price, volume |
| `AnalysisInput` | 分析引擎输入 | symbol, market, quote, kline, curve, news, fund_flow, watch_meta |
| `AnalysisOutput` | 分析引擎输出 | summary, sentiment, key_levels, risks, action_items, confidence, markdown |

**核心语法**：`Field(default_factory=list)` 用于可变默认值；`Optional[float]` 允许 None；`ge=0.0, le=1.0` 约束 confidence 范围。

## Provider 注册器（registry.py）

```python
class ProviderRegistry:
    def register(self, module: str, provider_id: str, factory: ProviderFactory) -> None
    def resolve(self, module: str, provider_id: str, **kwargs) -> Any
    def has(self, module: str, provider_id: str) -> bool
    def list_ids(self, module: str) -> list[str]
```

使用两级字典存储：`Dict[module, Dict[provider_id, factory]]`。`factory` 是 `Callable[..., Any]` 类型，延迟实例化 Provider。

**核心语法**：`defaultdict(dict)` 自动创建嵌套字典；`TypeVar("T")` 为泛型预留（当前未使用）。

## 异常层级（errors.py）

```
MarketReporterError (基类)
├── ProviderNotFoundError    # provider_id 无法解析
├── ProviderExecutionError   # provider 执行失败
├── SecretStorageError       # 密钥存储不可用
└── ValidationError          # 领域级校验失败
```

## JSON 工具（utils.py）

```python
def parse_json(content: str) -> Optional[Dict[str, Any]]:
```

先尝试 `json.loads`，失败后提取最外层 `{…}` 子串再解析。用于从 LLM 返回的混合文本中恢复 JSON。
