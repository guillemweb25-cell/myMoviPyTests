import type { ComfyStatus, ContentJobRequest, FileEntry, Job, ScriptInfo, UploadTranscriptionResponse } from './types'

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json() as Promise<T>
}

export const api = {
  scripts: () => getJson<ScriptInfo[]>('/api/scripts'),
  jobs: () => getJson<Job[]>('/api/jobs'),
  comfyStatus: () => getJson<ComfyStatus>('/api/comfy/status'),
  runJob: async (script: string, rawArgs: string) => {
    const response = await fetch('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script, rawArgs }),
    })
    if (!response.ok) {
      throw new Error(await response.text())
    }
    return response.json() as Promise<Job>
  },
  runContentJob: async (payload: ContentJobRequest) => {
    const response = await fetch('/api/content/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      throw new Error(await response.text())
    }
    return response.json() as Promise<Job>
  },
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
        body: formData,
      },
    )
    if (!response.ok) {
      throw new Error(await response.text())
    }
    return response.json() as Promise<UploadTranscriptionResponse>
  },
  jobLog: async (id: string) => {
    const data = await getJson<{ content: string }>(`/api/jobs/${id}/log`)
    return data.content
  },
  files: async (path = 'output') => {
    const data = await getJson<{ base: string; items: FileEntry[] }>(`/api/files?path=${encodeURIComponent(path)}`)
    return data
  },
  fileUrl: (path: string) => `/api/file?path=${encodeURIComponent(path)}`,
  fileText: async (path: string) => {
    const response = await fetch(`/api/file?path=${encodeURIComponent(path)}`)
    if (!response.ok) {
      throw new Error(await response.text())
    }
    return response.text()
  },
}
