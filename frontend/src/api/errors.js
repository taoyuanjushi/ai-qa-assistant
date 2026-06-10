export function getApiErrorMessage(data, fallbackMessage) {
  return data?.error?.message || data?.message || data?.detail || fallbackMessage
}


export function getApiErrorCode(data) {
  return data?.error?.code || data?.code || null
}
