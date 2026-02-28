# Market Reporter Pro 项目学习指南

## 1. 项目概述

Market Reporter Pro 是一个金融数据分析系统，整合了全球股市行情、新闻事件、资金流数据和AI分析能力，为用户提供智能投资决策支持。系统采用模块化架构，核心功能包括：

- 实时股票行情获取（A股、港股、美股）
- 多源新闻采集与智能匹配
- 资金流向分析（北向、南向资金）
- AI驱动的个股深度分析
- 自动化报告生成
- 可视化仪表盘

系统采用前后端分离架构，后端使用FastAPI构建，前端使用React + Tailwind CSS，数据存储使用SQLite数据库，支持通过配置灵活扩展数据源。

## 2. 架构设计

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API Layer                                       │
│  health | config | dashboard | watchlist | stocks | news | reports | analysis│
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Service/Module Layer                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │Dashboard │  │Watchlist │  │ Reports  │  │ Analysis │  │   News   │       │
│  │ Service  │  │ Service  │  │ Service  │  │ Service  │  │ Listener │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
│       │             │             │             │             │              │
│       └─────────────┴──────┬──────┴─────────────┴─────────────┘              │
│                            ▼                                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Market   │  │  News    │  │ FundFlow │  │ Symbol   │  │  Agent   │       │
│  │  Data    │  │ Service  │  │ Service  │  │ Search   │  │ Service  │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
└───────┼─────────────┼─────────────┼─────────────┼─────────────┼─────────────┘
        │             │             │             │             │
        ▼             ▼             ▼             ▼             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Core Layer                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Contracts   │  │    Types     │  │   Registry   │  │    Errors    │     │
│  │ (Protocols)  │  │   (DTOs)     │  │  (Providers) │  │  (Exceptions)│     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Infrastructure Layer                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Database   │  │    HTTP      │  │   Security   │  │   Provider   │     │
│  │  (SQLModel)  │  │   Client     │  │  (AES-GCM)   │  │  Implementations│  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            External Systems                                  │
│  SQLite | RSS Feeds | yfinance | akshare | Longbridge | OpenAI | Codex     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心设计原则

#### 2.2.1 可插拔Provider架构

系统采用Provider模式实现模块的可扩展性：

- 每个业务模块（news, fund_flow, market_data, analysis, symbol_search）定义一个协议接口
- 多个具体实现（Provider）可注册到系统中
- 通过配置文件动态选择默认Provider
- 支持自动回退机制（fallback）

**示例：行情数据模块**
```python
# 协议定义 (core/contracts.py)
class MarketDataProvider(Protocol):
    def get_quote(self, symbol: str, market: str) -> Quote: ...
    def get_kline(self, symbol: str, market: str, interval: str, limit: int) -> List[KLineBar]: ...
    def get_curve(self, symbol: str, market: str, interval: str, limit: int) -> List[CurvePoint]: ...

# 具体实现 (modules/market_data/providers/yfinance_provider.py)
class YFinanceProvider(MarketDataProvider):
    def get_quote(self, symbol: str, market: str) -> Quote:
        # 使用yfinance获取数据
        pass

# 注册到系统 (modules/market_data/service.py)
registry.register("market_data", "yfinance", YFinanceProvider)
```

#### 2.2.2 缓存与降级策略

系统在多个层级实现缓存和降级机制，确保高可用性：

| 模块 | 缓存策略 | 降级策略 |
|------|----------|----------|
| 行情数据 | K线、分时曲线数据持久化到SQLite | provider失败时返回缓存数据，无缓存时返回`source=unavailable` |
| 新闻监听 | 无显式缓存 | 新闻源失败时继续处理其他源，不阻断流程 |
| 分析 | 无显式缓存 | LLM输出失败时生成规则降级摘要 |
| 资金流 | 无显式缓存 | 单个数据源失败时使用其他数据源 |

#### 2.2.3 安全与密钥管理

系统采用多层次安全机制保护敏感信息：

