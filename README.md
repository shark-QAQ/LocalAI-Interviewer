# LocalAI-Interviewer

本地化智能面试官 —— 基于你本地的代码库和简历，动态生成技术问题并模拟真实面试；另附 **MBTI 职业性格测试** 与 **AI 简历生成** 工具。

默认全程离线（本地 Ollama），也支持切换到 **DeepSeek API**（文本生成更快更强；向量检索仍走本地 bge-m3）。

## 功能

| 模块 | 说明 |
|------|------|
| **藏经阁** | 导入本地代码库，自动扫描、切片、向量化，建立知识索引 |
| **拜帖** | 上传 PDF/Word 简历，自动提取技能栈和项目经历，并映射到代码库 |
| **论道** | AI 面试官基于你的代码 + 简历实时提问，SSE 流式输出 |
| **品鉴** | 多维度评估（切题正确/深度/逻辑/完整）+ 雷达图 + 改进建议，可查看/续面/删除历史面试 |
| **秘籍** | 针对你的技术栈，自动生成八股文备考资料 |
| **问心** | MBTI 职业测试：AI 出 20 题 → 判分 → 性格雷达 + 行业适合度（仅 DeepSeek 可用） |
| **挥毫** | AI 简历生成：上传带占位符的 Word 模板 → AI 对话填写 → 生成 docx 并**自动另存到系统桌面**（仅 DeepSeek 可用） |

> 为保证生成质量与可信度，**问心 / 挥毫** 仅在文本生成提供方为 **DeepSeek(API)** 时开放；本地模型下页面显示"锁链+挂锁"提示，点击可跳去「设置」切换。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.10+ / FastAPI / SQLite / ChromaDB |
| 前端 | React 19 / TypeScript / Vite / 水墨风 UI |
| LLM（可选） | 本地 Ollama（默认 `qwen2.5:7b`）⇄ DeepSeek API（默认 `deepseek-v4-flash`，可自定义） |
| Embedding | 本地 Ollama `bge-m3`（1024 维，始终本地） |

## 环境要求

