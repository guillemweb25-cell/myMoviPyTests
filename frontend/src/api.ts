import type { Campaign, Channel, ClipCandidate, ClipSource, ComfyStatus, ContentJobRequest, DetectClipsResponse, FileEntry, Job, ScriptInfo, UploadTranscriptionResponse } from './types'

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
  youtubeStatus: (channelId: number) =>
    getJson<{ hasSecret: boolean; linked: boolean; channelName: string }>(`/api/youtube/${channelId}/status`),
  youtubeAuthUrl: (channelId: number) =>
    getJson<{ authUrl: string; redirectUri: string }>(`/api/youtube/${channelId}/auth-url`),
  youtubeFinish: (code: string, state: string) =>
    postJson<{ linked: boolean; channelName: string }>('/api/youtube/finish', { code, state }),
  youtubeUnlink: (channelId: number) => postJson<{ linked: boolean }>(`/api/youtube/${channelId}/unlink`, {}),
  uploadYoutubeSecret: async (channelId: number, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    const response = await fetch(`/api/youtube/${channelId}/secret`, {
      method: 'POST',
      headers: authHeaders(),
      body: formData,
    })
    return handle<{ hasSecret: boolean }>(response)
  },
  campaigns: (channelId: number) => getJson<Campaign[]>(`/api/campaigns?channelId=${channelId}`),
  campaign: (id: number) => getJson<Campaign>(`/api/campaigns/${id}`),
  createCampaign: (payload: { channelId: number; name: string; sourceUrl: string; campaignUrl: string; cookiesFile?: string }) =>
    postJson<{ campaign: Campaign; job: Job | null }>('/api/campaigns', payload),
  updateCampaign: (id: number, payload: { name?: string; campaignUrl?: string }) =>
    patchJson<Campaign>(`/api/campaigns/${id}`, payload),
  deleteCampaign: (id: number) => del<{ deleted: number }>(`/api/campaigns/${id}`),
  extractBrief: (id: number, payload: { briefUrl?: string; briefText?: string }) =>
    postJson<{ campaign: Campaign; rules: Record<string, unknown> }>(`/api/campaigns/${id}/brief`, payload),
  applyCampaignRules: (id: number) => postJson<{ updated: number; onScreenText: string }>(`/api/campaigns/${id}/apply-rules`, {}),
  clipSources: (channelId?: number | null) =>
    getJson<ClipSource[]>(channelId != null ? `/api/clips/sources?channelId=${channelId}` : '/api/clips/sources'),
  clipSourceFromUrl: (payload: { url: string; channelId?: number | null; browser?: string; cookiesFile?: string; lang?: string; subtitleFormat?: string }) =>
    postJson<Job>('/api/clips/source-from-url', payload),
  detectClips: (transcriptPath: string, count: number, minDuration: number, maxDuration: number, channelId?: number | null) =>
    postJson<DetectClipsResponse>('/api/clips/detect', { transcriptPath, channelId, count, minDuration, maxDuration }),
  savedClips: (transcriptPath: string) =>
    getJson<{ clips: ClipCandidate[] }>(`/api/clips/list?transcriptPath=${encodeURIComponent(transcriptPath)}`),
  updateClipSettings: (clipId: string, payload: { focus: string; zoom: number; topRatio: number; subtitles: boolean; overlayText: string }) =>
    patchJson<ClipCandidate>(`/api/clips/${clipId}/settings`, payload),
  trimClip: (clipId: string, start: number, end: number) =>
    patchJson<ClipCandidate>(`/api/clips/${clipId}/trim`, { start, end }),
  renderClip: (clipId: string) => postJson<{ job: Job; renderedPath: string }>(`/api/clips/${clipId}/render`, {}),
  uploadClip: (clipId: string, privacy: string) => postJson<Job>(`/api/clips/${clipId}/upload`, { privacy }),
  setClipVisibility: (clipId: string, privacy: string) =>
    postJson<{ privacy: string }>(`/api/clips/${clipId}/visibility`, { privacy }),
  generateClipSeo: (clipId: string) =>
    postJson<{ title: string; description: string; tags: string }>(`/api/clips/${clipId}/seo`, {}),
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
