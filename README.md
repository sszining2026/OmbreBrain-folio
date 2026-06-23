# Ombre Brain

一个给 Claude（或其它 MCP 客户端）用的长期情绪记忆系统。基于 Russell 效价/唤醒度坐标打标，Obsidian 做存储层，MCP 接入，带遗忘曲线和向量语义检索。

A long-term emotional memory system for Claude (and any MCP client). Tags memories using Russell's valence/arousal coordinates, stores them as Obsidian-compatible Markdown, connects via MCP, with forgetting curve and vector semantic search.

> **开发者文档**：架构 / API / 配置细节请见 [docs/INTERNALS.md](docs/INTERNALS.md)。本 README 只关心『怎么把它跑起来用上』。

---

## 它是什么 / What is this

Claude 没有跨对话记忆。每次新会话开始，之前聊过的东西都消失。

Ombre Brain 给它一套持久记忆——不是冷冰冰的键值存储，而是带情感坐标、会自然衰减、像人类一样会遗忘和浮现的系统。

Claude has no cross-conversation memory. Everything from a previous chat vanishes once it ends.

Ombre Brain gives it persistent memory — not cold key-value storage, but a system with emotional coordinates, natural decay, and forgetting/surfacing mechanics that loosely mimic how human memory works.

**核心特性 / Key features**

- **情感坐标打标**：每条记忆用 Russell 环形情感模型的 valence（效价）+ arousal（唤醒度）两个连续维度标记，不是「开心/难过」这种离散标签
- **双通道检索**：rapidfuzz 关键词匹配 + cosine 向量语义并联检索，去重合并后按 token 预算截断
- **自然遗忘**：改进版艾宾浩斯遗忘曲线，不活跃的记忆自动衰减归档，高情绪强度的记忆衰减更慢
- **权重池浮现**：未解决的、情绪强烈的记忆权重更高，对话开头自动浮现
- **Obsidian 原生**：每个记忆桶 = 一个 Markdown 文件 + YAML frontmatter，可直接在 Obsidian 浏览编辑
- **历史对话导入**：批量导入 Claude / ChatGPT / DeepSeek 历史对话，分块处理带断点续传
- **Dashboard**：内置 Web 管理面板，密码保护，桶列表 / 检索调试 / 记忆网络 / 配置管理
- **Cloudflare Tunnel 一键管理**：Dashboard 内置 Tunnel 连接器，无需命令行即可开启公网访问
- **OAuth 2.1 远程鉴权**：通过 HTTPS 连接时自动触发 OAuth 流程，Claude.ai 网页版和 Claude Code 均支持

---

## 快速开始 / Quick Start（Docker Hub 预构建镜像）

> 不需要 clone 代码，不需要 build。第一次完整跑通约 5 分钟。

### 第零步：装 Docker Desktop

打开 [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)，下载对应你系统的版本，安装后启动。Windows 用户安装时会提示启用 WSL 2，点同意。

### 第一步：打开终端

| 系统 | 怎么打开 |
|---|---|
| **Mac** | `⌘ + 空格` → 输入 `终端` → 回车 |
| **Windows** | `Win + R` → 输入 `cmd` → 回车 |
| **Linux** | `Ctrl + Alt + T` |

### 第二步：创建工作文件夹

```bash
mkdir ombre-brain && cd ombre-brain
```

### 第三步：下载 compose 文件并启动

**不需要提前准备 API Key**——Ombre Brain 支持零配置启动，API Key 可以在 Dashboard 里随时填入并立即生效。

```bash
# 下载用户版 compose 文件
curl -O https://raw.githubusercontent.com/P0luz/Ombre-Brain/main/deploy/docker-compose.user.yml

# 拉取镜像并启动（第一次会下载约 500MB）
docker compose -f docker-compose.user.yml up -d
```

启动后在 Dashboard → **③ 引擎** 里填入 Key 并点「保存 Key」，立即热更新生效，无需重启。

> 也可以提前在 `.env` 文件里写好 Key：
> ```bash
> echo "OMBRE_COMPRESS_API_KEY=your-key-here" > .env
> echo "OMBRE_EMBED_API_KEY=your-embed-key" >> .env
> ```

**推荐免费方案：Google AI Studio**

1. 打开 [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. 用 Google 账号登录 → 点 **Create API key** → 复制
3. 推荐模型（均为免费额度，以官网实时信息为准）：
   - 脱水/打标模型：`gemini-2.0-flash`（无思考开销，稳定，免费）
   - 向量化模型：`gemini-embedding-001`（1500 req/day，3072 维，免费）
   - Base URL：`https://generativelanguage.googleapis.com/v1beta/openai/`

也支持任何 OpenAI 兼容接口：DeepSeek / SiliconFlow / Ollama / LM Studio / vLLM 等。

### 第四步：验证

```bash
curl http://localhost:8000/health
```

返回 `{"status":"ok",...}` 即成功。

浏览器打开 Dashboard：`http://localhost:8000`

> 第一次访问会弹出密码设置向导，设好密码后所有 `/api/*` 端点都需要这个密码登录。

### 第五步：接入 Claude

---

## 接入方式 / Connect to Claude

### 方式一：本地 stdio（Claude Desktop，最简单）

适合：在同一台电脑上用 Claude Desktop。不需要公网，零延迟。

打开配置文件（macOS：`~/Library/Application Support/Claude/claude_desktop_config.json`，Windows：`%APPDATA%\Claude\claude_desktop_config.json`），加入：

```json
{
  "mcpServers": {
    "ombre-brain": {
      "command": "python",
      "args": ["/path/to/Ombre-Brain/src/server.py"]
    }
  }
}
```

或者如果用 Docker 跑：

```json
{
  "mcpServers": {
    "ombre-brain": {
      "type": "streamable-http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

重启 Claude Desktop，工具列表里会出现 11 个工具：`breath` / `hold` / `grow` / `trace` / `pulse` / `dream` / `plan` / `letter_write` / `letter_read` / `anchor` / `release`。

---

### 方式二：HTTPS 远程连接（Claude.ai 网页版 / Claude Code / 手机）

适合：想在手机、浏览器、多台设备上用；或通过 claude.ai 网页版访问。

**必须先把服务暴露到公网**，推荐使用 Cloudflare Tunnel（免费）。

#### 步骤 1：配置 Cloudflare Tunnel

**方法 A：通过 Dashboard 一键配置（推荐）**

1. 去 [Cloudflare Zero Trust](https://one.dash.cloudflare.com) → **Networks → Tunnels → Create a tunnel**
2. 选 **Cloudflared** → 给 Tunnel 起名 → 下一步
3. 在 **Install connector** 页，选 **Docker**，找到 `--token` 后面那一长串字符（以 `eyJ` 开头），复制它
4. 回到 Ombre Brain Dashboard → **设置** → **Cloudflare Tunnel** 区域
5. 把 token 粘贴到输入框 → 点「**保存 Token**」→ 点「**启动**」
6. 状态点变绿（已连接）后，回到 Cloudflare 添加 Public Hostname：
   - **Domain**：你的域名（例如 `ombre.example.com`）
   - **Service Type**：HTTP
   - **URL**：`localhost:8000`
7. 保存后等约 30 秒，Tunnel 生效

**方法 B：命令行手动运行**

```bash
# 替换为你的 token
cloudflared tunnel --no-autoupdate run --token eyJ...
```

#### 步骤 2：连接 Claude.ai 网页版

1. 打开 [claude.ai](https://claude.ai) → 左侧边栏 → **Connectors**（或 **MCP Servers**）
2. 点 **Add** → 填入你的 Tunnel 域名：`https://ombre.example.com/mcp`
3. **自动触发 OAuth 授权流程**（详见下方说明）

#### OAuth 授权流程详解

这是最容易卡住的地方，解释清楚每一步：

```
Claude.ai                    Ombre Brain 服务器
   │                               │
   │── POST /mcp ─────────────────>│ 401 Unauthorized
   │<─ WWW-Authenticate: Bearer ───│ (告知需要 OAuth)
   │                               │
   │── GET /.well-known/oauth-authorization-server ──>│
   │<─ {authorization_endpoint, registration_endpoint...} ─│
   │                               │
   │── POST /oauth/register ──────>│ 201 (动态注册，拿到 client_id)
   │<─ {client_id: "xxx"} ─────────│
   │                               │
   │  [打开浏览器弹窗]              │
   │── GET /oauth/authorize ──────>│ 返回授权页 HTML
   │                               │
   │  [你在弹出页面输入 Dashboard 密码]
   │                               │
   │── POST /oauth/authorize ─────>│ 302 (验证通过，生成授权码)
   │<─ redirect_uri?code=xxx ──────│
   │                               │
   │── POST /oauth/token ─────────>│ 200 (交换 Bearer Token)
   │<─ {access_token: "..."} ──────│
   │                               │
   │── POST /mcp (Bearer token) ──>│ 200 (MCP 会话建立)
   │<─ tools: [breath, hold...] ───│
```

**注意事项**：
- 弹出的授权页是你自己的 Ombre Brain 服务器，不是第三方
- 密码就是你的 Dashboard 密码
- Token 有效期 30 天，过期后会自动重新授权
- 同一账号第一次授权后，之后的连接自动使用存储的 token

#### 步骤 3：工具分布（两个连接器）

Ombre Brain 出于 claude.ai 的 5 工具限制将工具拆成两个端点：

| 端点 | 工具 | 说明 |
|---|---|---|
| `/mcp` | `breath` `hold` `grow` `dream` `trace` | 高频工具，日常主要用这个 |
| `/mcp-extra` | `anchor` `release` `pulse` `plan` `letter_write` `letter_read` | 低频工具 |

在 Claude.ai 里分别添加 `/mcp` 和 `/mcp-extra` 两个连接器，即可使用全部 11 个工具。

#### 步骤 4：Claude Code（终端）远程连接

Claude Code 同样支持 OAuth 远程 MCP，但 **本地使用推荐 stdio**（更简单，无需 OAuth）：

```bash
# 本地 stdio（推荐）
claude mcp add ombre-brain python /path/to/server.py

# 远程 HTTPS（需要 OAuth，同 Claude.ai 流程）
claude mcp add ombre-brain --transport http https://ombre.example.com/mcp
```

---

## 从源码部署 / Deploy from Source

适合想自己改代码或部署到 VPS 的用户。

```bash
git clone https://github.com/P0luz/Ombre-Brain.git
cd Ombre-Brain
docker compose -f deploy/docker-compose.yml up -d
```

验证：

```bash
docker logs ombre-brain   # 看到 "Uvicorn running on http://0.0.0.0:8000"
curl http://localhost:18001/health   # docker-compose.yml 默认映射 18001:8000
```

Dashboard：`http://localhost:18001`

**VPS 部署注意**：`deploy/docker-compose.yml` 默认端口是 `127.0.0.1:18001`（仅本机访问）。如果没有反代，可改为 `0.0.0.0:18001` 对外开放，再配合 Cloudflare Tunnel 或 nginx 反代到 443。

### 不用 Docker（纯 Python）

```bash
git clone https://github.com/P0luz/Ombre-Brain.git
cd Ombre-Brain

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp config.example.yaml config.yaml
python src/server.py
```

---

## 部署到云平台 / Deploy to Cloud Platforms

### Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/P0luz/Ombre-Brain)

> ⚠️ **免费层不可用**：Render 免费层无持久化磁盘，重启后记忆会丢失，且无流量时会休眠。**必须使用 Starter（$7/mo）或以上**。

仓库已包含 `render.yaml`。点按钮后：

1. 设置环境变量 `OMBRE_COMPRESS_API_KEY`（必需）
2. 可选 `OMBRE_COMPRESS_BASE_URL`（例如 `https://generativelanguage.googleapis.com/v1beta/openai/`）和 `OMBRE_EMBED_API_KEY`
3. 持久化磁盘自动挂载到 `/opt/render/project/src/buckets`
4. 部署后 Dashboard：`https://<服务名>.onrender.com`，MCP URL：`https://<服务名>.onrender.com/mcp`

Render 自带 HTTPS，可直接在 Claude.ai 添加，无需额外 Tunnel。

### Zeabur

[![Deploy on Zeabur](https://zeabur.com/button.svg)](https://zeabur.com/templates/OMBRE-BRAIN)

1. Fork 本仓库 → Zeabur **New Project** → **Deploy from GitHub**
2. Variables 填 `OMBRE_COMPRESS_API_KEY`（必填）
3. Volumes → 挂载路径 `/app/buckets`
4. Networking → Port `8000` → **Generate Domain**

### 自有 VPS

```bash
git clone https://github.com/P0luz/Ombre-Brain.git
cd Ombre-Brain
cp config.example.yaml config.yaml
# 修改 config.yaml 设置 API key 和其他参数
docker compose -f deploy/docker-compose.yml up -d
```

配合 nginx / Caddy 反代到 443 端口，或直接用 Dashboard 内置的 Cloudflare Tunnel 管理器。

---

## Dashboard 功能概览

启动后浏览器打开 `/`（根路径）进入，第一次会引导设置密码。

| 标签页 | 功能 |
|---|---|
| **记忆** | 桶列表，按 domain / type 筛选，单桶可 pin / resolve / archive / delete |
| **Breath 调试** | 模拟检索查询，查看每个桶的四维评分分解 |
| **记忆网络** | 基于 embedding 相似度的桶关系图 |
| **③ 引擎** | 内联填写 LLM / Embedding API Key，在线修改参数，点「保存 Key」立即热更新 |
| **导入** | 上传历史对话文件批量导入 |
| **设置** | 修改密码、版本状态、Cloudflare Tunnel 管理、API Key 测试 |

**设置页 Cloudflare Tunnel 区**：填入 Token 后点启动，状态点颜色表示连接状态（灰=未运行，橙=连接中，绿=已连接，红=连接失败+错误原因）。支持「启动时自动连接」。

**API Key 测试按钮**：填入 Gemini API Key 后点「测试」，立即验证 Key 是否有效，显示 ✓ 或具体错误原因，无需手写测试请求。

---

## 配置 / Configuration

所有可调参数都在 `config.yaml`（从 `config.example.yaml` 复制）。最常用的几个：

| 参数 | 说明 | 推荐值 |
|---|---|---|
| `transport` | `stdio`（本地）/ `streamable-http`（远程） | Docker 部署用 `streamable-http` |
| `dehydration.model` | 脱水/打标 LLM 模型 | `gemini-2.0-flash` |
| `dehydration.base_url` | LLM API 地址 | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `dehydration.max_tokens` | 模型最大输出 token | `4096`（必须足够大，否则 JSON 截断导致域分类失败） |
| `embedding.api_format` | `gemini`（云端）/ `ollama`（本地 bge-m3）/ `openai_compat` | `gemini` |
| `embedding.model` | embedding 模型 | 云端 `gemini-embedding-001` / 本地 `bge-m3` |
| `decay.lambda` | 衰减速率，越大越快忘 | `0.05` |
| `merge_threshold` | 合并相似度阈值 (0-100) | `75` |

> ⚠️ **`dehydration.max_tokens` 不能太小**：Gemini 2.5 系列模型有「思考 token」开销，如果 max_tokens 设得太小（如 256/512），思考 token 会耗尽预算，JSON 响应被截断，导致所有记忆被错误分类为「未分类」。推荐 `gemini-2.0-flash`（无思考开销）或将 max_tokens 设为 `4096` 以上。

### Embedding 两后端：云端 Gemini vs 本地 bge-m3

| 后端 | 类型 | 维度 | 资源 | 适合 |
|---|---|---|---|---|
| **云端**（`api_format: gemini`） | Gemini API | 3072 | 0（不占本机） | 大多数人。免费额度 1500 req/day 够用，开箱即用 |
| **本地**（`api_format: ollama`） | Ollama + bge-m3 | 1024 | **约 2–3GB 空闲内存** + 1.2GB 磁盘，纯 CPU | 不想出网 / 没有 API key / 数据敏感 / 自托管 |

> 💾 **本地模型内存提醒**：bge-m3 加载后常驻约 2–3GB 内存。低配机器（<2GB 空闲内存）建议继续用云端；纯 CPU 即可推理，首条查询冷启动约 1–9s，之后 <0.5s。

**本地向量化怎么搭（一键，无需命令行）**

本地模型跑在一个独立的 `ollama` 容器里（OB 不直接管它，所以最稳）。两步：

1. **启动 ollama 容器**（一次性）。用源码部署的话，`deploy/docker-compose.yml` 里已带 `ollama` 服务，直接：
   ```bash
   docker compose -f deploy/docker-compose.yml up -d ollama
   ```
   或独立起一个（和 OB 同一 docker 网络即可）：
   ```bash
   docker run -d --name ombre-ollama --restart unless-stopped \
     --network <OB所在网络> -v ollama:/root/.ollama ollama/ollama
   ```
2. **Dashboard → 设置 → 向量化 → 「🖥️ 本地向量模型」面板 → 点「🚀 一键搭建本地向量化」**。它会自动：下载 bge-m3（约 1.2GB，带进度条）→ 切换后端 → 后台重算全库向量。期间照常使用，检索暂用旧库。

> 🌐 **国内网络**：模型下载默认走 ollama 官方源。拉不动时，在面板「分步操作」里换下载镜像（选 ModelScope 或填自定义 registry 前缀），再点「仅下载」。

**云端 ↔ 本地随时切换**：Dashboard → 设置 → 向量化面板 →「一键搭建本地向量化」或「切回云端 Gemini」。

> ⚠️ 两个后端向量维度不同（3072 vs 1024），**每次切换都会全库重算**（自动备份旧 DB、后台进行、失败不动旧库）。不要频繁来回切。

---

## 把记忆挂到 Obsidian

打开 `docker-compose.user.yml`，把 `./buckets:/data` 改成你的 Vault 路径：

```yaml
- /Users/你的用户名/Documents/Obsidian Vault/Ombre Brain:/data
```

重启后每条记忆就是 Vault 里一个 Markdown 文件，可在 Obsidian 直接浏览编辑。

---

## 更新 / How to Update

### Docker Hub 镜像用户

```bash
docker pull p0luz/ombre-brain:latest
docker compose -f docker-compose.user.yml down
docker compose -f docker-compose.user.yml up -d
```

### 从源码部署用户

```bash
cd Ombre-Brain
git pull origin main
docker compose -f deploy/docker-compose.yml down
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

记忆数据在 volume 里，更新不会丢失。

---

## 给 Claude 的使用指南

`docs/CLAUDE_PROMPT.md` 是写给 Claude 看的工具使用约定。把它放进 system prompt / custom instructions / Claude Desktop 项目说明里即可。

---

## 常见问题 / Troubleshooting

| 现象 | 可能原因 | 解决 |
|---|---|---|
| 首次进 Dashboard 设置密码页一闪而过变成登录页 | 已修复（v2.0.4+） | 更新到最新版本 |
| 所有记忆 domain 显示「未分类」 | `max_tokens` 太小，JSON 被截断 | 在 Dashboard ③ 引擎 或 `config.yaml` 将 `dehydration.max_tokens` 设为 `4096`；推荐用 `gemini-2.0-flash` 而非 2.5 系列 |
| Claude.ai 添加 MCP 报「Couldn't register」 | OAuth 端点无法访问（通常是 Tunnel 未启动/域名错误） | 先确认 Dashboard 能正常访问，再添加 MCP |
| OAuth 授权页正常弹出但密码输入后报错 | Dashboard 密码错误 | 使用 Dashboard 设置时的密码（不是 Cloudflare 密码） |
| 连接成功但「no tools available」 | 连接到了 `/mcp-extra` 但期望 `/mcp`，或反之 | 检查 URL 末尾是 `/mcp` 还是 `/mcp-extra`；分别添加两个连接器 |
| Token 过期后无法自动重连 | Bearer token 默认 30 天有效 | 在 Claude.ai connector 设置里重新授权 |
| Dashboard 401 | 未登录 / 密码错 | 浏览器重新登录 |
| `hold` / `grow` 报 API key 错误 | LLM key 未配置 | Dashboard → ③ 引擎 填入 Key 点「保存 Key」，立即热更新 |
| 重启后记忆丢失 | Volume 没挂载 | 检查 docker-compose volume 配置 |
| Tunnel 状态红色 / 连接失败 | Token 无效或 cloudflared 报错 | 展开 Dashboard 红色错误框查看 cloudflared 输出；重新从 Cloudflare Zero Trust 获取 token |
| 隧道连接偶尔断 | Cloudflare Free 闲置超时 | 内置 keepalive 已缓解；可在 Cloudflare Tunnel 设置里调整超时 |

---

## License

MIT
