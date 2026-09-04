# LocalAI-Interviewer

本地化智能面试官 —— 基于你本地的代码库和简历，动态生成技术问题并模拟真实面试；另附 **MBTI 职业性格测试** 与 **AI 简历生成** 工具。

默认全程离线（本地 Ollama），也支持切换到 **DeepSeek API**（文本生成更快更强；向量检索走本地 bge-m3，支持 Ollama 或 HuggingFace 两种加载方式）。

---

## 快速开始（一步一步跟着做）

### 第 1 步：确认环境

你需要先安装好以下软件（任一方式均可）：

| 软件 | 要求 | 检查命令 |
|------|------|----------|
| **Python** | 3.10 或更高 | `python --version` |
| **Node.js** | 18 或更高 | `node --version` |
| **Ollama** | 已安装并能运行 | `ollama --version` |

Windows 用户可直接去官网下载安装：
- Python：https://www.python.org/downloads/ （安装时勾选 "Add to PATH"）
- Node.js：https://nodejs.org/ （选 LTS 版本）
- Ollama：https://ollama.com/download

### 第 2 步：拉取 Ollama 模型

打开终端（PowerShell 或 CMD），执行：

```bash
# 拉取向量嵌入模型（必需，约 1.2GB）
ollama pull bge-m3

# 拉取本地对话模型（可选，约 4.7GB；如果只用 DeepSeek API 则可跳过）
ollama pull qwen2.5:7b
```

验证是否拉取成功：

```bash
ollama list
```

应能看到 `bge-m3` 和 `qwen2.5:7b` 在列表中。

### 第 3 步：安装前端依赖

```bash
cd frontend
npm install
```

等待完成，看到 `added XXX packages` 即成功。

### 第 4 步：一键启动

回到项目根目录：

```bash
cd ..
python start.py
```

启动后会自动打开浏览器。如果没自动打开，手动访问 http://localhost:5173。

看到页面即可开始使用。

### 第 5 步：基本使用流程

1. **上传简历**：左侧导航 → 拜帖 → 选择 PDF/DOCX 文件 → 呈递拜帖
2. **导入代码库**（可选）：左侧导航 → 藏经阁 → 输入项目名称和代码路径 → 导入
3. **开始面试**：左侧导航 → 论道 → 选择简历（项目可选）→ 开坛论道
4. **查看报告**：面试结束后点「查看品鉴报告」

### 停止服务

```bash
python stop.py
```

如果 `stop.py` 无法停止，在终端按 `Ctrl+C`，或在任务管理器中结束 `python` 和 `node` 进程。

---

## 环境要求详细说明

| 条件 | 说明 |
|------|------|
| Python 3.10+ | 后端运行环境 |
| Node.js 18+ | 前端构建与运行 |
| Ollama | 本地模型推理（文本生成 + 向量嵌入） |
| GPU（推荐） | 本地推理时：RTX 3060 12GB 或以上；纯 API 模式不需要 |
| DeepSeek API Key（可选） | 切到 API 文本生成模式时使用 |

---

## 功能

| 模块 | 说明 |
|------|------|
| **藏经阁** | 导入本地代码库，自动扫描、切片、向量化，建立知识索引 |
| **拜帖** | 上传 PDF/Word 简历，自动提取技能栈和项目经历，并映射到代码库 |
| **论道** | AI 面试官基于你的代码 + 简历实时提问，SSE 流式输出 |
| **品鉴** | 多维度评估（切题正确/深度/逻辑/完整）+ 雷达图 + 改进建议 |
| **秘籍** | 针对你的技术栈，自动生成八股文备考资料 |
| **问心** | MBTI 职业测试：AI 出 20 题 → 判分 → 性格雷达 + 行业适合度（仅 DeepSeek） |
| **挥毫** | AI 简历生成：上传 Word 模板 → AI 对话填写 → 生成 docx（仅 DeepSeek） |