1. **对称加密**：使用AES-GCM（256位）加密API密钥、OAuth令牌
2. **主密钥存储**：优先使用系统Keychain（macOS Keychain），失败时回退到文件存储
3. **密文存储**：数据库中仅存储加密后的密钥，永不存储明文
4. **安全通信**：HTTP客户端统一配置User-Agent和超时

```python
# 加密/解密实现 (infra/security/crypto.py)
class Crypto:
    def encrypt_text(self, text: str) -> str:
        # 生成随机nonce
        # 使用AES-GCM加密
        # 返回 base64(ciphertext) + base64(nonce)
        pass
    
    def decrypt_text(self, encrypted_text: str) -> str:
        # 解析base64编码的ciphertext和nonce
        # 使用AES-GCM解密
        pass

# 密钥存储 (infra/security/keychain_store.py)
class KeychainStore:
    def get_master_key(self) -> str:
        # 1. 检查配置的主密钥文件
        # 2. 尝试从系统Keychain获取
        # 3. 回退到主密钥文件
        pass
```

#### 2.2.4 任务异步处理

系统采用内存任务管理器处理耗时操作，避免阻塞HTTP请求：

- 报告生成：`ReportService._tasks` 字典管理异步任务
- 个股分析：`StockAnalysisTaskManager._tasks` 管理异步分析任务
- 任务状态：`PENDING/RUNNING/SUCCEEDED/FAILED`
- 前端轮询：通过`/api/reports/tasks/{task_id}`查询任务状态

```python
class ReportTaskManager:
    _tasks: Dict[str, ReportRunTaskView] = {}
    
    def add_task(self, task: ReportRunTaskView) -> None:
        # 添加任务到内存
        # 超过限制时清理最旧的任务
        pass
    
    def get_task(self, task_id: str) -> Optional[ReportRunTaskView]:
        # 获取任务状态
        pass
```

## 3. 核心模块详解

### 3.1 数据模型（core/types.py）

系统定义了一套统一的数据模型，确保模块间数据交换的一致性：

```python
# 行情数据
class Quote(BaseModel):
    symbol: str
    market: str
    price: float
    change: float
    change_percent: float
    volume: float
    source: str
    timestamp: str

# K线数据
class KLineBar(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float

# 分时曲线数据
class CurvePoint(BaseModel):
    time: str
    price: float
    volume: Optional[float]

# 新闻数据
class NewsItem(BaseModel):
    id: str
    title: str
    link: str
    source_name: str
    published: str
    summary: str

# 资金流数据
class FlowPoint(BaseModel):
    date: str
    value: float
    series_id: str
    series_name: str
    source: str

# 分析输入输出
class AnalysisInput(BaseModel):
    symbol: str
    market: str
    context: Dict[str, Any]
    prompt: str

class AnalysisOutput(BaseModel):
    markdown: str
    summary: str
    confidence: float
    data_sources: List[str]
```

### 3.2 Provider注册器（core/registry.py）

系统通过注册器实现模块的解耦：

```python
class ProviderRegistry:
    _registry: Dict[str, Dict[str, Callable]] = {}
    
    def register(self, module: str, provider_id: str, factory: Callable) -> None:
        """注册Provider工厂函数"""
        if module not in self._registry:
            self._registry[module] = {}
        self._registry[module][provider_id] = factory
    
    def resolve(self, module: str, provider_id: str, **kwargs) -> Any:
        """根据模块和ID创建Provider实例"""
        if module not in self._registry:
            raise ProviderNotFoundError(f"Module {module} not registered")
        
        if provider_id not in self._registry[module]:
            raise ProviderNotFoundError(f"Provider {provider_id} not found in {module}")
        
        return self._registry[module][provider_id](**kwargs)
    
    def list_ids(self, module: str) -> List[str]:
        """列出指定模块的所有Provider ID"""
        if module not in self._registry:
            return []
        return list(self._registry[module].keys())
```

### 3.3 配置系统（config.py + config_store.py）

系统采用YAML配置文件 + 运行时配置管理：

#### 3.3.1 配置模型定义（config.py）

