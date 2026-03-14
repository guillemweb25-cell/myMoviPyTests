export type ScriptInfo = {
  name: string
  description: string
  category: string
  suggestedArgs: string[]
}

export type Job = {
  id: string
  script: string
  args: string[]
  command: string[]
  status: 'queued' | 'running' | 'completed' | 'failed'
  created_at: string
  started_at: string | null
  ended_at: string | null
  return_code: number | null
  log_path: string
}

export type FileEntry = {
  name: string
  isDir: boolean
  path: string
  modifiedAt: string
}

export type ContentJobRequest = {
  url: string
  browser?: string
  cookiesFile?: string
  ffmpeg?: string
  lang: string
  subtitleFormat: 'vtt' | 'srt'
}
