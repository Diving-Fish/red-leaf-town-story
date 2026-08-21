export class ApiError extends Error {
  status: number
  code: string

  constructor(message: string, status = 0, code = 'network_error') {
    super(message)
    this.status = status
    this.code = code
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
      ...init,
    })
  } catch {
    throw new ApiError('暂时无法连接红叶镇，请稍后重试')
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError(body.message || '请求失败', response.status, body.code)
  }
  return body.data as T
}