```python
class AppConfig(BaseModel):
    # 基础配置
    output_root: str = "output"
    timezone: str = "Asia/Shanghai"
    
    # 数据库配置
    database: DatabaseConfig = DatabaseConfig()
    
    # 模块配置
    modules: ModulesConfig = ModulesConfig()
    
    # 分析配置
    analysis: AnalysisConfig = AnalysisConfig()
    
    # Watchlist配置
    watchlist: WatchlistConfig = WatchlistConfig()
    
    # Dashboard配置
    dashboard: DashboardConfig = DashboardConfig()
    
    # Agent配置
    agent: AgentConfig = AgentConfig()

# 模块配置子类
class ModulesConfig(BaseModel):
    news: NewsConfig = NewsConfig()
    fund_flow: FundFlowConfig = FundFlowConfig()
    market_data: MarketDataConfig = MarketDataConfig()
    news_listener: NewsListenerConfig = NewsListenerConfig()
    symbol_search: SymbolSearchConfig = SymbolSearchConfig()
```

#### 3.3.2 配置存储服务（services/config_store.py）

```python
class ConfigStore:
    def __init__(self, config_file: str = "config/settings.yaml"):
        self.config_file = config_file
        self.config = self.load()
    
    def load(self) -> AppConfig:
        """加载配置文件，不存在时创建默认配置"""
        if not os.path.exists(self.config_file):
            config = self._create_default_config()
            self.save(config)
            return config
        
        with open(self.config_file, "r") as f:
            data = yaml.safe_load(f)
        
        return AppConfig(**data)
    
    def save(self, config: AppConfig) -> None:
        """标准化并保存配置"""
        # 规范化路径
        config.output_root = os.path.abspath(config.output_root)
        
        # 规范化provider列表
        config.modules.market_data.providers = self._normalize_providers(
            config.modules.market_data.providers
        )
        
        # 创建输出目录
        os.makedirs(config.output_root, exist_ok=True)
        
        with open(self.config_file, "w") as f:
            yaml.dump(config.dict(), f, default_flow_style=False)
    
    def patch(self, patch_data: Dict[str, Any]) -> None:
        """浅层合并配置并保存"""
        # 深度合并配置
        self.config = self._deep_merge(self.config.dict(), patch_data)
        self.save(self.config)
        
        # 特殊处理：更新新闻监听调度器
        if "news_listener" in patch_data:
            self._update_news_listener_scheduler()
```

### 3.4 数据库层（infra/db）

系统使用SQLModel（基于SQLAlchemy）作为ORM，采用启动时自动迁移策略：

#### 3.4.1 数据库模型（infra/db/models.py）

```python
# Watchlist表
class WatchlistItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    market: str = Field(index=True)
    display_name: Optional[str] = None
    alias: Optional[str] = None
    keywords_json: Optional[str] = None  # JSON数组格式
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    __table_args__ = (UniqueConstraint("symbol", "market"),)

# K线缓存表
class StockKLineBar(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    market: str = Field(index=True)
    interval: str = Field(index=True)  # 1d, 1h, 5m, 1m
    time: datetime = Field(index=True)
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    __table_args__ = (UniqueConstraint("symbol", "market", "interval", "time"),)

# 分析Provider密钥表
class AnalysisProviderSecret(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    provider_id: str = Field(unique=True)
    encrypted_api_key: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

#### 3.4.2 数据库会话管理（infra/db/session.py）

```python
def init_db(url: str) -> None:
    """初始化数据库，创建表并自动补列"""
    engine = get_engine(url)
    SQLModel.metadata.create_all(engine)
    
    # SQLite兼容：自动补列
    with Session(engine) as session:
        _add_missing_columns(session, "stock_analysis_runs", ["skill_id"])
        _add_missing_columns(session, "watchlist_news_alerts", ["analysis_markdown"])

