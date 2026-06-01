SYSTEM_PROMPT = (
    "You are an AI question answering assistant. Answer the user's question "
    "clearly, accurately, and concisely."
)


def build_messages(message: str) -> list[dict[str, str]]:
    """把用户输入包装成 OpenAI-compatible messages 数组。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]
