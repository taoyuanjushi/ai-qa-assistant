# AI 问答助手

一个前后端分离的 AI 问答助手 MVP。前端使用 React + Vite，后端使用 FastAPI，后端通过 OpenAI-compatible 大模型 API 获取回答，并使用 SQLite 保存会话、消息和文档元信息；RAG 部分使用 Embedding Model + Chroma 支持多文档知识库问答。

## 功能

- 前端聊天页面：输入消息、发送请求、展示用户消息和 AI 回复。
- 后端健康检查：`GET /api/health`。
- 后端聊天接口：`POST /api/chat`。
- 后端流式聊天接口：`POST /api/chat/stream`。
- 历史会话接口：`GET /api/conversations`、`GET /api/conversations/{conversation_id}/messages`。
- Chroma RAG：支持单文件或批量上传 TXT/Markdown/PDF/DOCX，提取文本、保存解析文本、切分 chunk、生成 embedding、写入 Chroma；主聊天窗口可选择多个文档，或空选择时默认检索全部文档，并显示 sources。
- RAG 检索优化：支持 Chroma 粗召回 + 专业 Rerank API 重排，未配置或调用失败时自动回退到 LLM/规则 Rerank。
- 文档摘要缓存：上传后尝试为每篇文档生成结构化摘要，多文档论文分析时结合摘要和 reranked chunks。
- 知识库管理：支持删除单个文档、清空知识库、重建单个文档索引。
- 大模型调用：从 `.env` 读取 API Key、Base URL 和模型名称。
- SQLite 存储：保存 conversation、message、document 元信息、解析后的 `content` 和索引状态；Chroma 保存 chunk 文本和 embedding。
- 工程化基础：统一错误响应、请求日志、外部依赖耗时日志、pytest、Docker Compose、GitHub Actions CI。
- CORS：允许前端 `http://localhost:5173` 访问后端，并暴露 `X-Conversation-Id` 响应头。

## 技术栈

- 前端：React 19、Vite 8
- 后端：FastAPI、Pydantic、Uvicorn
- 数据库：SQLite、SQLAlchemy
- 向量库：Chroma
- 文档解析：pypdf、python-docx
- 配置：python-dotenv
- HTTP 请求：requests
- 工程化：pytest、Docker、Docker Compose、GitHub Actions

## 项目结构

