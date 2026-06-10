from app.core.prompt import DOCUMENT_SUMMARY_PROMPT_TEMPLATE
from app.services.llm_service import LLMServiceError, llm_service


MAX_SUMMARY_INPUT_CHARS = 12000


class SummaryServiceError(RuntimeError):
    """文档摘要生成失败时抛出。"""


def generate_document_summary(filename: str, text: str) -> str:
    """基于解析后的纯文本生成结构化中文摘要。"""
    content = _select_summary_content(text)
    if not content:
        raise SummaryServiceError("文档内容为空，无法生成摘要。")

    prompt = DOCUMENT_SUMMARY_PROMPT_TEMPLATE.format(
        filename=filename,
        content=content,
    )
    try:
        summary = llm_service.chat(prompt).strip()
    except LLMServiceError as exc:
        raise SummaryServiceError(str(exc)) from exc

    if not summary:
        raise SummaryServiceError("大模型没有返回可用摘要。")

    return summary


def _select_summary_content(text: str) -> str:
    """截取摘要输入，避免把整篇超长文档直接传给大模型。"""
    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(normalized_text) <= MAX_SUMMARY_INPUT_CHARS:
        return normalized_text

    return normalized_text[:MAX_SUMMARY_INPUT_CHARS]
