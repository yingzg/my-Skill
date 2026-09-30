# MCP 入门开发教程

> 面向 Java 程序员的 MCP 协议快速入门指南

## 目录

- [什么是 MCP](#什么是-mcp)
- [核心概念](#核心概念)
- [项目结构](#项目结构)
- [代码详解](#代码详解)
- [通信协议](#通信协议)
- [调试与测试](#调试与测试)
- [部署与使用](#部署与使用)
- [常见问题](#常见问题)

---

## 什么是 MCP

MCP（Model Context Protocol）是一个开放协议，让 AI 模型能够调用本地工具和服务。

### 一句话理解

```
用户提问 → AI 模型判断需要调用工具 → 通过 MCP 调用本地工具 → 返回结果给用户
```

### Java 类比

```java
// MCP 就像是给 AI 写的 REST Controller
@RestController
public class WebSearchController {
    @PostMapping("/tools/web_search")
    public String search(@RequestParam String query) {
        // 调用搜索 API
        return searchResult;
    }
}
```

---

## 核心概念

### 1. Host、Client、Server 三角关系

```
┌─────────────────────────────────────────────────────────────┐
│                        Host（宿主）                          │
│          AI 应用程序（Claude Desktop、Cursor 等）             │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │                  Client（客户端）                     │   │
│   │            MCP SDK 内置，自动创建管理                  │   │
│   │                                                     │   │
│   │   ┌─────────────────────────────────────────┐       │   │
│   │   │              Server（服务器）             │       │   │
│   │   │         提供具体工具（web_search 等）     │       │   │
│   │   └─────────────────────────────────────────┘       │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

| 角色 | 职责 | 类比 Java |
|------|------|-----------|
| **Host** | 管理 AI 应用，协调所有 Client | Spring Boot Application |
| **Client** | 与 Server 通信，发送请求/接收响应 | RestTemplate / FeignClient |
| **Server** | 提供具体工具，处理请求 | REST Controller |

**关键理解**：你只需要配置 Server，Client 由 Host 自动创建和管理。

### 2. 传输方式：stdio vs HTTP

#### stdio（本地工具推荐）

```
┌─────────────┐      stdin/stdout      ┌─────────────┐
│   Client    │ ←───────────────────→  │   Server    │
└─────────────┘     (JSON-RPC 数据)    └─────────────┘
```

- 通过标准输入输出通信
- 每个 Client 独占一个 Server 进程
- 适合本地工具、单用户场景

#### HTTP（网络服务）

```
┌─────────────┐                        ┌─────────────┐
│  Client A   │ ─────────────────────→ │             │
├─────────────┤      HTTP/REST         │   Server    │
│  Client B   │ ─────────────────────→ │             │
├─────────────┤                        │             │
│  Client C   │ ─────────────────────→ │             │
└─────────────┘                        └─────────────┘
```

- 通过 HTTP 请求通信
- 支持多客户端并发
- 适合网络服务、多用户场景

### 3. Python 语法快速入门（Java 程序员版）

| Python | Java | 说明 |
|--------|------|------|
| `async def method()` | `CompletableFuture<T>` | 异步方法 |
| `await` | `.get()` / `.join()` | 等待异步结果 |
| `async with` | try-with-resources | 自动资源管理 |
| `def method(self)` | `public void method()` | 实例方法（self=this） |
| `dict.get('key')` | `Optional.ofNullable(map.get(key))` | 安全取值 |
| `@decorator` | `@Annotation` | 装饰器/注解 |

---

## 项目结构

```
mcp_getting_started/
├── web_search.py          # MCP Server（工具提供者）
├── stdio_client.py        # MCP Client（测试用）
├── main.py                # 程序入口（未使用）
├── pyproject.toml         # 项目配置（类似 pom.xml）
├── .python-version        # Python 版本锁定
├── .venv/                 # 虚拟环境（类似本地 Maven 仓库）
└── uv.lock                # 依赖锁定（类似 package-lock.json）
```

### pyproject.toml（依赖配置）

```toml
[project]
name = "mcp-getting-started"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.28.1",           # HTTP 客户端库
    "mcp[cli]>=1.27.1",       # MCP 框架（含 CLI 工具）
    "openai>=2.38.0",         # OpenAI SDK
]
```

**Java 对比**：
```xml
<!-- pom.xml -->
<dependencies>
    <dependency>
        <groupId>org.httpx</groupId>
        <artifactId>httpx</artifactId>
        <version>0.28.1</version>
    </dependency>
</dependencies>
```

---

## 代码详解

### MCP Server：web_search.py

```python
import httpx
from mcp.server import FastMCP

# 初始化 FastMCP 服务器
# 类似：@SpringBootApplication
app = FastMCP('web-search')

@app.tool()  # 注册为 MCP 工具，类似 @RequestMapping
async def web_search(query: str) -> str:
    """
    搜索互联网内容

    Args:
        query: 要搜索内容

    Returns:
        搜索结果的总结
    """
    # 创建异步 HTTP 客户端
    # 类似：HttpClient.newBuilder().build()
    async with httpx.AsyncClient() as client:
        # 发送 POST 请求
        # 类似：httpClient.send(request)
        response = await client.post(
            'https://open.bigmodel.cn/api/paas/v4/tools',
            headers={'Authorization': 'your-api-key'},
            json={
                'tool': 'web-search-pro',
                'messages': [
                    {'role': 'user', 'content': query}
                ],
                'stream': False
            }
        )

        # 解析响应数据
        res_data = []
        for choice in response.json()['choices']:      # 遍历 JSON 数组
            for message in choice['message']['tool_calls']:  # 嵌套遍历
                search_results = message.get('search_result')  # 安全取值
                if not search_results:  # falsy 检查
                    continue
                for result in search_results:
                    res_data.append(result['content'])

        # 字符串拼接，类似 String.join()
        return '\n\n\n'.join(res_data)
```

### MCP Client：stdio_client.py

```python
import asyncio
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters

# 配置服务器参数（只是配置，不会启动）
# 类似：ProcessBuilder pb = new ProcessBuilder("uv", "run", "web_search.py")
server_params = StdioServerParameters(
    command='uv',                    # 启动命令
    args=['run', 'web_search.py'],   # 命令参数
)


async def main():
    # 创建 stdio 客户端连接
    # 这里会启动子进程！
    # 类似：Process process = pb.start()
    async with stdio_client(server_params) as (stdio, write):
        # 创建会话
        # 类似：创建 RPC 客户端代理
        async with ClientSession(stdio, write) as session:
            # 初始化连接（握手）
            # 类似：gRPC 的 channel.connect()
            await session.initialize()

            # 列出可用工具
            # 类似：反射获取所有 @RequestMapping 方法
            response = await session.list_tools()
            print(response)

            # 调用工具
            # 类似：RPC 方法调用
            response = await session.call_tool('web_search', {'query': '今天杭州天气'})
            print(response)


# 程序入口
if __name__ == '__main__':
    asyncio.run(main())  # 启动异步事件循环
```

### 关键语法解析

#### 1. 为什么没有 class？

Python 允许模块级别的函数，不需要包装在 class 里：

```python
# Java 必须这样
public class WebSearchService {
    public String search(String query) { ... }
}

# Python 可以直接写函数
def web_search(query: str) -> str:
    ...
```

#### 2. 为什么没有类型声明？

Python 是动态类型语言：

```python
# Java 必须声明类型
FastMCP app = new FastMCP("web-search");

# Python 直接赋值，类型由值决定
app = FastMCP('web-search')  # app 自动就是 FastMCP 类型
```

#### 3. @app.tool() 装饰器

```python
@app.tool()
async def web_search(query: str) -> str:
    ...

# 等价于（装饰器展开）：
async def web_search(query: str) -> str:
    ...
web_search = app.tool()(web_search)  # 注册到 app
```

**Java 类比**：
```java
@RequestMapping("/search")  // 注解
public String search() { ... }

// 运行时等价于：
app.registerTool("web_search", this::search);  // 手动注册
```

---

## 通信协议

MCP 使用 **JSON-RPC 2.0** 协议通信。

### 请求格式（Client → Server）

```json
{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "web_search",
        "arguments": {
            "query": "今天杭州天气"
        }
    }
}
```

### 响应格式（Server → Client）

```json
{
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "content": [
            {
                "type": "text",
                "text": "杭州今天晴，气温 25-32℃..."
            }
        ]
    }
}
```

### 核心方法

| 方法名 | 方向 | 用途 | Java 类比 |
|--------|------|------|-----------|
| `initialize` | Client→Server | 初始化连接，交换能力 | gRPC 握手 |
| `tools/list` | Client→Server | 获取可用工具列表 | 反射获取方法列表 |
| `tools/call` | Client→Server | 调用指定工具 | RPC 方法调用 |

### 完整通信流程

```
Client                                        Server
  │                                              │
  │─────── initialize ─────────────────────────→│
  │                                              │
  │←────── capabilities ──────────────────────│
  │                                              │
  │─────── tools/list ────────────────────────→│
  │                                              │
  │←────── tools 列表 ───────────────────────│
  │                                              │
  │─────── tools/call ────────────────────────→│
  │       (web_search, query="杭州天气")          │
  │                                              │
  │←────── 搜索结果 ───────────────────────│
  │                                              │
```

---

## 调试与测试

### 方式一：MCP Inspector（推荐）

```bash
# 进入项目目录
cd ~/projects/mcp-demo/mcp_getting_started

# 方式 1：使用 mcp 命令
mcp dev web_search.py

# 方式 2：使用 npx
npx -y @modelcontextprotocol/inspector uv run web_search.py
```

成功后打开浏览器访问 `http://localhost:5173`，可以看到可视化调试界面。

```
┌─────────────────────────────────────────────────┐
│  MCP Inspector (Web UI)                         │
│  http://localhost:5173                          │
├─────────────────────────────────────────────────┤
│  Tools:                                         │
│  ┌─────────────────────────────────────────┐   │
│  │  web_search                             │   │
│  │  ┌─────────────────────────────────┐   │   │
│  │  │ query: [________________]       │   │   │
│  │  │ [Run]                           │   │   │
│  │  └─────────────────────────────────┘   │   │
│  └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### 方式二：Python 客户端测试

```bash
python stdio_client.py
```

**注意**：客户端会自动启动服务器，不需要手动运行 `web_search.py`。

### 调试注意事项

**不能使用 print()**：stdout 是数据通道，print 会破坏 JSON-RPC 通信。

```python
# ❌ 错误：会破坏数据流
@app.tool()
async def web_search(query: str) -> str:
    print("调试信息")  # 输出到 stdout，破坏数据流
    return result

# ✅ 正确：使用 logging 输出到 stderr
import logging
logger = logging.getLogger(__name__)

@app.tool()
async def web_search(query: str) -> str:
    logger.debug("调试信息")  # 输出到 stderr，不影响数据流
    return result
```

---

## 部署与使用

### 配置 Claude CLI

```bash
# 1. 安装依赖
cd ~/projects/mcp-demo/mcp_getting_started
uv sync

# 2. 添加 MCP 工具
claude mcp add web-search uv run ~/projects/mcp-demo/mcp_getting_started/web_search.py

# 3. 验证配置
claude mcp list

# 4. 使用
claude
> 搜索一下今天杭州天气
```

### 配置文件位置

```json
// ~/.claude/claude_desktop_config.json
{
  "mcpServers": {
    "web-search": {
      "command": "uv",
      "args": [
        "run",
        "~/projects/mcp-demo/mcp_getting_started/web_search.py"
      ],
      "env": {}
    }
  }
}
```

### 使用流程

```
┌─────────────────────────────────────────────────────────────┐
│  用户使用流程                                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 配置（一次性）                                           │
│     └─ 添加 MCP 工具到 Claude CLI 配置                       │
│                                                             │
│  2. 使用（日常）                                             │
│     └─ 直接用自然语言提问                                     │
│                                                             │
│     用户："帮我查一下订单 12345"                              │
│             │                                               │
│             ▼                                               │
│     AI 判断需要调用工具                                       │
│             │                                               │
│             ▼                                               │
│     自动创建 Client，启动 Server                              │
│             │                                               │
│             ▼                                               │
│     调用 MCP 工具，返回结果                                   │
│             │                                               │
│             ▼                                               │
│     用户看到：订单 12345 的详情                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 常见问题

### Q1: 服务器是什么时候启动的？

```python
server_params = StdioServerParameters(...)  # 只是创建参数对象

async with stdio_client(server_params) as (stdio, write):  # 这里启动！
    # 内部会调用 subprocess 创建子进程
    # 执行：uv run web_search.py
```

### Q2: 为什么不能随便 print()？

stdout 是 MCP 的数据通道，print 会污染数据流：

```
正常数据：{"jsonrpc":"2.0","id":1,"result":{...}}
print 输出：调试信息

混合后：调试信息{"jsonrpc":"2.0","id":1,"result":{...}}
        ↑
        客户端解析失败！
```

### Q3: stdio 为什么只支持单客户端？

一个进程只有一套 stdin/stdout，多客户端同时写入会数据混乱：

```
✅ 单客户端：清晰的通信
Client A ──→ stdin ──→ Server
Client A ←── stdout ←── Server

❌ 多客户端：数据混乱
Client A ──→ stdin ──┐
Client B ──→ stdin ──┼──→ Server（无法区分来源）
Client A ←── stdout ←┘
Client B ←── stdout ←┘（收到错误数据）
```

### Q4: 如何查看已配置的 MCP 工具？

```bash
# Claude CLI
claude mcp list

# 查看配置文件
cat ~/.claude/claude_desktop_config.json
```

---

## 附录：Java 程序员速查表

### Python vs Java 语法对照

| Python | Java | 说明 |
|--------|------|------|
| `import httpx` | `import org.httpx.*` | 导入模块 |
| `async def method()` | `CompletableFuture<T>` | 异步方法 |
| `await expr` | `.get()` / `.join()` | 等待异步结果 |
| `async with resource` | try-with-resources | 自动资源管理 |
| `class MyClass:` | `public class MyClass {}` | 类定义 |
| `def method(self)` | `public void method()` | 实例方法 |
| `self.field` | `this.field` | 访问实例字段 |
| `dict.get('key')` | `map.get("key")` | 字典取值 |
| `[x for x in list]` | `list.stream().collect()` | 列表推导 |
| `f"Hello, {name}"` | `String.format("Hello, %s", name)` | 字符串模板 |
| `@decorator` | `@Annotation` | 装饰器/注解 |

### MCP 核心 API

```python
# Server 端
from mcp.server import FastMCP

app = FastMCP('my-server')

@app.tool()
async def my_tool(param: str) -> str:
    """工具描述"""
    return "result"

# Client 端
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters

server_params = StdioServerParameters(command='...', args=[...])

async with stdio_client(server_params) as (stdio, write):
    async with ClientSession(stdio, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool('my_tool', {'param': 'value'})
```

---

## 总结

### MCP 开发最小要素

1. **编写 Server**：定义工具函数
2. **配置 Host**：告诉 AI 应用你的 Server 在哪里
3. **使用**：直接用自然语言提问

### 核心架构

```
用户 → AI (Host) → Client → Server → 业务逻辑
用户 ← AI (Host) ← Client ← Server ← 返回结果
```

### 关键理解

- **Client 是自动创建的**：你只需要配置 Server
- **stdio 是默认传输方式**：适合本地工具
- **stdout 是数据通道**：不要用 print 输出调试信息
- **JSON-RPC 2.0**：所有通信都是 JSON 格式

---

*本文档基于 MCP Python SDK 1.27.1 编写*