def _add_missing_columns(session: Session, table_name: str, columns: List[str]) -> None:
    """为现有表添加缺失的列（SQLite兼容）"""
    # 查询现有列
    result = session.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row[1] for row in result.fetchall()}
    
    # 添加缺失的列
    for column in columns:
        if column not in existing_columns:
            session.execute(f"ALTER TABLE {table_name} ADD COLUMN {column} TEXT")
    session.commit()
```

### 3.5 Agent系统（modules/analysis/agent）

Agent系统是项目的核心智能模块，采用工具调用+护栏校验的架构：

#### 3.5.1 工具集合（modules/analysis/agent/tools）

```python
# 工具定义示例
class GetPriceHistoryTool:
    name = "get_price_history"
    description = "获取股票历史价格数据"
    
    @staticmethod
    def schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码"},
                "market": {"type": "string", "enum": ["CN", "HK", "US"]},
                "interval": {"type": "string", "enum": ["1d", "1h", "5m", "1m"]},
                "lookback": {"type": "integer", "description": "回溯天数"}
            },
            "required": ["symbol", "market"]
        }
    
    @staticmethod
    async def execute(symbol: str, market: str, interval: str = "1d", lookback: int = 365) -> Dict[str, Any]:
        """执行工具"""
        # 调用MarketDataService获取数据
        bars = await market_data_service.get_kline(symbol, market, interval, lookback)
        
        return {
            "bars": bars,
            "source": "yfinance",
            "as_of": datetime.utcnow().isoformat()
        }

# 工具注册
class ToolRegistry:
    _tools: Dict[str, Type[BaseTool]] = {}
    
    @classmethod
    def register(cls, tool_class: Type[BaseTool]) -> None:
        cls._tools[tool_class.name] = tool_class
    
    @classmethod
    def get(cls, name: str) -> Type[BaseTool]:
        if name not in cls._tools:
            raise ToolNotFoundError(f"Tool {name} not found")
        return cls._tools[name]
    
    @classmethod
    def list_all(cls) -> List[str]:
        return list(cls._tools.keys())
```

#### 3.5.2 运行时策略（modules/analysis/agent/runtime）

系统支持两种运行时策略：

1. **OpenAI Tools API**：使用OpenAI的工具调用API循环执行
2. **Action-JSON协议**：要求模型输出结构化JSON（call_tool/final）

```python
class OpenAIToolRuntime:
    def __init__(self, model: str, tools: List[Dict[str, Any]], max_iterations: int = 10):
        self.model = model
        self.tools = tools
        self.max_iterations = max_iterations
    
    async def run(self, messages: List[Dict[str, str]]) -> RuntimeDraft:
        """使用OpenAI Tools API运行"""
        for iteration in range(self.max_iterations):
            # 调用OpenAI API
            response = await openai.ChatCompletion.create(
                model=self.model,
                messages=messages,
                tools=self.tools,
                tool_choice="auto"
            )
            
            message = response.choices[0].message
            
            # 检查是否需要调用工具
            if message.tool_calls:
                # 执行工具
                tool_results = []
                for tool_call in message.tool_calls:
                    tool = ToolRegistry.get(tool_call.function.name)
                    args = json.loads(tool_call.function.arguments)
                    result = await tool.execute(**args)
                    tool_results.append({
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "result": result
                    })
                    
                # 将工具结果添加到消息
                messages.append(message)
                messages.extend([
                    {"role": "tool", "tool_call_id": r["tool_call_id"], "name": r["name"], "content": json.dumps(r["result"])}
                    for r in tool_results
                ])
            else:
                # 模型完成，返回结果
                return RuntimeDraft(
                    content=message.content,
                    confidence=1.0,
                    tool_calls=[tool_call.dict() for tool_call in message.tool_calls]
                )
        
        # 达到最大迭代次数，返回降级结果
        return RuntimeDraft(
            content="分析任务超时，返回默认结果",
            confidence=0.5
        )
