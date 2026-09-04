# 贡献指南

感谢你对 LocalAI-Interviewer 的关注！

## 开发环境

```bash
# 后端
cd backend
uv sync
uv run run.py

# 前端
cd frontend
npm install
npm run dev
```

## 代码规范

### 后端 (Python)

- 遵循 PEP 8
- 使用 type hints
- 异步优先（FastAPI 路由使用 `async def`）
- 运行 `ruff check` 检查代码风格

### 前端 (TypeScript)

- 使用函数式组件 + Hooks
- 样式使用内联对象（水墨风主题变量定义在 `index.css`）
- 组件定义在 `src/components.tsx`

## 提交规范

```
feat: 新功能
fix: 修复
docs: 文档
style: 样式调整
refactor: 重构
test: 测试
chore: 构建/工具变更
```

## Pull Request

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feat/xxx`
3. 提交更改
4. 推送到你的 Fork
5. 发起 Pull Request

## 问题反馈

请在 GitHub Issues 中反馈问题，包含：

- 操作系统和版本
- Python / Node.js 版本
- 错误信息和复现步骤