- Python 3.10+、Node.js 18+
- [Ollama](https://ollama.com/) 已安装并运行（**至少需要 bge-m3**；若只用 DeepSeek 生成也仍需 Ollama 提供向量）
- GPU 推荐（本地推理时）：RTX 3060 12GB 或以上
- 可选：DeepSeek API Key（切到 API 模式时使用）

### 1. 安装 Ollama 并拉取模型

```bash
ollama pull bge-m3          # 向量模型（必需）
ollama pull qwen2.5:7b      # 本地生成模型（默认）
```

### 2. 启动

```bash
python start.py             # 一键启动前后端并自动打开浏览器/应用窗口
```

- 停止：在终端 `Ctrl+C`；若卡住另开终端 `python stop.py` 清残留。
- 后端 8000、前端 5173；API 文档 http://localhost:8000/docs

## LLM 提供方：本地 ⇄ DeepSeek

「设置」页（左侧导航 → 设置）可在 **本地 Ollama** 与 **DeepSeek API** 之间即时切换，**无需重启**：

- 填一次 API Key 即持久化到 `data/llm_settings.json`（项目内、删项目即干净；GET 只显示尾号，不回明文）。
- 模型名默认为 `deepseek-v4-flash`，可自定义；API 地址可填中转/代理。
- 「测试连接」可即时验证。
- 环境变量同样可配（会被设置页覆盖）：`APP_LLM_PROVIDER`、`APP_DEEPSEEK_API_KEY`、`APP_DEEPSEEK_BASE_URL`、`APP_DEEPSEEK_MODEL`、`APP_LLM_MODEL`、`APP_EMBEDDING_MODEL`、`OLLAMA_HOST`。

**说明**：DeepSeek 只接管"文本生成"（出题/问答/评分/摘要/参考答案/八股等）；**向量 Embedding 始终用本地 bge-m3**，因此 Ollama 仍需运行。

## 桌面版（Electron，可选）

想以"原生桌面应用窗口"运行（自带图标/标题栏/任务栏，**下载默认保存到系统桌面**）：

```bash
# 安装 Electron 到项目内（约 100MB+，下载缓存也放项目内，只需一次）
# 双击 desktop\安装桌面版.cmd
# 启动桌面应用（自动拉起后端+前端，关窗即停本应用拉起的服务）
# 双击 desktop\运行桌面版.cmd，或系统桌面「LocalAI 面试官」快捷方式
```

- 依赖 `desktop/node_modules`、安装缓存 `.electron-cache/`、运行时数据 `.desktop-userdata/` 全部在项目内。
- 若 8000/5173 已在跑（如 `python start.py`），桌面版会直接复用、不重复拉起。
- 桌面版内下载文件（如生成的简历）默认存到**桌面**；浏览器版则按浏览器下载目录。

### 彻底清理：删项目即干净

应用自身写入全部收敛在项目内：`data/`（SQLite、Chroma、上传、`resume_code_map.json`、`llm_settings.json`、`resume_templates/`、`resume_gen/`）、`desktop/node_modules`、`.desktop-userdata/` 等。删除整个项目文件夹即无应用残留。npm/uv/Ollama 的缓存与模型属外部运行时，不随项目删除。

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
| `GET` | `/api/v1/llm/settings` | 查看 LLM 提供方配置（key 脱敏） |
| `PUT` | `/api/v1/llm/settings` | 保存提供方/模型/Key |
| `POST` | `/api/v1/llm/test` | 测试连接 |
| `GET` | `/api/v1/mbti/questions` | MBTI 出题（20 题，门禁） |
| `POST` | `/api/v1/mbti/result` | MBTI 判分 + 结论（门禁） |
| `GET` | `/api/v1/resume-gen/example-template` | 下载示例占位模板（门禁） |
| `POST` | `/api/v1/resume-gen/upload-template` | 上传模板并解析占位字段（门禁） |
| `POST` | `/api/v1/resume-gen/sessions` | 创建简历会话（门禁） |
| `POST` | `/api/v1/resume-gen/sessions/{id}/chat` | 与 AI 对话填简历（门禁） |
| `POST` | `/api/v1/resume-gen/sessions/{id}/generate` | 生成 docx（门禁） |
| `GET` | `/api/v1/resume-gen/sessions/{id}/download` | 下载生成的简历（门禁） |

## 项目结构

```
LocalAI-Interviewer/
├── backend/                     # FastAPI 后端
│   ├── app/
│   │   ├── main.py              # 入口 + 路由挂载
│   │   ├── config.py            # 配置（env 前缀 APP_）
│   │   ├── database.py          # SQLite（interview.db）
│   │   ├── llm_config.py        # 提供方运行时配置（data/llm_settings.json）
│   │   ├── llm_client.py        # 文本生成调度：Ollama ⇄ DeepSeek
│   │   ├── ollama_client.py     # 本地 Ollama（含 embed/bge-m3）
│   │   ├── vector_store.py      # ChromaDB
│   │   ├── routers/             # projects/resumes/materials/interviews/cram/llm/mbti/resume_gen
│   │   └── services/            # 业务逻辑（含 mbti_service / resume_gen / evaluator…）
│   ├── tests/                   # pytest 单测 + 覆盖率（目标模块 ≥90%）
│   └── .venv/                   # Python 虚拟环境
├── frontend/                    # React + Vite 前端（水墨风）
│   └── src/
│       ├── App.tsx              # 路由/导航
│       ├── api.ts               # API 封装
│       ├── components.tsx       # 复用组件；components/ 下另有 ApiGate(锁门禁)/RadarChart
│       └── pages/               # Projects/Resumes/Interview/Report/Cram/Mbti/ResumeGen/Settings
├── desktop/                     # Electron 桌面壳（自包含）
│   ├── 安装桌面版.cmd / 运行桌面版.cmd
│   ├── main.cjs                 # 主进程（含下载默认到桌面）
│   ├── icon.ico / build_icon.py
│   └── node_modules/
├── data/                        # 运行时数据（自动创建、可删）
│   ├── db/ chroma_data/ uploads/ resumes/
│   ├── resume_code_map.json     # 简历项目↔代码库映射
│   ├── llm_settings.json        # 提供方/Key 配置（gitignore）
│   ├── resume_templates/        # 简历模板（运行时）
│   └── resume_gen/              # 简历会话/产物（运行时）
├── docs/
├── start.py / stop.py / open_app.py + 打开应用窗口.cmd
└── README.md / .gitignore
```

## 测试

```bash
cd backend
uv run pytest tests --cov=app.llm_config --cov=app.llm_client \
  --cov=app.services.mbti_service --cov=app.services.resume_gen \
  --cov=app.services.evaluator --cov=app.routers.mbti \
  --cov=app.routers.resume_gen --cov=app.routers.llm --cov-report=term
```

当前目标模块覆盖 **约 92%**（72 个用例）。测试使用隔离的临时数据目录，不污染真实 `data/`；LLM/Embedding 均已 mock。
（pytest/pytest-cov 直接装在 backend/.venv；如重建虚拟环境需重装 `uv pip install pytest pytest-cov`。）

## 常见问题

**Q: 问心 / 挥毫提示"未解锁/需 DeepSeek"？**
这两项为可信度仅在 API 模式下开放。到「设置」填 DeepSeek Key（模型默认 `deepseek-v4-flash`）→「测试连接」→「保存并应用」，刷新后即可。

**Q: DeepSeek Key 存哪？安全吗？**
存在项目内 `data/llm_settings.json`（已 gitignore、删项目即净）。后端所有 GET/响应只回脱敏尾号，不回明文；日志不打印 Key。

**Q: 简历模板怎么写占位符？**
在 Word 里用 `{{字段名}}`（如 `{{姓名}} {{求职意向}} {{工作经历}}`）。可先「下载示例模板」参考；AI 会逐字段询问并最终替换这些占位生成 Word。

**Q: 生成的简历在哪？**
生成后**默认自动另存一份到系统桌面**（页面会提示文件名）；页面另有「在下载目录再取一份」按钮（Electron 附件下载同样默认桌面）。

**Q: 评分"随便答也不低"？**
单题评分现包含 `correctness`（切题/正确）+ `off_topic/critical_error` 门控，答非所问/硬伤/过短会被代码层强制压到 ≤3；参考答案会作为判分对照。

**Q: Ollama 连接失败？**
先确认 `ollama serve`；至少需拉取 `bge-m3`（向量必需），生成用模型按所选提供方决定。

**Q: 本地生成慢/显存不足？**
Qwen2.5-7B + BGE-M3 本地约需 7GB 显存；可切 DeepSeek（生成走 API）以降低本机负载，或换更小的本地模型。

**Q: 如何支持更多文件类型/语言？**
在 `backend/app/config.py` 的 `allowed_extensions` 中追加后缀即可。

**Q: 复制项目后无法启动？**
若项目被复制到新目录（如 `123/LocalAI-Interviewer`），需注意：
1. **端口冲突**：原项目的后端（8000）和前端（5173）可能仍在运行，需先停掉旧进程。
   ```bash
   python stop.py   # 或在任务管理器中结束相关进程
   ```
2. **前端依赖缺失**：复制时不包含 `node_modules`，需重新安装：
   ```bash
   cd frontend
   npm install
   ```
3. **pytest 未安装**：虚拟环境用 `uv` 创建，不含 pip。如需运行测试：
   ```bash
   uv pip install pytest pytest-cov
   ```

**Q: 如何验证服务是否正常？**
启动后访问以下地址：
- 后端健康检查：`http://localhost:8000/health`
- 后端 API 文档：`http://localhost:8000/docs`
- 前端界面：`http://localhost:5173`

## License

MIT
