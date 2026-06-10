# RAG 知识库维护说明

本文整理当前项目中和知识库维护及检索优化相关的操作：删除单个文档、清空知识库、重建文档索引、文档摘要缓存、Rerank 检索重排。

## 数据存储边界

SQLite 的 `document` 表保存：

- `filename`：上传文件名；
- `file_type`：解析后的文件类型；
- `chunk_count`：当前索引中的 chunk 数；
- `chroma_collection`：写入的 Chroma collection 名称；
- `status`：索引状态，常见值为 `ready`、`reindexing`、`failed`；
- `content`：解析后的纯文本，用于后续重建索引。
- `summary`：文档摘要缓存，用于多文档论文分析的整体理解；
- `summary_status`：摘要状态，常见值为 `pending`、`ready`、`failed`；
- `summary_updated_at`：摘要最近更新时间。

Chroma collection 保存：

- chunk 文本；
- chunk embedding；
- metadata：`document_id`、`filename`、`file_type`、`chunk_index`、`created_at`。

Rerank 不单独存储数据，它只对本次 Chroma 粗召回 sources 重新排序，并把 `rerank_score` 和 `rerank_reason` 放回本次响应。

`conversation` 和 `message` 是聊天历史，不属于知识库维护范围。

## 删除单个文档

接口：

```http
DELETE /api/rag/documents/{document_id}
```

流程：

1. `rag_service.delete_document()` 检查 SQLite 中是否存在该文档。
2. `chroma_service.delete_document_chunks()` 按 `metadata.document_id` 删除 Chroma 中该文档的 chunks。
3. Chroma 删除成功后，删除 SQLite 中的 document 记录。
4. 前端刷新文档列表，并从 `selectedDocumentIds` 移除该 ID。

一致性原则：

- Chroma 删除失败时，不继续删除 SQLite document，避免文档列表消失但向量仍残留。

## 清空知识库

接口：

```http
DELETE /api/rag/documents
```

流程：

1. `rag_service.clear_knowledge_base()` 统计当前 document 数量。
2. `chroma_service.clear_collection()` 删除当前 collection 并重建空 collection。
3. 清空 SQLite 中所有 document 记录。
4. 前端清空 `documents`、`selectedDocumentIds`，并关闭 RAG 开关。

一致性原则：

- 清空知识库不删除 `conversation` 和 `message`。
- Chroma 清空失败时，不继续删除 SQLite document。

## 重建文档索引

接口：

```http
POST /api/rag/documents/{document_id}/reindex
```

流程：

1. 检查文档是否存在。
2. 检查 `document.content` 是否有解析后的纯文本。
3. 将 `status` 更新为 `reindexing`。
4. 使用当前 `split_text_into_chunks()` 重新切分文本。
5. 使用当前 `embedding_service.get_embeddings()` 重新生成 embedding。
6. 删除该文档在 Chroma 中的旧 chunks。
7. 写入新的 chunks、embeddings 和 metadata。
8. 更新 SQLite 的 `chunk_count`、`chroma_collection`、`status=ready`、`updated_at`。

失败处理：

- 旧文档 `content` 为空：直接返回“该文档缺少原始内容，无法重建索引，请重新上传。”。
- embedding 失败：不删除旧 Chroma chunks，并将状态标记为 `failed`。
- Chroma 写入失败：状态标记为 `failed`，需要重新上传或再次重建。

## 文档摘要缓存

上传新文档时，文档 chunks 写入 Chroma 成功后，`rag_service.create_document()` 会调用 `summary_service.generate_document_summary()` 生成摘要。

状态规则：

- 生成前：`summary_status=pending`。
- 生成成功：保存 `summary`，设置 `summary_status=ready` 和 `summary_updated_at`。
- 生成失败：设置 `summary_status=failed`，但文档上传仍然成功。

重新生成接口：

```http
POST /api/rag/documents/{document_id}/summary/regenerate
```

流程：

1. 检查 document 是否存在。
2. 检查 `document.content` 是否存在。
3. 设置 `summary_status=pending`。
4. 调用大模型生成摘要。
5. 成功后更新 `summary`、`summary_status=ready`、`summary_updated_at`。
6. 失败时设置 `summary_status=failed` 并返回错误。

旧文档如果 `content` 为空，需要重新上传后才能生成摘要。

## Rerank 检索重排

RAG 问答当前流程：

```text
用户问题
  ↓
question embedding
  ↓
Chroma 粗召回 RERANK_CANDIDATE_TOP_K 个 candidate sources
  ↓
rerank_service.rerank_sources()
  ↓
取 RERANK_FINAL_TOP_K 个 final sources
  ↓
Prompt 和前端 sources 使用同一批 final sources
```

默认配置：

```env
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

配置 `RERANK_MODEL` 后，后端会优先调用专业 rerank API。通用供应商可把 `RERANK_BASE_URL` 配成类似 `https://api.siliconflow.cn/v1`，后端会请求 `/rerank`；DashScope rerank 服务地址会自动使用 DashScope 请求格式。

未配置专业 rerank 模型，或专业 API 调用失败时，会回退到规则 Rerank：

- 优先使用 Chroma 转换后的 `score`，越大越相关；
- 如果只有 `distance`，按距离换算分数；
- 命中用户问题关键词的 chunk 会加分；
- 返回 sources 中包含 `rerank_score` 和 `rerank_reason`。

如果设置 `RERANK_USE_LLM=true`，专业 rerank 不可用时系统会先让大模型只返回排序 JSON，不让它回答用户问题。LLM Rerank 出错、JSON 解析失败或返回空结果时，会自动回退到规则 Rerank。

## 多文档论文分析上下文

当问题命中“论文、课题、适合、创新点、借鉴、启发、对比、方法、技术路线、AS-OCT、少样本、分割、关键点”等关键词时，使用多文档论文分析 Prompt。

该 Prompt 会同时使用：

- 文档摘要：用于理解文档整体方向；
- reranked sources：用于具体回答依据。

摘要不会替代 sources。如果摘要为空，系统会跳过该文档摘要，不影响 RAG 问答。

## 手动测试建议

1. 上传一个 Markdown 文档。
2. 查看文档列表，确认 `status=ready`，并显示 chunk 数。
3. 开启“基于文档回答”，基于该文档提问，确认返回 sources。
4. 点击“重建索引”，确认弹出二次确认。
5. 重建完成后刷新列表，确认 chunk 数和状态正常。
6. 再次基于该文档提问，确认仍然返回 sources。
7. 查看摘要状态，确认 `summary_status=ready` 或失败时能显示 `failed`。
8. 点击“生成摘要”，确认摘要状态和摘要预览刷新。
9. 基于多个文档提问，确认 sources 中包含 `rerank_score`。
10. 删除该文档，确认文档列表中消失。
11. 清空知识库，确认文档列表为空，但历史会话仍可打开。

## 扩展方向

- 批量重建索引：遍历 document 列表逐个调用当前 `reindex_document()`，返回 uploaded/failed 类似的明细。
- 批量重新生成摘要：遍历 document 列表逐个调用当前 `regenerate_document_summary()`。
- 专业 rerank 模型：当前已支持供应商 rerank API，后续可继续扩展为本地 cross-encoder。
- 上传原始文件保存：如果需要重新解析 PDF/DOCX，可新增 `file_path` 字段并保存原始文件。
- 操作审计：为删除、清空、重建记录操作者、时间和失败原因。
