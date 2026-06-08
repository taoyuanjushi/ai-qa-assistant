const API_BASE_URL = 'http://127.0.0.1:8001/api'


async function parseJsonResponse(response, fallbackMessage) {
  // FastAPI 错误通常是 JSON；解析失败时使用调用方传入的兜底提示。
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    throw new Error(data?.detail || fallbackMessage)
  }

  return data
}


function validateDocumentUploadResponse(data) {
  if (
    typeof data?.document_id !== 'number' ||
    typeof data.filename !== 'string' ||
    typeof data.file_type !== 'string' ||
    typeof data.chunk_count !== 'number'
  ) {
    throw new Error('后端返回的文档上传结果格式不正确。')
  }

  return data
}


function appendRagScope(body, { document_id, document_ids }) {
  // document_ids 优先级高于旧的 document_id；空数组表示让后端检索全部文档。
  if (Array.isArray(document_ids)) {
    body.document_ids = document_ids.map((id) => Number(id))
    return
  }

  if (document_id !== null) {
    body.document_id = document_id
  }
}


export async function uploadDocument(file) {
  const formData = new FormData()
  formData.append('file', file)

  // 上传文件时不要手动设置 Content-Type，浏览器会自动补 multipart boundary。
  const response = await fetch(`${API_BASE_URL}/rag/documents`, {
    method: 'POST',
    body: formData,
  })

  return validateDocumentUploadResponse(
    await parseJsonResponse(response, '上传文档失败。'),
  )
}


export async function uploadDocuments(files) {
  const formData = new FormData()
  Array.from(files).forEach((file) => {
    formData.append('files', file)
  })

  const response = await fetch(`${API_BASE_URL}/rag/documents/batch`, {
    method: 'POST',
    body: formData,
  })

  const data = await parseJsonResponse(response, '批量上传文档失败。')
  if (!Array.isArray(data?.uploaded) || !Array.isArray(data?.failed)) {
    throw new Error('后端返回的批量上传结果格式不正确。')
  }

  data.uploaded.forEach(validateDocumentUploadResponse)
  data.failed.forEach((item) => {
    if (typeof item?.filename !== 'string' || typeof item.error !== 'string') {
      throw new Error('后端返回的批量上传失败项格式不正确。')
    }
  })

  return data
}


export async function getDocuments() {
  return parseJsonResponse(
    await fetch(`${API_BASE_URL}/rag/documents`),
    '加载文档列表失败。',
  )
}


export async function ragChat({
  question,
  document_id = null,
  document_ids = null,
  conversation_id = null,
}) {
  const body = { question }
  appendRagScope(body, { document_id, document_ids })
  if (conversation_id !== null) {
    body.conversation_id = conversation_id
  }

  const response = await fetch(`${API_BASE_URL}/rag/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  const data = await parseJsonResponse(response, '基于文档提问失败。')
  if (
    typeof data?.conversation_id !== 'number' ||
    typeof data.answer !== 'string' ||
    !Array.isArray(data.sources)
  ) {
    throw new Error('后端返回的 RAG 问答结果格式不正确。')
  }

  return data
}


export async function ragChatStream({
  question,
  document_id = null,
  document_ids = null,
  conversation_id = null,
  onMetadata,
  onChunk,
  onDone,
  onError,
}) {
  const body = { question }
  appendRagScope(body, { document_id, document_ids })
  if (conversation_id !== null) {
    body.conversation_id = conversation_id
  }

  const response = await fetch(`${API_BASE_URL}/rag/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(data?.detail || '流式文档问答失败。')
  }

  if (!response.body) {
    throw new Error('当前浏览器不支持流式读取。')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  async function handleLine(line) {
    if (!line.trim()) {
      return
    }

    let payload
    try {
      payload = JSON.parse(line)
    } catch {
      throw new Error('流式 RAG 返回格式不正确。')
    }

    if (payload.type === 'metadata') {
      onMetadata?.(payload)
      return
    }

    if (payload.type === 'chunk') {
      onChunk?.(payload.content || '')
      return
    }

    if (payload.type === 'done') {
      onDone?.()
      return
    }

    if (payload.type === 'error') {
      const message = payload.message || '流式文档问答失败。'
      onError?.(message)
      throw new Error(message)
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      await handleLine(line)
    }
  }

  buffer += decoder.decode()
  if (buffer.trim()) {
    await handleLine(buffer)
  }
}