```

#### 3.5.3 护栏校验（modules/analysis/agent/guardrails.py）

```python
class AgentGuardrails:
    def __init__(self, config: AgentConfig):
        self.config = config
    
    def validate(self, draft: RuntimeDraft, tool_calls: List[ToolCall]) -> GuardrailResult:
        """校验分析结果"""
        warnings = []
        confidence_adjustment = 0
        
        # 证据完整性检查
        if self.config.guardrails.evidence_required and not self._has_evidence_markers(draft.content):
            warnings.append("结论缺少证据标记 [E*]")
            confidence_adjustment -= 20
        
        # PE一致性校验
        if self.config.guardrails.pe_consistency_check:
            pe_consistency = self._check_pe_consistency(tool_calls)
            if not pe_consistency:
                warnings.append("基本面PE与计算PE不一致")
                confidence_adjustment -= 10
        
        # 数据时效性检查
        if not self._check_data_freshness(tool_calls):
            warnings.append("部分数据超过24小时")
            confidence_adjustment -= 5
        
        # 来源多样性检查
        if not self._check_source_diversity(tool_calls):
            warnings.append("数据来源不够多样")
            confidence_adjustment -= 5
        
        return GuardrailResult(
            passed=confidence_adjustment >= -30,
            warnings=warnings,
            confidence_adjustment=confidence_adjustment
        )
    
    def _has_evidence_markers(self, content: str) -> bool:
        """检查是否有证据标记 [E*]"""
        return re.search(r"\[E\d+\]", content) is not None
    
    def _check_pe_consistency(self, tool_calls: List[ToolCall]) -> bool:
        """检查PE一致性"""
        # 从工具调用中提取基本面PE和计算PE
        # 比较是否在10%误差范围内
        pass
```

## 4. 代码风格与最佳实践

### 4.1 异步编程

系统大量使用异步编程提高性能：

- 使用`asyncio.gather`并发执行多个HTTP请求
- 使用`async/await`处理I/O密集型操作
- 避免在异步函数中使用同步阻塞调用

```python
# 正确示例：并发获取多个股票报价
async def get_multiple_quotes(symbols: List[str], market: str) -> List[Quote]:
    tasks = [
        market_data_service.get_quote(symbol, market)
        for symbol in symbols
    ]
    return await asyncio.gather(*tasks)

# 错误示例：串行执行（性能差）
async def get_multiple_quotes_wrong(symbols: List[str], market: str) -> List[Quote]:
    quotes = []
    for symbol in symbols:
        quote = await market_data_service.get_quote(symbol, market)
        quotes.append(quote)
    return quotes
```

### 4.2 错误处理

系统采用分层错误处理：

```python
# 核心异常定义（core/errors.py）
class MarketReporterError(Exception):
    """所有自定义异常的基类"""
    pass

class ProviderNotFoundError(MarketReporterError):
    """Provider未找到"""
    pass

class ProviderExecutionError(MarketReporterError):
    """Provider执行失败"""
    pass

class SecretStorageError(MarketReporterError):
    """密钥存储错误"""
    pass

# API错误处理（api/errors.py）
class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail

# 全局异常处理器（main.py）
@app.exception_handler(MarketReporterError)
async def market_reporter_exception_handler(request: Request, exc: MarketReporterError):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)}
    )

@app.exception_handler(ProviderNotFoundError)
async def provider_not_found_handler(request: Request, exc: ProviderNotFoundError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)}
    )
```

### 4.3 配置管理

系统采用"配置即代码"原则：

- 所有配置通过YAML文件管理
- 支持运行时热更新
- 配置变更自动触发相关服务重启
- 配置项有明确的默认值

```yaml
# config/settings.yaml 示例
analysis:
  default_provider: openai_compatible
  default_model: gpt-4
  providers:
    - id: mock
      enabled: true
      auth_mode: none
    - id: openai_compatible
      enabled: true
      auth_mode: api_key
      base_url: https://api.openai.com/v1
      models:
        - gpt-4
        - gpt-3.5-turbo
    - id: codex_app_server
      enabled: false
      auth_mode: chatgpt_oauth
      base_url: http://localhost:8080

