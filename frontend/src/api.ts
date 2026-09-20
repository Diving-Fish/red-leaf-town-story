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
  // 上传走 FormData，Content-Type 必须留给浏览器自己填（它要带上 multipart 边界）。
  const jsonType: Record<string, string> = init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }
  try {
    response = await fetch(path, {
      credentials: 'same-origin',
      headers: { ...jsonType, ...(init.headers || {}) },
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
