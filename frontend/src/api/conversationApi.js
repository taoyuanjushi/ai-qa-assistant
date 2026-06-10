import { API_BASE_URL } from './config'
import { getApiErrorMessage } from './errors'


async function requestJson(url) {
  const response = await fetch(url)
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    throw new Error(getApiErrorMessage(data, '请求历史会话失败。'))
  }

  return data
}


export async function fetchConversations() {
  return requestJson(`${API_BASE_URL}/conversations`)
}


export async function fetchConversationMessages(conversationId) {
  return requestJson(`${API_BASE_URL}/conversations/${conversationId}/messages`)
}
