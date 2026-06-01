# AI 问答助手

一个前后端分离的 AI 问答助手 MVP。前端使用 React + Vite，后端使用 FastAPI，后端通过 OpenAI-compatible 大模型 API 获取回答，并使用 SQLite 保存会话和消息记录。

## 功能

- 前端聊天页面：输入消息、发送请求、展示用户消息和 AI 回复。
- 后端健康检查：`GET /api/health`。
- 后端聊天接口：`POST /api/chat`。
- 大模型调用：从 `.env` 读取 API Key、Base URL 和模型名称。
- SQLite 存储：保存 conversation 和 message。
- CORS：允许前端 `http://localhost:5173` 访问后端。

## 技术栈

- 前端：React 19、Vite 8
- 后端：FastAPI、Pydantic、Uvicorn
- 数据库：SQLite、SQLAlchemy
- 配置：python-dotenv
- HTTP 请求：requests

## 项目结构

```text
ai-qa-assistant/
  README.md
  .gitignore
  docs/
    PROJECT_PLAN.md
    chat_flow.md
    core_files.md
    learn1.md
  backend/
    .env
    .env.example
    app.db
    requirements.txt
    app/
      main.py
      api/
        chat.py
      core/
        config.py
        prompt.py
      db/
        database.py
      schemas/
        chat_schema.py
      services/
        chat_service.py
        llm_service.py
  frontend/
    package.json
    vite.config.js
    index.html
    src/
      main.jsx
      App.jsx
      ChatPage.jsx
      App.css
      index.css
      api/
        chatApi.js
      components/
        ChatInput.jsx
        MessageList.jsx
        MessageItem.jsx
      assets/
        hero.png
        react.svg
        vite.svg
    public/
      favicon.svg
      icons.svg
```

说明：

- `backend/.env` 是本地真实配置文件，不应提交。
- `backend/.env.example` 是配置模板。
- `backend/app.db` 是本地 SQLite 数据库文件，会自动生成，不应提交。
- `frontend/node_modules/`、`frontend/dist/`、`__pycache__/`、日志文件属于运行或构建产物，不需要手动维护。

## 后端配置

后端会读取 `backend/.env`。

参考 `backend/.env.example` 配置：

```env
APP_NAME=AI QA Assistant
LLM_API_KEY=replace-with-your-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_TIMEOUT=30
```

字段说明：

- `APP_NAME`：FastAPI 应用名称。
- `LLM_API_KEY`：大模型 API Key，必须替换为真实值。
- `LLM_BASE_URL`：OpenAI-compatible API 基础地址，不要带 `/chat/completions`。
- `LLM_MODEL`：模型名称。
- `LLM_TIMEOUT`：请求超时时间，单位秒。

## 启动后端

当前前端代码请求地址是：

```text
http://127.0.0.1:8001/api/chat
```

因此建议后端启动在 `8001` 端口：

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

后端启动时会自动创建 SQLite 表。

## 启动前端

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

浏览器访问：

```text
http://localhost:5173
```

## API 说明

### 健康检查

```http
GET /api/health
```

返回：

```json
{
  "status": "ok"
}
```

### 聊天接口

```http
POST /api/chat
Content-Type: application/json
```

第一次发送消息时，不传 `conversation_id`：

```json
{
  "message": "你好"
}
```

后端会自动创建 conversation，并保存用户消息和 AI 回复。

返回：

```json
{
  "conversation_id": 1,
  "answer": "AI 的回答"
}
```

继续同一个会话时，带上 `conversation_id`：

```json
{
  "message": "继续刚才的话题",
  "conversation_id": 1
}
```

## 数据库

数据库文件位置：

```text
backend/app.db
```

当前有两张表：

- `conversation`
  - `id`
  - `title`
  - `created_at`
  - `updated_at`
- `message`
  - `id`
  - `conversation_id`
  - `role`
  - `content`
  - `created_at`

## 验证方法

先启动后端，再测试健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/health
```

预期返回：

```json
{
  "status": "ok"
}
```

测试第一次聊天：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8001/api/chat `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"message":"你好，请简单介绍一下你自己"}'
```

测试继续会话：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8001/api/chat `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"message":"请继续说明","conversation_id":1}'
```

检查前端：

1. 启动后端 `8001`。
2. 启动前端 `5173`。
3. 打开 `http://localhost:5173`。
4. 输入消息并点击“发送”。
5. 页面应显示用户消息、loading 状态和 AI 回复。

## 常见问题

### 1. 前端提示请求失败

确认后端是否启动在 `8001`：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/health
```

### 2. 后端提示缺少环境变量

检查 `backend/.env` 是否存在，并确认已经填写：

```env
LLM_API_KEY=真实 API Key
LLM_BASE_URL=模型服务地址
LLM_MODEL=模型名称
```

修改 `.env` 后需要重启后端。

### 3. 数据库没有生成

确认后端启动成功。`backend/app.db` 会在 FastAPI 启动时自动创建。

## 开发检查命令

后端编译检查：

```powershell
cd backend
.\.venv\Scripts\python.exe -m compileall app
```

前端代码检查：

```powershell
cd frontend
npm run lint
```

前端构建：

```powershell
cd frontend
npm run build
```
