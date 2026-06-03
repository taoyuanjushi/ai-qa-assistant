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