```text
ai-qa-assistant/
  README.md
  .gitignore
  docs/
    PROJECT_PLAN.md
    chat_flow.md
    core_files.md
    rag_operations.md
    BUG_FIX_AND_TEST_REPORT.md
    RAG_OPTIMIZATION_NOTES.md
    RAG_EVALUATION.md
    GITHUB_PROJECT_GUIDE.md
    learn1.md
  .github/
    workflows/
      ci.yml
  docker-compose.yml
  backend/
    .env
    .env.example
    Dockerfile
    app.db
    requirements.txt
    app/
      main.py
      api/
        chat.py
        conversation.py
        rag.py
      core/
        config.py
        prompt.py
      db/
        database.py
      schemas/
        chat_schema.py
        conversation_schema.py
        rag_schema.py
      services/
        chat_service.py
        conversation_service.py
        chroma_service.py
        document_parser.py
        embedding_service.py
        llm_service.py
        rag_service.py
        rerank_service.py
        summary_service.py
  frontend/
    package.json
    .env.example
    Dockerfile
    vite.config.js
    index.html
    src/
      main.jsx
      App.jsx
      ChatPage.jsx
      App.css
      index.css
      api/
        config.js
        chatApi.js
        conversationApi.js
        ragApi.js
      components/
        ChatInput.jsx
        ConversationItem.jsx
        ConversationList.jsx
        DocumentToolbar.jsx
        MessageList.jsx
        MessageItem.jsx
        SourceList.jsx
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
- `backend/chroma_db/` 是 Chroma 本地向量库目录，清空或更换 embedding 模型时可能需要重建。

## 后端配置

后端会读取 `backend/.env`。

参考 `backend/.env.example` 配置：

```env
APP_NAME=AI QA Assistant
APP_ENV=local
LOG_LEVEL=INFO
STRICT_CONFIG_VALIDATION=false
LLM_API_KEY=replace-with-your-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_TIMEOUT=30
EMBEDDING_API_KEY=
EMBEDDING_BASE_URL=
EMBEDDING_MODEL=text-embedding-3-small
DATABASE_PATH=app.db
CHROMA_PERSIST_DIR=./chroma_db
CHROMA_COLLECTION_NAME=ai_qa_documents
RERANK_ENABLED=true
RERANK_CANDIDATE_TOP_K=20
RERANK_FINAL_TOP_K=5
RERANK_API_KEY=
RERANK_BASE_URL=
RERANK_MODEL=
RERANK_API_FORMAT=auto
RERANK_TIMEOUT=30
RERANK_USE_LLM=false
```

字段说明：

- `APP_NAME`：FastAPI 应用名称。
- `APP_ENV`：运行环境标识，默认 `local`。
- `LOG_LEVEL`：日志级别，默认 `INFO`。
- `STRICT_CONFIG_VALIDATION`：是否在启动时强制校验 LLM/Embedding 配置；默认 `false`，只输出 warning。
- `LLM_API_KEY`：大模型 API Key，必须替换为真实值。
- `LLM_BASE_URL`：OpenAI-compatible API 基础地址，不要带 `/chat/completions`。
- `LLM_MODEL`：模型名称。
- `LLM_TIMEOUT`：请求超时时间，单位秒。
- `EMBEDDING_API_KEY`：Embedding API Key；留空时复用 `LLM_API_KEY`。
- `EMBEDDING_BASE_URL`：Embedding API 基础地址；留空时复用 `LLM_BASE_URL`。
- `EMBEDDING_MODEL`：Embedding 模型名称，上传文档和 embedding 检索时必须配置。
- `DATABASE_PATH`：SQLite 文件路径。相对路径会解释为 `backend/` 下的文件；Docker 中建议使用 `/app/data/app.db`。
- `CHROMA_PERSIST_DIR`：Chroma 本地持久化目录，默认 `./chroma_db`。
- `CHROMA_COLLECTION_NAME`：Chroma collection 名称。
- `RERANK_ENABLED`：是否启用 Rerank，默认 `true`。
- `RERANK_CANDIDATE_TOP_K`：Chroma 粗召回候选数量，默认 `20`。
- `RERANK_FINAL_TOP_K`：Rerank 后最终放入 Prompt 和返回前端的 sources 数量，默认 `5`。
- `RERANK_API_KEY`：专业 Rerank API Key；留空时依次复用 `EMBEDDING_API_KEY`、`LLM_API_KEY`。
- `RERANK_BASE_URL`：专业 Rerank API 地址；通用供应商可填类似 `https://api.siliconflow.cn/v1`，后端会请求 `/rerank`；DashScope 可填完整 rerank 服务地址。
- `RERANK_MODEL`：专业 Rerank 模型名称，例如 `BAAI/bge-reranker-v2-m3`。配置后会优先使用专业模型重排。
- `RERANK_API_FORMAT`：Rerank 请求格式，默认 `auto`；普通 `/rerank` 接口使用 `generic`，DashScope 地址会自动使用 `dashscope`。
- `RERANK_TIMEOUT`：Rerank API 请求超时时间，单位秒。
- `RERANK_USE_LLM`：专业 Rerank 不可用时，是否继续用大模型做轻量 rerank；默认 `false`，关闭时使用规则 fallback rerank。

缺少 embedding 配置不会影响后端启动；只有上传文档或调用 RAG 问答时，接口才会返回配置错误提示。

## 前端配置

参考 `frontend/.env.example`：

```env
VITE_API_BASE_URL=http://127.0.0.1:8001/api
```

字段说明：

- `VITE_API_BASE_URL`：前端请求后端 API 的基础地址。修改后需要重新启动 `npm run dev`；Docker 前端镜像构建时也会读取这个值。

## 启动后端

当前前端代码请求地址是：

