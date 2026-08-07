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

export type UploadTranscriptionResponse = {
  folderPath: string
  uploadedPath: string
  transcriptionSourcePath: string
  convertedToMp3Path: string | null
  job: Job
}

export type Channel = {
  id: number
  name: string
  language: string
  seoRules: string
  youtubeLinked: boolean
  youtubeName: string
  createdAt: string
}

export type ClipSource = {
  folder: string
  name: string
  videoPath: string
  transcriptPath: string
  modifiedAt: string
}

export type ClipCandidate = {
  id: string
  transcriptPath?: string
  videoPath?: string
  start: number
  end: number
  duration: number
  title: string
  reason: string
  score: number
  transcript: string
  channelId?: number | null
  focus: 'left' | 'center' | 'right'
  zoom: number
  topRatio: number
  subtitles: boolean
  renderedPath?: string
  youtubeUrl?: string
  rendered?: boolean
  uploaded?: boolean
}

export type DetectClipsResponse = {
  videoPath: string | null
  clips: ClipCandidate[]
}

export type ComfyStatus = {
  configured: boolean
  online: boolean
  url: string | null
  pending: number | null
  running: number | null
  error: string | null
}
