const API_BASE_URL = 'http://127.0.0.1:8001/api'


async function requestJson(url) {
  const response = await fetch(url)
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    throw new Error(data?.detail || '请求历史会话失败。')
  }

  return data
}


export async function fetchConversations() {
  return requestJson(`${API_BASE_URL}/conversations`)
}


export async function fetchConversationMessages(conversationId) {
  return requestJson(`${API_BASE_URL}/conversations/${conversationId}/messages`)
}
