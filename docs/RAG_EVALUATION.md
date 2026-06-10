# RAG 评估清单

本文用于验证 Rerank 和文档摘要缓存是否改善多文档 RAG 效果。

## 测试 1：普通 RAG 不受影响

1. 上传一个 TXT 或 Markdown 文档。
2. 打开“基于文档回答”。
3. 提问普通问题。
4. 检查回答包含 `answer + sources`。
5. 检查 sources 正常显示，不报错。

## 测试 2：Rerank 生效

1. 上传多个主题不同的文档。
2. 提问一个带明确关键词的问题。
3. 检查后端日志中的 candidate 数量和 final 数量。
4. 检查返回 sources 是否包含 `rerank_score`。
5. 检查前端 sources 顺序是否和后端返回顺序一致。

## 测试 3：Rerank fallback

1. 配置 `RERANK_MODEL` 后模拟专业 rerank API 返回错误，确认 RAG 仍然可用。
2. 保持 `RERANK_USE_LLM=false`，验证系统会回退到规则 Rerank。
3. 或设置 `RERANK_USE_LLM=true` 并模拟模型返回非法 JSON。
4. 系统应最终回退到规则 Rerank，RAG 问答仍然可用。

## 测试 4：摘要生成

1. 上传新文档。
2. 查看文档列表中的 `summary_status`。
3. 成功时应显示“摘要已生成”并显示摘要预览。
4. 失败时应显示“摘要失败”，但文档仍然可以用于 RAG。

## 测试 5：摘要失败不影响上传

1. 临时移除 LLM 配置或模拟摘要服务失败。
2. 上传文档。
3. 确认 chunks 正常写入 Chroma。
4. 确认 document 记录存在。
5. 确认 `summary_status=failed`。

## 测试 6：重新生成摘要

1. 点击文档列表中的“生成摘要”。
2. 后端调用 `POST /api/rag/documents/{document_id}/summary/regenerate`。
3. 成功后刷新文档列表。
4. 检查摘要状态和摘要预览更新。

## 测试 7：多文档论文分析

提问：

```text
我的课题是 AS-OCT 少样本结构分割与 SS/IR 关键点检测，这些论文中哪些适合？分别能借鉴什么？
```

检查：

- Prompt 使用多文档论文分析模板；
- Prompt 包含文档摘要；
- Prompt 包含 reranked sources；
- 回答按文档分别分析；
- sources 和回答依据能对齐；
- 不把不同文档的方法、贡献、实验结果混在一起。

## 测试 8：原功能回归

确认以下功能仍然可用：

- 普通聊天；
- 流式聊天；
- 普通 RAG；
- 流式 RAG；
- 文档上传；
- 删除文档；
- 清空知识库；
- 重建索引；
- 历史会话。

## 评估记录建议

记录每次测试的：

- 问题；
- `RERANK_CANDIDATE_TOP_K`；
- `RERANK_FINAL_TOP_K`；
- 是否配置专业 Rerank 模型；
- 是否开启 LLM Rerank fallback；
- 返回 sources 的 `score`；
- 返回 sources 的 `rerank_score`；
- 摘要是否参与 Prompt；
- 回答是否基于 sources；
- 是否出现多文档混淆；
- 摘要和 sources 是否互相矛盾。
