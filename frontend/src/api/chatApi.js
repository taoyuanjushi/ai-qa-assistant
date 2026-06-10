import { API_BASE_URL } from './config'
import { getApiErrorMessage } from './errors'

// 前端 API 封装：把 React 层的消息转换成 POST /api/chat 请求。
export async function sendChatMessage(message, conversationId = null) {
  const body = { message }
  if (conversationId !== null) {
    body.conversation_id = conversationId
  }

  // fetch 返回的是 HTTP 响应对象，不会因为 4xx/5xx 自动抛错。
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: {
      // 告诉 FastAPI 请求体是 JSON，后端才能按 ChatRequest 解析。
      'Content-Type': 'application/json',
    },
    // 第一次只发送 message；后续会带上同一个 conversation_id。
    body: JSON.stringify(body),
  })

  // 尝试解析响应 JSON；如果后端返回空响应或非 JSON，就用 null 兜底。
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    // FastAPI 错误通常放在 detail 字段里，优先展示后端返回的原因。
    throw new Error(getApiErrorMessage(data, '发送失败，请检查后端服务。'))
  }

  if (!data || typeof data.answer !== 'string') {
    // 成功响应必须包含 answer 字符串，否则说明前后端接口契约不一致。
    throw new Error('后端返回格式不正确。')
  }

  if (typeof data.conversation_id !== 'number') {
    throw new Error('后端没有返回 conversation_id。')
  }

  // 返回完整数据，当前页面主要使用 data.answer。
  return data
}

export async function sendChatMessageStream(
  message,
  conversationId = null,
  onChunk,
  onConversationId,
) {
  const body = { message, conversation_id: conversationId }

  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const errorPayload = await response.json().catch(() => null)
    throw new Error(getApiErrorMessage(errorPayload, '流式请求失败，请检查后端服务。'))
  }

  if (!response.body) {
    throw new Error('当前浏览器不支持流式读取。')
  }

  const nextConversationId = Number(response.headers.get('X-Conversation-Id'))
  if (!Number.isFinite(nextConversationId)) {
    throw new Error('后端没有返回 conversation_id。')
  }
  onConversationId?.(nextConversationId)

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }

    const chunk = decoder.decode(value, { stream: true })
    if (chunk) {
      onChunk(chunk)
    }
  }

  const finalChunk = decoder.decode()
  if (finalChunk) {
    onChunk(finalChunk)
  }

  return { conversation_id: nextConversationId }
}