```text
http://127.0.0.1:8001/api/chat
http://127.0.0.1:8001/api/chat/stream
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

## Docker 启动

先准备后端环境变量：

```powershell
Copy-Item backend\.env.example backend\.env
```

然后编辑 `backend/.env`，填写真实的 `LLM_*` 和 `EMBEDDING_MODEL`。

启动：

```powershell
docker compose up --build
```

访问：

```text
前端：http://localhost:5173
后端：http://127.0.0.1:8001/api/health
```

Docker Compose 会把后端数据挂载到：

```text
backend/data/
```

其中：

- SQLite：`backend/data/app.db`
- Chroma：`backend/data/chroma_db/`

停止服务：

```powershell
docker compose down
```

## API 说明

### 统一错误响应

普通 JSON 接口出错时，后端统一返回：

```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "document_id 不存在。",
    "details": null
  },
  "detail": "document_id 不存在。"
}
```

说明：

- `error.code`：稳定错误码，方便前端或测试判断错误类型。
- `error.message`：展示给用户的错误信息。
- `error.details`：参数校验等场景的附加信息。
- `detail`：兼容旧版前端读取逻辑。

流式 RAG 使用 NDJSON，错误格式为：

```json
{"type":"error","code":"CHROMA_ERROR","message":"Chroma 检索失败：..."}
```

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

### 流式聊天接口

```http
POST /api/chat/stream
Content-Type: application/json
```

请求体和普通聊天接口一致：

```json
{
  "message": "什么是 RAG？",
  "conversation_id": null
}
```

返回值不再是 JSON，而是 `text/plain` 文本流。后端会通过响应头返回当前会话 ID：

```text
X-Conversation-Id: 1
```

前端会用 `response.body.getReader()` 逐段读取文本 chunk，并把每个 chunk 追加到同一条 AI 消息里。流结束后，后端才会把完整 assistant 回答保存到 SQLite，不会把每个 chunk 都保存成一条 message。

### 历史会话列表

```http
GET /api/conversations
```

返回按 `updated_at` 倒序排列的会话摘要，不包含消息正文列表：

```json
[
  {
    "id": 1,
    "title": "什么是 RAG？",
    "created_at": "2026-06-02T10:00:00",
    "updated_at": "2026-06-02T10:05:00"
  }
]
```

### 会话消息

```http
GET /api/conversations/{conversation_id}/messages
```

返回某个会话下的全部 `user` 和 `assistant` 消息，按 `created_at` 正序排列：

```json
{
  "conversation_id": 1,
  "messages": [
    {
      "id": 1,
      "role": "user",
      "content": "什么是 RAG？",
      "created_at": "2026-06-02T10:00:00"
    },
    {
      "id": 2,
      "role": "assistant",
      "content": "RAG 是检索增强生成...",
      "created_at": "2026-06-02T10:00:10"
    }
  ]
}
```

### 上传 RAG 文档

```http
POST /api/rag/documents
Content-Type: multipart/form-data
```

支持 `.txt`、`.md`、`.markdown`、`.pdf`、`.docx`。TXT/Markdown 按 UTF-8 读取；PDF 使用 `pypdf` 提取可复制文本；DOCX 使用 `python-docx` 提取段落和表格文本。上传后统一按段落切分成 chunk，为每个 chunk 调用 embedding API，并把 chunk 文本、embedding 和 metadata 写入 Chroma；SQLite 保存 document 元信息、解析后的纯文本 `content` 和索引状态 `status`，用于后续重建索引。

当前不支持老式 `.doc`、扫描版 PDF OCR、Excel、PPT。上传不支持的文件会返回：

```text
当前仅支持 TXT、Markdown、PDF、DOCX 文件。
```

上传成功的关键标准是 chunks 和 embeddings 写入 Chroma 成功；摘要生成失败不会导致上传失败，只会把 `summary_status` 标记为 `failed`。

返回：

```json
{
  "document_id": 1,
  "filename": "RAG_NOTES.md",
  "file_type": "markdown",
  "chunk_count": 3,
  "summary_status": "ready",
  "summary_preview": "1. 文档主题：..."
}
```

### 批量上传 RAG 文档

```http
POST /api/rag/documents/batch
Content-Type: multipart/form-data
```

字段名固定为 `files`，可以一次提交多个文件。每个文件都会独立执行解析、chunk 切分、embedding 生成、SQLite 元信息保存和 Chroma 写入；单个文件失败不会影响其他文件。

返回：

```json
{
  "uploaded": [
    {
      "document_id": 1,
      "filename": "paper-a.pdf",
      "file_type": "pdf",
      "chunk_count": 12,
      "summary_status": "ready",
      "summary_preview": "1. 文档主题：..."
    }
  ],
  "failed": [
    {
      "filename": "legacy.doc",
      "error": "当前仅支持 TXT、Markdown、PDF、DOCX 文件。"
    }
  ]
}
```

### RAG 文档列表

```http
GET /api/rag/documents
```

返回按 `created_at` 倒序排列的文档摘要，不包含完整正文：

```json
[
  {
    "id": 1,
    "filename": "RAG_NOTES.md",
    "file_type": "markdown",
    "chunk_count": 3,
    "status": "ready",
    "summary_status": "ready",
    "summary_preview": "1. 文档主题：...",
    "created_at": "2026-06-03T10:00:00"
  }
]
```

`status` 常见值：

- `ready`：索引可用。
- `reindexing`：正在重建索引。
- `failed`：最近一次重建索引失败。

`summary_status` 常见值：

- `pending`：摘要待生成或正在生成。
- `ready`：摘要已生成。
- `failed`：摘要生成失败，文档索引仍可正常用于 RAG。

### 删除单个 RAG 文档

```http
DELETE /api/rag/documents/{document_id}
```

后端会先按 `metadata.document_id` 删除 Chroma 中该文档的所有 chunks / embeddings / metadata，再删除 SQLite 中的 document 记录。如果 Chroma 删除失败，SQLite 记录会保留，方便继续排查或重试。

返回：

```json
{
  "document_id": 1,
  "deleted": true,
  "message": "文档已删除，对应向量索引也已清理"
}
```

### 清空知识库

```http
DELETE /api/rag/documents
```

只清理知识库，不删除聊天历史。后端会删除并重建当前 Chroma collection，然后删除 SQLite 中所有 document 记录。

返回：

```json
{
  "deleted_documents": 10,
  "cleared_vector_store": true,
  "message": "知识库已清空"
}
```

### 重建文档索引

```http
POST /api/rag/documents/{document_id}/reindex
```

用于 chunk 策略调整、embedding 模型更换、metadata 格式更新或向量索引异常后的单文档重建。当前项目采用 `content` 方案：上传新文档时保存解析后的纯文本，重建时直接使用 `document.content` 重新切分、重新生成 embedding、清理旧 Chroma chunks 并写入新 chunks。

返回：

```json
{
  "document_id": 1,
  "filename": "paper1.pdf",
  "chunk_count": 42,
  "status": "ready",
  "message": "文档索引已重建"
}
```

旧文档如果 `content` 为空，会返回：

```text
该文档缺少原始内容，无法重建索引，请重新上传。
```

### 重新生成文档摘要

```http
POST /api/rag/documents/{document_id}/summary/regenerate
```

后端会读取 `document.content`，调用大模型重新生成结构化中文摘要，并更新 `summary`、`summary_status`、`summary_updated_at`。旧文档如果没有保存 `content`，会返回“该文档缺少原始文本，无法重新生成摘要，请重新上传。”。

返回：

```json
{
  "document_id": 1,
  "filename": "paper1.pdf",
  "summary": "1. 文档主题：...",
  "summary_status": "ready",
  "summary_updated_at": "2026-06-09T10:00:00",
  "message": "文档摘要已重新生成"
}
```

### 基于文档问答

```http
POST /api/rag/chat
Content-Type: application/json
```

```json
{
  "question": "chunk 是什么？",
  "document_id": 1,
  "conversation_id": null
}
```

兼容旧的单文档请求，也支持新的多文档范围：

```json
{
  "question": "哪些论文适合我的课题？",
  "document_ids": [1, 2, 3, 4, 5],
  "conversation_id": null
}
```

规则：

- `document_ids` 优先级高于 `document_id`。
- `document_ids` 有值时，只检索这些文档。
- `document_ids: []` 或不传 `document_id` / `document_ids` 时，检索全部已上传文档。
- Rerank 开启时，后端先按 `RERANK_CANDIDATE_TOP_K` 粗召回，再取 `RERANK_FINAL_TOP_K` 个 reranked sources。
- Rerank 关闭时，单文档默认取 top 5 chunks；多文档或全部文档默认取 top 10 chunks。
- `document_ids` 中存在无效 ID 时，后端返回清晰错误。

后端会为问题生成 embedding，从 Chroma 按文档范围检索 candidate chunks，执行 rerank，拼接 RAG Prompt，再调用聊天模型。Prompt 中使用的 sources 和返回给前端展示的 sources 是同一批 reranked sources。返回：

```json
{
  "conversation_id": 1,
  "answer": "根据参考资料，chunk 是文档的一小段...",
  "sources": [
    {
      "document_id": 1,
      "filename": "RAG_NOTES.md",
      "file_type": "markdown",
      "chunk_index": 1,
      "content": "A chunk is a small piece of a document...",
      "score": 0.8234,
      "rerank_score": 0.9034,
      "rerank_reason": "规则重排：原始相似度较高，并命中问题关键词。"
    }
  ]
}
```

### 基于文档流式问答

```http
POST /api/rag/chat/stream
Content-Type: application/json
```

请求体和普通 RAG 问答一致，支持 `document_id` 和 `document_ids`：

```json
{
  "question": "RAG 和向量数据库是什么关系？",
  "document_ids": [],
  "conversation_id": null
}
```

返回值是 NDJSON 文本流，每一行都是一个 JSON 对象，`media_type` 为：

```text
application/x-ndjson; charset=utf-8
```

第一行返回 metadata，包含会话 ID 和 sources：

```json
{"type":"metadata","conversation_id":1,"sources":[{"document_id":1,"filename":"RAG_NOTES.md","file_type":"markdown","chunk_index":1,"content":"A chunk is a small piece of a document...","score":0.8234,"rerank_score":0.9034,"rerank_reason":"规则重排：原始相似度较高，并命中问题关键词。"}]}
```

后续逐步返回回答片段：

```json
{"type":"chunk","content":"RAG "}
{"type":"chunk","content":"会先检索相关片段，"}
{"type":"done"}
```

如果出错，会返回：

```json
{"type":"error","message":"错误说明"}
```

当前前端在打开“基于文档回答”时会使用这个流式 RAG 接口；如果勾选了多个文档，前端传 `document_ids`，如果没有勾选具体文档，前端传 `document_ids: []` 让后端检索全部文档。sources 会先显示在 AI 消息下方，回答文本随后逐步追加。sources 顺序按后端 rerank 后的顺序展示，前端不做二次排序。流结束后，后端只保存一条完整 assistant message，不会把每个 chunk 都保存成一条消息。

## 数据库

数据库文件位置：

```text
backend/app.db
```

当前 SQLite 主要使用三张业务表：

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
- `document`
  - `id`
  - `filename`
  - `file_type`
  - `chunk_count`
  - `chroma_collection`
  - `status`
  - `content`
  - `summary`
  - `summary_status`
  - `summary_updated_at`
  - `created_at`
  - `updated_at`

`content` 保存解析后的纯文本，用于后续重建索引和重新生成摘要；历史旧文档如果该字段为空，需要重新上传后才能重建索引或生成摘要。`summary` 保存文档摘要缓存，多文档论文分析时用于理解整篇文档的整体方向；具体回答依据仍然来自 reranked sources。`document_chunk` 是旧版 RAG 遗留表，新版 Chroma RAG 不再使用它作为检索来源。

Chroma 持久化目录：

```text
backend/chroma_db
```

Chroma 保存：

- chunk 文本；
- chunk embedding；
- `document_id`、`filename`、`file_type`、`chunk_index`、`created_at` metadata。

注意：旧版本已经写入 Chroma 的 chunk 可能没有 `filename` 或 `file_type`，本次改造不强制迁移旧数据；重新上传或重建索引后会写入完整 metadata。

## 日志

后端日志输出到启动后端的终端或 Docker logs。日志级别由 `LOG_LEVEL` 控制。

本项目会记录：

- HTTP 请求开始和结束：method、path、status、duration、request id；
- RAG 问题摘要、`document_ids`、sources 数量；
- Embedding 调用耗时和批量大小；
- Chroma 写入、查询、删除、清空耗时；
- LLM 普通和流式调用耗时；
- 异常堆栈。

不会记录：

- API Key；
- Authorization header；
- 完整请求体；
- 完整文档内容。

Docker 查看日志：

```powershell
docker compose logs -f backend
```

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

测试流式接口：

```powershell
cd backend
$env:PYTHONIOENCODING='utf-8'
@'
import requests

url = "http://127.0.0.1:8001/api/chat/stream"
payload = {"message": "What is RAG? Answer in one short sentence.", "conversation_id": None}

with requests.post(url, json=payload, stream=True, timeout=120) as response:
    print("status =", response.status_code)
    print("conversation_id =", response.headers.get("X-Conversation-Id"))
    response.raise_for_status()

    for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
        if chunk:
            print(chunk, end="", flush=True)
'@ | .\.venv\Scripts\python.exe -
```

测试上传 RAG 文档：

```powershell
cd backend
$sample = Join-Path $env:TEMP "RAG_NOTES.md"
@"
# RAG Notes

RAG means Retrieval-Augmented Generation.

A chunk is a small piece of a document.
"@ | Set-Content -LiteralPath $sample -Encoding UTF8

@'
import os
import requests

path = os.path.join(os.environ["TEMP"], "RAG_NOTES.md")
with open(path, "rb") as file:
    response = requests.post(
        "http://127.0.0.1:8001/api/rag/documents",
        files={"file": ("RAG_NOTES.md", file, "text/markdown")},
        timeout=30,
    )
print(response.status_code)
print(response.text)
'@ | .\.venv\Scripts\python.exe -
```

测试基于文档问答：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8001/api/rag/chat `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"question":"chunk 是什么？","document_id":1}'
```

测试批量上传 RAG 文档：

```powershell
cd backend
$sample1 = Join-Path $env:TEMP "paper-a.md"
$sample2 = Join-Path $env:TEMP "paper-b.md"
"Paper A discusses RAG evaluation and retrieval quality." | Set-Content -LiteralPath $sample1 -Encoding UTF8
"Paper B discusses embedding models and vector databases." | Set-Content -LiteralPath $sample2 -Encoding UTF8

@'
import os
import requests

paths = [
    os.path.join(os.environ["TEMP"], "paper-a.md"),
    os.path.join(os.environ["TEMP"], "paper-b.md"),
]
files = [
    ("files", (os.path.basename(path), open(path, "rb"), "text/markdown"))
    for path in paths
]
try:
    response = requests.post(
        "http://127.0.0.1:8001/api/rag/documents/batch",
        files=files,
        timeout=120,
    )
    print(response.status_code)
    print(response.text)
finally:
    for _, file_tuple in files:
        file_tuple[1].close()
'@ | .\.venv\Scripts\python.exe -
```

测试多文档 RAG 问答：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8001/api/rag/chat `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"question":"哪些资料适合研究 RAG 检索质量？","document_ids":[1,2]}'
```

测试全部文档 RAG 问答：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8001/api/rag/chat `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"question":"这些资料整体在讨论什么？","document_ids":[]}'
```

验证 SQLite 只保存一条完整 assistant 消息：

```powershell
cd backend
@'
import sqlite3

conversation_id = 1
conn = sqlite3.connect("app.db")
rows = conn.execute(
    """
    select role, count(*) as count
    from message
    where conversation_id = ?
    group by role
    """,
    (conversation_id,),
).fetchall()
print(rows)
conn.close()
'@ | .\.venv\Scripts\python.exe -
```

检查前端：

1. 启动后端 `8001`。
2. 启动前端 `5173`。
3. 打开 `http://localhost:5173`。
4. 左侧应显示历史会话列表。
5. 点击任意历史会话，右侧应加载该会话消息。
6. 输入消息并点击“发送”，AI 回复应逐步显示。
7. 点击“新建会话”，右侧清空；再次提问后左侧会出现新会话。
8. 在主聊天窗口批量选择多个 TXT/Markdown/PDF/DOCX 文件上传，上传成功后工具栏应显示 uploaded / failed 结果。
9. 打开“基于文档回答”，勾选多个文档后提问，sources 应显示来自不同文档的片段。
10. 清空文档勾选后继续提问，前端会传 `document_ids: []`，后端默认检索全部已上传文档。
11. 点击单个文档的“重建索引”，成功后 chunk 数和状态应刷新。
12. 查看文档列表中的 `summary_status`，摘要生成成功时应显示“摘要已生成”，失败时不影响文档问答。
13. 点击单个文档的“生成摘要”，成功后摘要状态和摘要预览应刷新。
14. 打开“基于文档回答”并提问，回答下方 sources 应显示 `score`；如果启用 Rerank，可能显示 `rerank` 分数。
15. 点击单个文档的“删除”，成功后该文档从列表和已选范围中移除。
16. 点击“清空知识库”，文档列表应清空，聊天历史仍保留。

