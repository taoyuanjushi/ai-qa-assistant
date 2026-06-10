# RAG 优化说明

本文记录当前项目新增的 Rerank 和文档摘要缓存能力。

## Rerank 流程

当前 RAG 检索流程：

```text
question
  ↓
embedding_service.get_embedding()
  ↓
chroma_service.search_chroma(top_k=RERANK_CANDIDATE_TOP_K)
  ↓
rerank_service.rerank_sources()
  ↓
取 RERANK_FINAL_TOP_K 个 sources
  ↓
Prompt 和前端展示使用同一批 sources
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

## 专业 Rerank 模型

配置 `RERANK_MODEL`、`RERANK_BASE_URL` 和 `RERANK_API_KEY` 后，后端会优先调用专业 rerank API 对 Chroma 粗召回结果重排。

通用 `/rerank` 接口示例：

```env
RERANK_MODEL=BAAI/bge-reranker-v2-m3
RERANK_BASE_URL=https://api.siliconflow.cn/v1
RERANK_API_KEY=replace-with-your-rerank-api-key
RERANK_API_FORMAT=auto
```

后端会发送 `query`、`documents`、`top_n`，并解析 `results[].index` 和 `results[].relevance_score`。如果 `RERANK_BASE_URL` 是 DashScope rerank 服务地址，`RERANK_API_FORMAT=auto` 会自动改用 DashScope 的 `input` / `parameters` 请求格式。

专业 rerank API 调用失败、返回非 JSON、没有有效排序结果时，会自动回退到 LLM Rerank 或规则 Rerank，保证 RAG 问答仍可用。

## 规则 Rerank

未配置专业 rerank 模型时，默认使用规则 Rerank，不额外调用大模型。

排序依据：

- `score`：Chroma cosine distance 已在后端转换为越大越相关的 score；
- `distance`：如果缺少 score，则按距离换算；
- keyword boost：命中用户问题关键词的 chunk 会加分。

返回 sources 会带上：

- `score`：Chroma 相似度分数；
- `rerank_score`：重排后的分数；
- `rerank_reason`：重排原因。

## LLM Rerank

设置 `RERANK_USE_LLM=true` 后，会让大模型只返回排序 JSON，不回答用户问题。

如果出现以下情况，会自动回退到规则 Rerank：

- 大模型请求失败；
- 返回内容不是合法 JSON；
- `source_index` 无法匹配候选 source；
- 返回空排序结果。

## 文档摘要缓存

上传文档时，chunks 写入 Chroma 成功后，会尝试生成文档摘要。

状态：

- `pending`：待生成或正在生成；
- `ready`：摘要已生成；
- `failed`：摘要生成失败。

摘要失败不影响上传成功。多文档论文分析时，Prompt 会加入当前 reranked sources 涉及文档的摘要。

## 多文档论文分析上下文

论文分析类问题会使用：

- 文档摘要：帮助模型理解每篇文档整体方向；
- reranked sources：作为具体回答依据。

Prompt 明确要求摘要不能替代 sources，避免模型只根据摘要下结论。

## 当前限制

- 专业 Rerank 依赖供应商 API 的请求格式和返回字段；当前内置支持通用 `/rerank` 与 DashScope 风格。
- LLM Rerank 依赖模型稳定返回 JSON。
- 摘要只基于 `document.content` 的前 12000 字符生成，超长论文可能遗漏后文信息。
- 旧文档如果没有 `content`，无法重新生成摘要，需要重新上传。

## 后续扩展

- 如果要离线部署，可继续把 `rerank_service.py` 扩展为本地 cross-encoder。
- 为摘要增加关键词、研究任务、方法、贡献等结构化字段。
- 支持批量重新生成摘要。
- 保存原始文件路径，允许重新解析 PDF/DOCX 后生成摘要。
