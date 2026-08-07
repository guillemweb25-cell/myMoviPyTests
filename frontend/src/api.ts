import type { Channel, ClipCandidate, ClipSource, ComfyStatus, ContentJobRequest, DetectClipsResponse, FileEntry, Job, ScriptInfo, UploadTranscriptionResponse } from './types'

async function patchJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'PATCH',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  return handle<T>(response)
}

async function del<T>(url: string): Promise<T> {
  const response = await fetch(url, { method: 'DELETE', headers: authHeaders() })
  return handle<T>(response)
}

const TOKEN_KEY = 'mediaops_token'

export class UnauthorizedError extends Error {
  constructor() {
    super('No autorizado')
    this.name = 'UnauthorizedError'
  }
}

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? ''
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = getToken()
  return token ? { ...extra, Authorization: `Bearer ${token}` } : extra
}

function withToken(url: string): string {
  const token = getToken()
  if (!token) return url
  const separator = url.includes('?') ? '&' : '?'
  return `${url}${separator}token=${encodeURIComponent(token)}`
}

async function handle<T>(response: Response): Promise<T> {
  if (response.status === 401) {
    throw new UnauthorizedError()
  }
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json() as Promise<T>
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: authHeaders() })
  return handle<T>(response)
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  return handle<T>(response)
}

export const api = {
  health: () => getJson<{ status: string; authRequired: boolean }>('/api/health'),
  scripts: () => getJson<ScriptInfo[]>('/api/scripts'),
  jobs: () => getJson<Job[]>('/api/jobs'),
  job: (id: string) => getJson<Job>(`/api/jobs/${id}`),
  comfyStatus: () => getJson<ComfyStatus>('/api/comfy/status'),
  runJob: (script: string, rawArgs: string) => postJson<Job>('/api/jobs', { script, rawArgs }),
  runContentJob: (payload: ContentJobRequest) => postJson<Job>('/api/content/jobs', payload),
  channels: () => getJson<Channel[]>('/api/channels'),
  createChannel: (payload: { name: string; language: string; seoRules?: string }) =>
    postJson<Channel>('/api/channels', payload),
  updateChannel: (id: number, payload: { name?: string; language?: string; seoRules?: string }) =>
    patchJson<Channel>(`/api/channels/${id}`, payload),
  deleteChannel: (id: number) => del<{ deleted: number }>(`/api/channels/${id}`),
  clipSources: () => getJson<ClipSource[]>('/api/clips/sources'),
  clipSourceFromUrl: (payload: { url: string; browser?: string; cookiesFile?: string; lang?: string; subtitleFormat?: string }) =>
    postJson<Job>('/api/clips/source-from-url', payload),
  detectClips: (transcriptPath: string, count: number, minDuration: number, maxDuration: number) =>
    postJson<DetectClipsResponse>('/api/clips/detect', { transcriptPath, count, minDuration, maxDuration }),
  savedClips: (transcriptPath: string) =>
    getJson<{ clips: ClipCandidate[] }>(`/api/clips/list?transcriptPath=${encodeURIComponent(transcriptPath)}`),
  renderClip: (payload: { video: string; start: number; end: number; subtitles: boolean; topRatio: number; focus: string; zoom: number; title?: string }) =>
    postJson<Job>('/api/clips/render', payload),
  uploadAndTranscribe: async (
    file: File,
    folderTitle: string,
    lang: string,
    subtitleFormat: 'vtt' | 'srt',
  ) => {
    const formData = new FormData()
    formData.append('file', file)

    const response = await fetch(
      `/api/transcriptions/upload?folderTitle=${encodeURIComponent(folderTitle)}&lang=${encodeURIComponent(lang)}&subtitleFormat=${subtitleFormat}`,
      {
        method: 'POST',
        headers: authHeaders(),
        body: formData,
      },
    )
    return handle<UploadTranscriptionResponse>(response)
  },
  jobLog: async (id: string) => {
    const data = await getJson<{ content: string }>(`/api/jobs/${id}/log`)
    return data.content
  },
  /**
   * Abre un stream SSE del log en vivo de un job. Devuelve el EventSource para
   * poder cerrarlo. El token va por query param porque EventSource no admite
   * cabeceras personalizadas.
   */
  streamJobLog: (
    id: string,
    handlers: { onLine: (line: string) => void; onEnd: (status: string) => void; onError: () => void },
  ): EventSource => {
    const source = new EventSource(withToken(`/api/jobs/${id}/stream`))
    source.onmessage = (event) => handlers.onLine(event.data)
    source.addEventListener('end', (event) => {
      handlers.onEnd((event as MessageEvent).data)
      source.close()
    })
    source.onerror = () => {
      handlers.onError()
      source.close()
    }
    return source
  },
  files: (path = 'output') =>
    getJson<{ base: string; items: FileEntry[] }>(`/api/files?path=${encodeURIComponent(path)}`),
  fileUrl: (path: string) => withToken(`/api/file?path=${encodeURIComponent(path)}`),
  fileText: async (path: string) => {
    const response = await fetch(`/api/file?path=${encodeURIComponent(path)}`, { headers: authHeaders() })
    if (response.status === 401) {
      throw new UnauthorizedError()
    }
    if (!response.ok) {
      throw new Error(await response.text())
    }
    return response.text()
  },
}
