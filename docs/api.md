# API 参考

Base URL: `http://localhost:8000`

## 项目管理

### POST /api/v1/projects/init

导入代码库并建立向量索引（异步）。

**请求体：**
```json
{
  "project_name": "my-project",
  "code_path": "/path/to/code",
  "force_rebuild": false
}
```

**响应：**
```json
{
  "project_id": "abc123",
  "status": "indexing",
  "total_chunks": 0,
  "estimated_time": 30
}
```

### GET /api/v1/projects/list-dirs

浏览文件夹目录。

**参数：**
- `path` (query): 目标路径，为空时返回磁盘列表

**响应：**
```json
{
  "parent": "D:\\",
  "dirs": [
    {"name": "project-a", "path": "D:\\project-a"},
    {"name": "project-b", "path": "D:\\project-b"}
  ]
}
```

### GET /api/v1/projects

列出所有已导入的项目。

### GET /api/v1/projects/{project_id}/status

查询项目索引进度。

**响应：**
```json
{
  "project_id": "abc123",
  "index_status": "completed",
  "chunk_count": 1520,
  "last_indexed_at": "2025-01-01T00:00:00"
}
```

## 简历管理

### POST /api/v1/resumes/upload

上传并解析 PDF 简历。

**请求：** `multipart/form-data`，字段 `file`

**响应：**
```json
{
  "resume_id": "xyz789",
  "parsed_data": {
    "name": "张三",
    "skills": ["Java", "Redis", "Docker"],
    "years_of_experience": 5,
    "projects": [...]
  }
}
```

### GET /api/v1/resumes

列出所有已上传的简历。

### GET /api/v1/resumes/{resume_id}

获取简历详情。

## 面试管理

### POST /api/v1/interviews/sessions

创建面试会话。

**请求体：**
```json
{
  "resume_id": "xyz789",
  "project_id": "abc123",
  "difficulty": "mid",
  "max_rounds": 8
}
```

**响应：**
```json
{
  "session_id": "sess_666",
  "status": "waiting_for_question"
}
```

### POST /api/v1/interviews/sessions/{session_id}/interact

面试交互（SSE 流式响应）。

**请求体：**
```json
{
  "user_answer": "你的回答..."
}
```

`user_answer` 为空时获取第一题。

**SSE 事件流：**

| event | 说明 |
|-------|------|
| `thinking` | 模型思考中 |
| `evaluation` | 上轮评分 |
| `question` | 新题目 |
| `done` | 面试结束 |

### GET /api/v1/interviews/sessions/{session_id}/report

获取面试评估报告。

### GET /api/v1/interviews/sessions/{session_id}

获取会话信息。

## 八股文生成

### POST /api/v1/cram/generate

异步生成八股文。

**请求体：**
```json
{
  "project_id": "abc123",
  "resume_id": "xyz789",
  "focus_areas": ["JVM调优", "分布式锁"]
}
```

**响应：**
```json
{
  "task_id": "cram_001",
  "status": "generating",
  "estimated_seconds": 45
}
```

### GET /api/v1/cram/tasks/{task_id}

查询生成状态和结果。

## 错误码

| HTTP Status | 说明 |
|-------------|------|
| 400 | 请求参数错误 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |
