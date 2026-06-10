# Bug 修复与测试报告

## 1. 本次检查范围

后端：

- `backend/app/main.py`
- `backend/app/api/`
- `backend/app/services/`
- `backend/app/core/`
- `backend/app/db/`
- `backend/app/schemas/`
- `backend/requirements.txt`

前端：

- `frontend/src/`
- `frontend/src/api/`
- `frontend/src/components/`
- `frontend/src/App.css`
- `frontend/src/index.css`

文档：

- `README.md`
- `docs/`

说明：当前项目没有 `backend/app/models/` 和 `frontend/src/styles/` 目录。ORM 模型定义在 `backend/app/db/database.py`，样式在 `frontend/src/App.css` 和 `frontend/src/index.css`。

## 2. 发现的问题

1. CORS 只允许 `http://localhost:5173`，如果前端使用 `http://127.0.0.1:5173` 或 Vite 自动切换端口，会出现跨域失败。
2. 前端 API base URL 分散在多个文件里，后续修改后端端口时容易漏改。
3. 普通流式聊天接口失败时，前端直接显示原始响应文本；FastAPI JSON 错误不够友好。
4. `ChatRequest.message` 和 `RagChatRequest.question` 只校验 `min_length=1`，空白字符串可能绕过 schema。
5. 项目没有后端 pytest 测试目录。
6. `requirements.txt` 未声明 `pytest`，新环境无法直接运行后端测试。
7. 项目没有前端自动化测试框架，也没有手动测试清单。
8. 项目没有稳定性修复与测试报告文档。
9. 当前没有删除文档接口，因此“删除文档时 SQLite 和 Chroma 同步”暂时无法自动化验证。

## 3. 已修复的问题

1. CORS 改为允许本地 `localhost` 和 `127.0.0.1` 任意端口，覆盖常见 Vite 开发端口。
2. 新增 `frontend/src/api/config.js`，集中维护 `API_BASE_URL`。
3. `chatApi.js`、`conversationApi.js`、`ragApi.js` 统一引用 `API_BASE_URL`。
4. 普通流式聊天失败时，前端优先解析 FastAPI JSON 错误中的 `detail`。
5. `ChatRequest.message` 增加空白字符串校验，并返回去掉首尾空白后的消息。
6. `RagChatRequest.question` 增加空白字符串校验，并返回去掉首尾空白后的问题。
7. 新增后端 pytest 测试，覆盖 health、文档解析、文本切分、Prompt、RAG 请求校验。
8. 新增前端手动测试清单。

## 4. 修改文件列表

- `backend/app/main.py`
- `backend/app/schemas/chat_schema.py`
- `backend/app/schemas/rag_schema.py`
- `backend/requirements.txt`
- `backend/tests/conftest.py`
- `backend/tests/test_health.py`
- `backend/tests/test_document_parser.py`
- `backend/tests/test_text_splitter.py`
- `backend/tests/test_prompt.py`
- `backend/tests/test_rag_request_validation.py`
- `frontend/src/api/config.js`
- `frontend/src/api/chatApi.js`
- `frontend/src/api/conversationApi.js`
- `frontend/src/api/ragApi.js`
- `frontend/TEST_CHECKLIST.md`
- `docs/BUG_FIX_AND_TEST_REPORT.md`

## 5. 新增测试列表

### `backend/tests/test_health.py`

- 测试 `GET /api/health` 返回 `{"status": "ok"}`。

### `backend/tests/test_document_parser.py`

- 测试 TXT 解析。
- 测试 Markdown 解析。
- 测试不支持文件类型错误。
- 测试空上传文件会在 RAG 入库前返回清晰错误。
- 测试 DOCX 解析。

### `backend/tests/test_text_splitter.py`

- 测试普通文本切分。
- 测试空文本返回空 chunk 列表。
- 测试超长文本会被切分，且单个 chunk 不超过上限。

### `backend/tests/test_prompt.py`

- 测试 source 格式包含文档名、文档ID、文件类型、chunk_index、score。
- 测试多文档论文分析 Prompt 包含 source 元信息。
- 测试无上下文时 Prompt 包含资料不足提示。

### `backend/tests/test_rag_request_validation.py`

- 测试空白 question 被拒绝。
- 测试 `document_ids=[]` 且存在文档时解析为检索全部文档。
- 测试 `document_ids=[]` 且没有文档时返回清晰错误。
- 测试无效 `document_ids` 返回清晰错误。

## 6. 后端测试命令

```powershell
cd backend
.\.venv\Scripts\python.exe -m compileall app tests
.\.venv\Scripts\python.exe -m pytest
```

本次运行结果：

- `compileall app tests`：通过。
- `pytest`：16 passed，1 warning。

warning：

- `fastapi.testclient` 提示 Starlette TestClient 依赖的 httpx 用法有 deprecation warning。当前不影响测试通过，后续可根据 FastAPI/Starlette 版本升级建议调整依赖。

## 7. 前端测试命令

```powershell
cd frontend
npm run lint
npm run build
```

本次运行结果：

- `npm run lint`：通过。
- `npm run build`：通过。

## 8. 手动测试清单

详见：

```text
frontend/TEST_CHECKLIST.md
```

重点覆盖：

1. 普通聊天。
2. 流式聊天。
3. 文档上传。
4. PDF 上传。
5. DOCX 上传。
6. 多文档选择。
7. 全部文档 RAG。
8. 流式 RAG。
9. 历史会话。
10. 新建会话。
11. sources 展示。
12. 页面滚动固定布局。
13. 错误提示。
14. loading 状态。

## 9. 仍然存在的问题

1. 没有删除文档接口，因此无法验证删除文档时 SQLite 和 Chroma 的同步清理。
2. PDF 解析没有新增自动化 PDF 构造测试；当前通过 `document_parser.py` 的错误分支和手动测试清单覆盖。
3. RAG 上传、RAG 问答、流式 RAG 的真实链路依赖外部 Embedding API、大模型 API 和 Chroma，本次自动化测试使用 mock/纯函数/临时 SQLite，未调用真实外部服务。
4. 前端仍未引入自动化测试框架；当前以 lint、build 和手动测试清单作为最小验证。
5. `requirements.txt` 中部分依赖版本约束可能需要后续统一整理；本次仅补充测试运行所需的 `pytest` 和 `httpx`。

## 10. 下一步建议

1. 增加文档删除接口，并在 service 层保证 SQLite 删除和 Chroma chunk 删除在失败时有清晰处理。
2. 给 `llm_service.py` 和 `embedding_service.py` 增加 requests mock 测试，覆盖 404、400、非 JSON、空 choices/data 等错误。
3. 给 RAG 流式 NDJSON 增加后端 generator 单元测试，验证 metadata/chunk/done/error 顺序。
4. 如果项目继续扩大，考虑给前端增加轻量组件测试或 Playwright 端到端测试。
5. 整理后端依赖版本，避免未来 FastAPI、Starlette、httpx 组合出现兼容性警告。

## 11. 当前补充说明

后续迭代已经补充了知识库维护能力：

- 删除单个文档：`DELETE /api/rag/documents/{document_id}`。
- 清空知识库：`DELETE /api/rag/documents`。
- 重建文档索引：`POST /api/rag/documents/{document_id}/reindex`。
- 新上传文档会保存解析后的 `document.content`，用于后续重建索引。
- `document.status` 用于展示索引维护状态：`ready`、`reindexing`、`failed`。

因此本报告第 2、9、10 节中关于“尚无删除文档接口”的描述是当时检查阶段的历史记录，不代表当前项目状态。当前知识库维护链路请以 `README.md`、`docs/chat_flow.md` 和 `docs/rag_operations.md` 为准。

## 12. RAG 优化补充说明

本次迭代已补充：

- Rerank 检索重排：默认规则 Rerank，可配置 LLM Rerank。
- 文档摘要缓存：上传后尝试生成摘要，失败不影响文档上传。
- 重新生成摘要接口：`POST /api/rag/documents/{document_id}/summary/regenerate`。
- 多文档论文分析 Prompt：结合 document summary 和 reranked sources。
- 前端展示：文档列表显示摘要状态和摘要预览；sources 显示可选 rerank 分数。

新增自动化测试：

- `backend/tests/test_rerank.py`
- `backend/tests/test_summary.py`

本次验证：

- `python -m compileall app tests`：通过。
- `python -m pytest -q`：37 passed，1 warning。
- `npm run lint`：通过。
- `npm run build`：通过。

## 13. 工程化补充说明

本次进一步补充工程化能力：

- 统一错误处理：新增 `AppException`、错误码和全局异常处理器。
- 统一错误响应：普通接口返回 `error.code/error.message/error.details`，并保留 `detail` 兼容旧前端。
- 请求日志：记录 HTTP 请求开始、结束、状态码、耗时和 request id。
- 外部依赖日志：记录 Embedding、Chroma、LLM 调用耗时，不记录 API Key。
- 配置管理：新增 `LOG_LEVEL`、`DATABASE_PATH`、`STRICT_CONFIG_VALIDATION` 和 `frontend/.env.example`。
- Docker：新增后端/前端 Dockerfile 和 `docker-compose.yml`，数据挂载到 `backend/data/`。
- GitHub：新增 `.github/workflows/ci.yml` 和 `docs/GITHUB_PROJECT_GUIDE.md`。

新增测试：

- `backend/tests/test_error_handling.py`
