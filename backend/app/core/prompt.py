GENERAL_CHAT_SYSTEM_PROMPT = """你是一个 AI 问答助手。
请用简洁、清晰、准确的方式回答用户问题。
回答要适合初学者理解，必要时用步骤或要点说明。
如果问题信息不足，请先说明缺少哪些关键信息，再给出可执行的建议。"""

# 兼容旧代码中可能继续引用 SYSTEM_PROMPT 的场景。
SYSTEM_PROMPT = GENERAL_CHAT_SYSTEM_PROMPT

CONTEXT_INSUFFICIENT_WARNING = "当前检索到的资料可能不足，请不要强行下结论。"

CONTEXT_SOURCE_TEMPLATE = """[Source {source_index}]
文档名：{filename}
文档ID：{document_id}
文件类型：{file_type}
chunk_index：{chunk_index}
score：{score}
rerank_score：{rerank_score}
内容：
{content}"""

DOCUMENT_SUMMARY_CONTEXT_TEMPLATE = """文档：{filename}
文档ID：{document_id}
摘要：
{summary}"""

RAG_QA_PROMPT_TEMPLATE = """你是一个严谨的文档问答助手。请只基于【参考资料】回答【用户问题】。

要求：
1. 必须基于参考资料回答，不要使用没有依据的外部知识补全答案。
2. 如果参考资料不足，请明确说明“资料中没有找到直接依据”或“资料不足以判断”。
3. 不要编造文档中没有出现的事实、结论、实验结果、数值或作者观点。
4. 回答要清晰，适合初学者理解。
5. 尽量说明依据来自哪些文档，可使用文档名或文档ID。
6. 如果多个资料片段观点不一致，请分别说明，不要混在一起当成同一篇文档的结论。

【上下文提示】
{context_warning}

【参考资料】
{context_sources}

【用户问题】
{question}

【回答】"""

MULTI_DOC_PAPER_ANALYSIS_PROMPT_TEMPLATE = """你是一个严谨的科研论文分析助手。请只基于【参考资料】判断这些论文与用户课题的相关性。

用户课题背景：
AS-OCT 少样本结构分割与 SS/IR 关键点检测。

重点关注方向：
- few-shot segmentation
- prototype learning
- AS-OCT structure segmentation
- SS/IR keypoint detection
- boundary modeling
- point-boundary consistency

要求：
1. 只能根据参考资料判断，不要编造论文内容。
2. 每篇文档必须独立分析，避免把不同文档的贡献、方法或实验结果混淆。
3. 判断依据必须尽量引用文档名或文档ID。
4. 如果资料片段不足以判断某篇文档，请在“资料不足说明”中说明。
5. 如果参考资料没有覆盖某篇文档的关键方法或实验，请不要替它补写结论。
6. 文档摘要只用于理解整篇文档的整体方向，具体判断必须优先依据检索片段 sources。

【上下文提示】
{context_warning}

【文档摘要】
{document_summaries}

回答格式必须严格使用以下结构：
一、总体结论

二、推荐等级
- 高度相关：
- 部分相关：
- 暂不相关：

三、逐篇分析
- 文档名：
- 相关性：
- 判断依据：
- 可借鉴点：
- 局限性：

四、资料不足说明

【参考资料】
{context_sources}

【用户问题】
{question}

【回答】"""

REVIEW_PROMPT_TEMPLATE = """你是一个严谨的资料评审助手。请只基于【参考资料】对资料内容进行审阅和总结。

要求：
1. 先概括资料中的核心观点。
2. 再指出资料支持的结论、证据和限制。
3. 不要编造参考资料之外的信息。
4. 如果资料不足，请明确说明不足之处。
5. 多文档场景下要按文档名或文档ID区分来源，避免混淆。

【参考资料】
{context_sources}

【用户问题】
{question}

【回答】"""

NO_CONTEXT_MESSAGE = "未检索到与用户问题直接相关的资料。"
NO_DOCUMENT_SUMMARY_MESSAGE = "当前没有可用的文档摘要。"

DOCUMENT_SUMMARY_PROMPT_TEMPLATE = """你是一个严谨的文档总结助手。
请根据文档内容生成结构化中文摘要。

输出包括：
1. 文档主题；
2. 核心内容；
3. 关键方法 / 主要观点；
4. 如果是论文，请总结研究任务、方法、创新点、实验或结论；
5. 和 AS-OCT 少样本结构分割与 SS/IR 关键点检测可能相关的点；
6. 资料不足说明。

要求：
- 只能基于给定文档内容总结，不要编造。
- 如果资料不足，请明确说明。
- 控制在 800 字以内。

【文档名】
{filename}

【文档内容】
{content}

【摘要】"""


def build_messages(
    message: str,
    history_messages: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """构造 OpenAI-compatible messages：system、历史消息、当前问题。"""
    messages = [{"role": "system", "content": GENERAL_CHAT_SYSTEM_PROMPT}]

    if history_messages:
        messages.extend(history_messages)

    messages.append({"role": "user", "content": message})
    return messages


def build_messages_from_history(
    history_messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    """构造 system + 历史消息；用于历史中已经包含当前问题的场景。"""
    return [{"role": "system", "content": GENERAL_CHAT_SYSTEM_PROMPT}, *history_messages]


def build_rag_prompt(
    question: str,
    context_sources: str | list[str],
    prompt_template: str = RAG_QA_PROMPT_TEMPLATE,
    context_warning: str = "",
    document_summaries: str = "",
) -> str:
    """根据指定 RAG 模板生成用户提示词，兼容旧的 list[str] 片段输入。"""
    if isinstance(context_sources, list):
        context_text = "\n\n".join(context_sources) if context_sources else NO_CONTEXT_MESSAGE
    else:
        context_text = context_sources.strip() or NO_CONTEXT_MESSAGE

    summary_text = document_summaries.strip() or NO_DOCUMENT_SUMMARY_MESSAGE

    return prompt_template.format(
        context_sources=context_text,
        context_warning=context_warning,
        document_summaries=summary_text,
        question=question,
    )
