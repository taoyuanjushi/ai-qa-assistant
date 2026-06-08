SYSTEM_PROMPT = (
    "You are an AI question answering assistant. Answer the user's question "
    "clearly, accurately, and concisely."
)


def build_messages(
    message: str,
    history_messages: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """构造 OpenAI-compatible messages：system、历史消息、当前问题。"""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history_messages:
        messages.extend(history_messages)

    messages.append({"role": "user", "content": message})
    return messages


def build_messages_from_history(
    history_messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    """构造 system + 历史消息；用于历史中已经包含当前问题的场景。"""
    return [{"role": "system", "content": SYSTEM_PROMPT}, *history_messages]


def build_rag_prompt(question: str, source_contents: list[str]) -> str:
    """把检索到的 top-k chunk 拼成 RAG 用户提示词。"""
    if source_contents:
        references = "\n\n".join(
            f"片段 {index}：\n{content}"
            for index, content in enumerate(source_contents, start=1)
        )
    else:
        references = "未检索到与用户问题直接相关的资料。"

    return f"""你是一个严谨的 AI 学习助手。请优先根据【参考资料】回答用户问题。
如果参考资料中没有相关信息，请明确说明“资料中没有找到直接依据”，不要编造。
回答要清晰、适合初学者理解。

【参考资料】
{references}

【用户问题】
{question}"""