## 演示流程

1. 启动后端 `8001` 和前端 `5173`。
2. 在主聊天窗口批量上传 10 篇论文，检查工具栏里的成功和失败结果。
3. 打开“基于文档回答”。
4. 勾选其中几篇论文，提问“哪些论文适合我的课题？为什么？”。
5. 查看文档列表中的摘要状态，确认摘要已生成或失败时有清晰状态。
6. 查看回答下方 sources，确认来源包含 `filename`、`file_type`、chunk 序号、score 和可选 rerank 分数。
7. 点击某篇论文的“生成摘要”，确认列表中摘要状态刷新。
8. 点击某篇论文的“重建索引”，确认列表中 chunk 数和状态刷新。
9. 点击“清空选择”或“全部文档”，继续提问“这些论文整体分成哪些主题？”。
10. 删除一篇测试文档后再次提问，sources 不应再返回该文档。
11. 左侧历史会话中应能看到本轮 RAG 对话；点击历史会话可以重新加载消息。

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

### 4. 提示缺少 embedding 配置

RAG 上传和检索必须配置 `EMBEDDING_MODEL`。如果 Embedding API 和大模型 API 使用同一个服务，可以只填写：

```env
LLM_API_KEY=真实 API Key
LLM_BASE_URL=模型服务基础地址
LLM_MODEL=聊天模型名称
EMBEDDING_MODEL=embedding 模型名称
```

如果 Embedding 使用另一个服务，再单独填写：

```env
EMBEDDING_API_KEY=真实 Embedding API Key
EMBEDDING_BASE_URL=Embedding 服务基础地址
```

### 5. Embedding API 返回 404

检查 `EMBEDDING_BASE_URL` 是否只到 `/v1` 这一层，不要写成 `/v1/embeddings`。代码会自动请求 `{EMBEDDING_BASE_URL}/embeddings`。

### 6. Embedding API 返回 batch size is invalid

部分 Embedding 服务要求单次 input 不能超过 10 条。当前 `embedding_service.py` 已按 10 条一批请求；如果仍报错，确认你运行的是最新代码并重启后端。

### 7. Chroma 报向量维度不一致

如果出现类似 `Collection expecting embedding with dimension of 3, got 1024`，说明旧 Chroma collection 的向量维度和当前 `EMBEDDING_MODEL` 不一致。处理方式：

- 没有重要旧数据：删除 `backend/chroma_db` 后重启后端并重新上传文档。
- 想保留旧数据：修改 `CHROMA_COLLECTION_NAME` 使用一个新 collection，再重新上传文档。

### 8. 重建索引提示缺少原始内容

当前项目使用 `document.content` 保存解析后的纯文本。旧版本上传的文档可能没有保存 `content`，因此无法直接重建索引。处理方式：

- 重新上传该文档；
- 或清空知识库后重新上传全部文档。

### 9. 清空知识库后历史会话还在

这是当前设计。知识库清空只删除 `document` 和 Chroma collection，不删除 `conversation` / `message`，因为聊天历史和知识库是两类数据。

### 10. Rerank 没有调用专业模型或大模型

默认配置是：

```env
RERANK_ENABLED=true
RERANK_MODEL=
RERANK_USE_LLM=false
```

这表示启用 Rerank 流程，但没有配置专业 Rerank 模型，也不额外调用大模型，因此会使用规则 Rerank。规则 Rerank 会结合 Chroma `score` 和用户问题关键词给 chunks 重新排序。

如果要启用专业 Rerank 模型，可以设置：

```env
RERANK_MODEL=BAAI/bge-reranker-v2-m3
RERANK_BASE_URL=https://api.siliconflow.cn/v1
RERANK_API_KEY=你的-rerank-api-key
```

如果专业 Rerank API 调用失败，系统会自动回退。如果还想启用 LLM Rerank 作为第二层兜底，可以设置：

```env
RERANK_USE_LLM=true
```

LLM Rerank 会多一次大模型调用，用于返回排序 JSON；如果 JSON 解析失败或模型调用失败，会自动回退到规则 Rerank。

### 11. 摘要生成失败怎么办

摘要生成失败不会影响文档上传和 RAG 检索。文档列表会显示 `summary_status=failed`，可以点击“生成摘要”重新生成。如果旧文档没有 `content`，需要重新上传该文档。

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

GitHub Actions：

```text
.github/workflows/ci.yml
```

CI 会在 push 和 pull request 时运行：

- `backend`: `python -m pytest -q`
- `frontend`: `npm run lint`
- `frontend`: `npm run build`

更多上传 GitHub 前的整理说明见：

```text
docs/GITHUB_PROJECT_GUIDE.md
```

## 后续计划

- 增加前端自动化测试或 Playwright 端到端测试。
- 按需增加本地 cross-encoder rerank，支持离线部署。
- 增加用户体系和多用户知识库隔离。
- 增加 Alembic 数据库迁移。
- 增加生产级 Nginx 反向代理和 HTTPS 部署说明。