> **问心 / 按毫** 仅在文本生成提供方为 **DeepSeek(API)** 时开放；本地模型下页面显示"锁链"提示，点击可跳去设置切换。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.10+ / FastAPI / SQLite / ChromaDB |
| 前端 | React 19 / TypeScript / Vite / 水墨风 UI |
| LLM（可选） | 本地 Ollama（默认 `qwen2.5:7b`）⇄ DeepSeek API（默认 `deepseek-v4-flash`） |
| Embedding | 本地 `bge-m3`（1024 维）—— 通过 Ollama 或 HuggingFace sentence-transformers 加载 |

---

## LLM 提供方：本地 ⇄ DeepSeek

「设置」页（左侧导航 → 设置）可在 **本地 Ollama** 与 **DeepSeek API** 之间即时切换，**无需重启**：

- 填一次 API Key 即持久化到 `data/llm_settings.json`（删项目即干净；GET 只显示尾号，不回明文）。
- 模型名默认为 `deepseek-v4-flash`，可自定义；API 地址可填中转/代理。
- 「测试连接」可即时验证。

环境变量同样可配（会被设置页覆盖）：

```bash
APP_LLM_PROVIDER=ollama          # ollama 或 deepseek
APP_DEEPSEEK_API_KEY=sk-xxx      # DeepSeek API Key
APP_DEEPSEEK_BASE_URL=https://api.deepseek.com
APP_DEEPSEEK_MODEL=deepseek-v4-flash
APP_LLM_MODEL=qwen2.5:7b
APP_EMBEDDING_MODEL=bge-m3
APP_EMBEDDING_PROVIDER=ollama     # ollama 或 huggingface
APP_HUGGINGFACE_MODEL=BAAI/bge-m3
OLLAMA_HOST=http://localhost:11434
```

## 嵌入提供方：Ollama ⇄ HuggingFace

「设置」页底部 **向量嵌入（Embedding）** 区域可切换嵌入后端，**无需重启**：

| 模式 | 说明 |
|------|------|
| **Ollama**（默认） | 通过 Ollama 运行 `bge-m3`，需先 `ollama pull bge-m3` |
| **HuggingFace** | 通过 `sentence-transformers` 加载本地模型，无需 Ollama 的 bge-m3 |

- 填入 HuggingFace 模型 ID（如 `BAAI/bge-m3`）会自动下载；填本地目录路径（如 `D:\models\bge-m3`）则直接加载不联网。
- 安装 HuggingFace 依赖（需要 `torch`，约 118MB+）：

```bash
cd backend
uv pip install -e ".[huggingface]"
```

---

## 桌面版（Electron，可选）

```bash
# 安装（只需一次）
cd desktop
双击 安装桌面版.cmd

# 启动
双击 运行桌面版.cmd
# 或使用系统桌面「LocalAI 面试官」快捷方式
```

- 若 8000/5173 已在跑（如 `python start.py`），桌面版会直接复用。
- 桌面版内下载文件默认存到**桌面**。

### 彻底清理：删项目即干净

应用自身写入全部收敛在项目内：`data/`（SQLite、Chroma、上传文件、配置）等。删除整个项目文件夹即无应用残留。Ollama 的模型缓存属外部运行时，不随项目删除。

---

## API 主要端点

| 方法 | 路径 | 功能 |
|------|------|------|
| `POST` | `/api/v1/projects/init` | 导入代码库并建立索引 |
| `GET` | `/api/v1/projects` | 列出已有项目 |
| `POST` | `/api/v1/resumes/upload` | 上传 PDF/Word 简历 |
| `GET` | `/api/v1/resumes` | 列出已有简历 |
| `POST` | `/api/v1/interviews/sessions` | 创建面试会话 |
| `POST` | `/api/v1/interviews/sessions/{id}/interact` | 面试交互（SSE） |
| `GET` | `/api/v1/interviews/sessions/{id}/report` | 面试报告 |
| `POST` | `/api/v1/cram/generate` | 生成八股文 |
| `GET` | `/api/v1/llm/settings` | 查看 LLM 配置（key 脱敏） |
| `PUT` | `/api/v1/llm/settings` | 保存提供方/模型/Key/嵌入设置 |
| `POST` | `/api/v1/llm/test` | 测试 LLM 连接 |
| `POST` | `/api/v1/llm/test-embed` | 测试嵌入后端 |
| `GET` | `/api/v1/mbti/questions` | MBTI 出题（门禁） |
| `POST` | `/api/v1/mbti/result` | MBTI 判分（门禁） |
| `POST` | `/api/v1/resume-gen/sessions` | 创建简历生成会话（门禁） |
| `POST` | `/api/v1/resume-gen/sessions/{id}/chat` | AI 对话填简历（门禁） |
| `POST` | `/api/v1/resume-gen/sessions/{id}/generate` | 生成 docx（门禁） |

---

## 项目结构

```
LocalAI-Interviewer/
├── backend/                     # FastAPI 后端
│   ├── app/
│   │   ├── main.py              # 入口 + 路由挂载
│   │   ├── config.py            # 配置（env 前缀 APP_）
│   │   ├── database.py          # SQLite
│   │   ├── llm_config.py        # 提供方运行时配置
│   │   ├── llm_client.py        # 文本生成调度：Ollama ⇄ DeepSeek
│   │   ├── ollama_client.py     # 本地 Ollama 客户端
│   │   ├── embed_client.py      # 统一嵌入：Ollama ⇄ HuggingFace
│   │   ├── vector_store.py      # ChromaDB
│   │   ├── routers/             # API 路由
│   │   └── services/            # 业务逻辑
│   ├── tests/                   # pytest 单测
│   └── .venv/                   # Python 虚拟环境
├── frontend/                    # React + Vite 前端
│   └── src/
│       ├── App.tsx              # 路由/导航
│       ├── api.ts               # API 封装
│       ├── components.tsx       # 复用组件
│       └── pages/               # 各页面组件
├── desktop/                     # Electron 桌面壳（可选）
├── data/                        # 运行时数据（自动创建、可删）
├── start.py / stop.py           # 一键启动/停止
└── README.md
```

---

## 测试

```bash
cd backend
uv run pytest tests --cov=app.llm_config --cov=app.llm_client \
  --cov=app.services.mbti_service --cov=app.services.resume_gen \
  --cov=app.services.evaluator --cov=app.routers.mbti \
  --cov=app.routers.resume_gen --cov=app.routers.llm --cov-report=term
```

目标模块覆盖率约 92%（72 个用例）。测试使用隔离的临时数据目录；LLM/Embedding 均已 mock。

---

## 常见问题

**Q: 启动后页面空白？**
确保前端依赖已安装：`cd frontend && npm install`，然后重新 `python start.py`。

**Q: Ollama 连接失败？**
1. 确认 Ollama 正在运行：终端执行 `ollama list` 看能否列出模型
2. 如果报错，启动 Ollama：`ollama serve`
3. 确认已拉取模型：`ollama pull bge-m3` 和 `ollama pull qwen2.5:7b`

**Q: 问心 / 挥毫提示"未解锁/需 DeepSeek"？**
这两项仅在 DeepSeek API 模式下可用。到「设置」填 DeepSeek Key → 测试连接 → 保存并应用 → 刷新页面。

**Q: DeepSeek Key 存哪？安全吗？**
存在项目内 `data/llm_settings.json`（已 gitignore）。后端响应只回脱敏尾号，不回明文。

**Q: 简历模板怎么写占位符？**
在 Word 里用 `{{字段名}}`（如 `{{姓名}} {{求职意向}} {{工作经历}}`）。可先「下载示例模板」参考。

**Q: 生成的简历在哪？**
生成后默认自动另存一份到系统桌面；页面另有下载按钮。

**Q: 评分"随便答也不低"？**
单题评分包含 `correctness`（切题/正确）+ `off_topic/critical_error` 门控，答非所问/硬伤/过短会被压分。

**Q: 本地生成慢/显存不足？**
Qwen2.5-7B + BGE-M3 约需 7GB 显存。可切 DeepSeek（生成走 API）降低本机负载，或换更小的本地模型。

**Q: 复制项目后无法启动？**
1. 先停旧进程：`python stop.py`
2. 安装前端依赖：`cd frontend && npm install`
3. 重新启动：`cd .. && python start.py`

**Q: 如何验证服务是否正常？**
- 后端健康检查：http://localhost:8000/health
- 后端 API 文档：http://localhost:8000/docs
- 前端界面：http://localhost:5173

---

## License

MIT
