const CHAT_API_URL = 'http://127.0.0.1:8001/api/chat'

// 前端 API 封装：把 React 层的消息转换成 POST /api/chat 请求。
export async function sendChatMessage(message) {
  // fetch 返回的是 HTTP 响应对象，不会因为 4xx/5xx 自动抛错。
  const response = await fetch(CHAT_API_URL, {
    method: 'POST',
    headers: {
      // 告诉 FastAPI 请求体是 JSON，后端才能按 ChatRequest 解析。
      'Content-Type': 'application/json',
    },
    // 当前版本只发送 message；后续多轮会话可以在这里追加 conversation_id。
    body: JSON.stringify({ message }),
  })

  // 尝试解析响应 JSON；如果后端返回空响应或非 JSON，就用 null 兜底。
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    // FastAPI 错误通常放在 detail 字段里，优先展示后端返回的原因。
    throw new Error(data?.detail || '发送失败，请检查后端服务。')
  }

  if (!data || typeof data.answer !== 'string') {
    // 成功响应必须包含 answer 字符串，否则说明前后端接口契约不一致。
    throw new Error('后端返回格式不正确。')
  }

  // 返回完整数据，当前页面主要使用 data.answer。
  return data
}