# 代码中安全地访问配置
config = ConfigStore().config
provider_config = config.analysis.providers[0]
api_key = config.analysis.providers[1].api_key  # 会自动解密
```

## 5. 启动与运行

### 5.1 本地开发环境搭建

```bash
# 1. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate  # Windows

# 2. 安装依赖
pip install -e .

# 3. 安装前端依赖
cd frontend
npm install

# 4. 启动后端
python -m market_reporter

# 5. 启动前端
npm run dev
```

### 5.2 Docker部署

```bash
# 构建镜像
docker build -t market-reporter .

# 运行容器
docker run -p 8000:8000 \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/output:/app/output \
  market-reporter
```

### 5.3 环境变量配置

```bash
# 设置配置文件路径
export MARKET_REPORTER_CONFIG_FILE=/path/to/config.yaml

# 设置API端口
export MARKET_REPORTER_API_PORT=3000

# 使用文件存储主密钥（跳过Keychain）
export MARKET_REPORTER_MASTER_KEY_FILE=/secure/path/master.key

# 启动服务
python -m market_reporter
```

## 6. 调试与测试

### 6.1 测试框架

系统使用pytest进行单元测试，测试覆盖率高：

```bash
# 运行所有测试
pytest tests/

# 运行特定测试文件
pytest tests/test_analysis_provider_status.py -v

# 运行带覆盖率的测试
pytest tests/ --cov=market_reporter --cov-report=html
```

### 6.2 API调试

使用curl或Postman调试API：

```bash
# 获取健康状态
curl http://localhost:8000/api/health

# 获取配置
curl http://localhost:8000/api/config

# 获取市场快照
curl http://localhost:8000/api/dashboard/snapshot

# 运行个股分析
curl -X POST http://localhost:8000/api/analysis/stocks/AAPL/run \
  -H "Content-Type: application/json" \
  -d '{"provider_id": "openai_compatible", "model": "gpt-4"}'
```

### 6.3 日志查看

系统使用Rich库输出结构化日志：

```python
# 日志输出示例
from rich.console import Console
console = Console()

console.log(f"[green]成功获取AAPL行情数据")
console.log(f"[yellow]警告：yfinance数据源超时，使用缓存")
console.log(f"[red]错误：无法连接到OpenAI API")
```

## 7. 扩展与定制

### 7.1 添加新的数据源

要添加新的Provider，遵循以下步骤：

1. **定义协议**：在`core/contracts.py`中定义新的协议接口
2. **实现Provider**：在`modules/*/providers/`中创建新的Provider类
3. **注册Provider**：在`modules/*/service.py`中注册Provider
4. **更新配置**：在`config/settings.yaml`中添加Provider配置
5. **编写测试**：在`tests/`中添加单元测试

### 7.2 自定义分析模型

要使用新的AI模型，可以：

1. **修改配置**：在`config/settings.yaml`中添加新的模型
2. **创建新Provider**：如果需要特殊处理，创建新的分析Provider
3. **调整Prompt**：在`analysis/prompt_builder.py`中调整提示词模板

### 7.3 增加新的报告类型

要添加新的报告类型，遵循以下步骤：

1. **创建Skill**：在`modules/reports/skills.py`中创建新的报告技能
2. **实现Renderer**：在`modules/reports/renderer.py`中实现报告渲染逻辑
3. **更新配置**：在`config/settings.yaml`中配置新报告的默认设置
4. **添加API端点**：在`api/reports.py`中添加新报告的API端点

## 8. 总结

Market Reporter Pro是一个设计精良、架构清晰的金融数据分析系统，其核心优势在于：

1. **模块化设计**：通过Provider模式实现高度可扩展
2. **智能分析**：Agent系统结合工具调用和护栏校验，提供高质量分析
3. **高可用性**：完善的缓存和降级策略确保系统稳定
4. **安全可靠**：多层次密钥管理保障数据安全
5. **易用性**：清晰的API和配置系统便于使用和维护

通过本指南，您应该能够全面理解系统的架构和实现细节。建议从阅读`core/`和`modules/`目录开始，逐步深入理解各个模块的实现原理。