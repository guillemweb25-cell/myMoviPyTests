import { useEffect, useMemo, useState } from 'react'
import { api, clearToken, getToken, setToken, UnauthorizedError } from './api'
import type { Campaign, Channel, ClipCandidate, ClipSource, ComfyStatus, FileEntry, Job, ScriptInfo } from './types'

type Section = 'dashboard' | 'content' | 'clipping' | 'channel' | 'execute' | 'jobs' | 'files'

const sections: { id: Section; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'content', label: 'Contenido Web' },
  { id: 'clipping', label: 'Clipping' },
  { id: 'execute', label: 'Ejecutar Scripts' },
  { id: 'jobs', label: 'Historial' },
  { id: 'files', label: 'Explorador Output' },
]

function formatSeconds(value: number): string {
  const total = Math.max(0, Math.round(value))
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

export default function App() {
  const [authState, setAuthState] = useState<'checking' | 'authed' | 'login'>('checking')
  const [tokenInput, setTokenInput] = useState('')
  const [activeSection, setActiveSection] = useState<Section>('dashboard')
  const [scripts, setScripts] = useState<ScriptInfo[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [comfyStatus, setComfyStatus] = useState<ComfyStatus | null>(null)
  const [selectedScript, setSelectedScript] = useState('')
  const [rawArgs, setRawArgs] = useState('')
  const [selectedJobId, setSelectedJobId] = useState<string>('')
  const [selectedLog, setSelectedLog] = useState('')
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isLaunchingContent, setIsLaunchingContent] = useState(false)

  const [currentPath, setCurrentPath] = useState('output')
  const [fileEntries, setFileEntries] = useState<FileEntry[]>([])
  const [cookieEntries, setCookieEntries] = useState<FileEntry[]>([])
  const [selectedFile, setSelectedFile] = useState<FileEntry | null>(null)
  const [selectedFileContent, setSelectedFileContent] = useState('')
  const [isLoadingFile, setIsLoadingFile] = useState(false)
  const [isGeneratingTranscript, setIsGeneratingTranscript] = useState(false)
  const [isDownloadingVideo, setIsDownloadingVideo] = useState(false)
  const [isDownloadingThumbnail, setIsDownloadingThumbnail] = useState(false)
  const [isConvertingImageToPng, setIsConvertingImageToPng] = useState(false)
  const [isDetectingInsertedFrames, setIsDetectingInsertedFrames] = useState(false)
  const [copyFeedback, setCopyFeedback] = useState('')

  const [contentUrl, setContentUrl] = useState('')
  const [contentMode, setContentMode] = useState<'audio' | 'video'>('audio')
  const [contentBrowser, setContentBrowser] = useState('')
  const [contentCookiesFile, setContentCookiesFile] = useState('')
  const [contentFfmpeg, setContentFfmpeg] = useState('')
  const [contentLang, setContentLang] = useState('auto')
  const [contentSubtitleFormat, setContentSubtitleFormat] = useState<'vtt' | 'srt'>('vtt')
  const [uploadedMediaFile, setUploadedMediaFile] = useState<File | null>(null)
  const [uploadFolderTitle, setUploadFolderTitle] = useState('')
  const [uploadLang, setUploadLang] = useState('auto')
  const [uploadSubtitleFormat, setUploadSubtitleFormat] = useState<'vtt' | 'srt'>('vtt')
  const [isUploadingAndTranscribing, setIsUploadingAndTranscribing] = useState(false)

  const [channels, setChannels] = useState<Channel[]>([])
  const [activeChannelId, setActiveChannelId] = useState<number | null>(null)
  const [channelDraft, setChannelDraft] = useState<{ name: string; language: string; seoRules: string }>({ name: '', language: 'es', seoRules: '' })
  const [ytStatus, setYtStatus] = useState<{ hasSecret: boolean; linked: boolean; channelName: string } | null>(null)
  const [isUploadingSecret, setIsUploadingSecret] = useState(false)

  const [clipSources, setClipSources] = useState<ClipSource[]>([])
  const [selectedClipSource, setSelectedClipSource] = useState('')
  const [clipCandidates, setClipCandidates] = useState<ClipCandidate[]>([])
  const [clipCount, setClipCount] = useState(5)
  const [clipUrl, setClipUrl] = useState('')
  const [clipUrlCookies, setClipUrlCookies] = useState('')
  const [isPreparingSource, setIsPreparingSource] = useState(false)
  const [clipSourceStatus, setClipSourceStatus] = useState('')
  const [isDetectingClips, setIsDetectingClips] = useState(false)
  const [renderingClipKey, setRenderingClipKey] = useState('')
  const [uploadingClipId, setUploadingClipId] = useState('')
  const [generatingSeoId, setGeneratingSeoId] = useState('')
  const [clipTab, setClipTab] = useState<'create' | 'manage' | 'youtube'>('create')
  const [copiedUrl, setCopiedUrl] = useState('')

  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [activeCampaignId, setActiveCampaignId] = useState<number | null>(null)
  const [campName, setCampName] = useState('')
  const [campSourceUrl, setCampSourceUrl] = useState('')
  const [campCampaignUrl, setCampCampaignUrl] = useState('')
  const [campCookies, setCampCookies] = useState('')
  const [isCreatingCampaign, setIsCreatingCampaign] = useState(false)
  const [campBriefUrl, setCampBriefUrl] = useState('')
  const [isExtractingBrief, setIsExtractingBrief] = useState(false)

  function handleApiError(e: unknown) {
    if (e instanceof UnauthorizedError) {
      clearToken()
      setAuthState('login')
      setError('Token invalido o sesion expirada. Vuelve a introducir el token.')
      return
    }
    setError(e instanceof Error ? e.message : String(e))
  }

  async function refreshScripts() {
    try {
      const data = await api.scripts()
      setScripts(data)
      if (!selectedScript && data.length > 0) {
        setSelectedScript(data[0].name)
      }
    } catch (e) {
      handleApiError(e)
    }
  }

  async function refreshJobs() {
    try {
      const data = await api.jobs()
      setJobs(data)
      if (!selectedJobId && data.length > 0) {
        setSelectedJobId(data[0].id)
      }
    } catch (e) {
      handleApiError(e)
    }
  }

  async function refreshComfyStatus() {
    try {
      const data = await api.comfyStatus()
      setComfyStatus(data)
    } catch {
      setComfyStatus({
        configured: false,
        online: false,
        url: null,
        pending: null,
        running: null,
        error: 'No se pudo consultar ComfyUI',
      })
    }
  }

  function insertOrUpdateJob(job: Job) {
    setJobs((currentJobs) => {
      const remaining = currentJobs.filter((item) => item.id !== job.id)
      return [job, ...remaining]
    })
  }

  async function refreshFiles(path = currentPath) {
    try {
      const data = await api.files(path)
      setCurrentPath(data.base)
      setFileEntries(data.items)
    } catch (e) {
      handleApiError(e)
    }
  }

  async function refreshCookies() {
    try {
      const data = await api.files('cookies')
      setCookieEntries(data.items.filter((item) => !item.isDir))
    } catch {
      setCookieEntries([])
    }
  }

  async function refreshChannels() {
    try {
      const data = await api.channels()
      setChannels(data)
      if (activeChannelId === null && data.length > 0) {
        setActiveChannelId(data[0].id)
      }
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleCreateChannel() {
    const name = window.prompt('Nombre del canal:')
    if (!name || !name.trim()) return
    try {
      const channel = await api.createChannel({ name: name.trim(), language: 'es' })
      setChannels((prev) => [...prev, channel])
      setActiveChannelId(channel.id)
      setChannelDraft({ name: channel.name, language: channel.language, seoRules: channel.seoRules })
      setActiveSection('channel')
    } catch (e) {
      handleApiError(e)
    }
  }

  function handleSelectChannel(channel: Channel) {
    setActiveChannelId(channel.id)
    setActiveSection('clipping')
  }

  async function handleSaveChannel() {
    if (activeChannelId === null) return
    try {
      const updated = await api.updateChannel(activeChannelId, channelDraft)
      setChannels((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))
      setCopyFeedback('Canal guardado')
      window.setTimeout(() => setCopyFeedback(''), 1500)
    } catch (e) {
      handleApiError(e)
    }
  }

  async function refreshYoutubeStatus(channelId: number) {
    try {
      setYtStatus(await api.youtubeStatus(channelId))
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleUploadSecret(file: File | null) {
    if (!file || activeChannelId === null) return
    setIsUploadingSecret(true)
    setError('')
    try {
      await api.uploadYoutubeSecret(activeChannelId, file)
      await refreshYoutubeStatus(activeChannelId)
    } catch (e) {
      handleApiError(e)
    } finally {
      setIsUploadingSecret(false)
    }
  }

  async function handleLinkYoutube() {
    if (activeChannelId === null) return
    try {
      const { authUrl } = await api.youtubeAuthUrl(activeChannelId)
      window.location.href = authUrl
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleUnlinkYoutube() {
    if (activeChannelId === null) return
    if (!window.confirm('¿Desvincular YouTube de este canal? Podras volver a vincular eligiendo otro canal.')) return
    try {
      await api.youtubeUnlink(activeChannelId)
      await refreshYoutubeStatus(activeChannelId)
      refreshChannels()
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleDeleteChannel() {
    if (activeChannelId === null) return
    if (!window.confirm('¿Eliminar este canal?')) return
    try {
      await api.deleteChannel(activeChannelId)
      const remaining = channels.filter((c) => c.id !== activeChannelId)
      setChannels(remaining)
      setActiveChannelId(remaining.length > 0 ? remaining[0].id : null)
      setActiveSection('clipping')
    } catch (e) {
      handleApiError(e)
    }
  }

  async function refreshCampaigns(channelId: number | null = activeChannelId) {
    if (channelId === null) return
    try {
      setCampaigns(await api.campaigns(channelId))
    } catch (e) {
      handleApiError(e)
    }
  }

  const activeCampaign = useMemo(
    () => campaigns.find((c) => c.id === activeCampaignId) ?? null,
    [campaigns, activeCampaignId],
  )

  function handleOpenCampaign(campaign: Campaign) {
    setActiveCampaignId(campaign.id)
    setClipCandidates([])
    setCampBriefUrl(campaign.briefUrl || '')
    if (campaign.transcriptPath) {
      setSelectedClipSource(campaign.transcriptPath)
      loadSavedClips(campaign.transcriptPath)
    }
  }

  async function handleCreateCampaign() {
    if (activeChannelId === null) { setError('Selecciona un canal.'); return }
    if (!campSourceUrl.trim()) { setError('Pega la URL del video de YouTube a clipear.'); return }
    setIsCreatingCampaign(true)
    setError('')
    setClipSourceStatus('Creando campana: descargando y transcribiendo el video...')
    try {
      const { campaign, job } = await api.createCampaign({
        channelId: activeChannelId,
        name: campName.trim(),
        sourceUrl: campSourceUrl.trim(),
        campaignUrl: campCampaignUrl.trim(),
        cookiesFile: campCookies.trim() || undefined,
      })
      setCampaigns((prev) => [campaign, ...prev])
      if (job) {
        insertOrUpdateJob(job)
        const status = await waitForJob(job.id)
        if (status !== 'completed') {
          setError('Fallo la preparacion de la campana. Revisa el Historial.')
          setClipSourceStatus('')
          return
        }
      }
      const ready = await api.campaign(campaign.id)
      setCampaigns((prev) => prev.map((c) => (c.id === ready.id ? ready : c)))
      setCampName(''); setCampSourceUrl(''); setCampCampaignUrl('')
      setClipSourceStatus('')
      setClipTab('manage')
      handleOpenCampaign(ready)
      if (ready.transcriptPath) await runDetect(ready.transcriptPath)
    } catch (e) {
      setClipSourceStatus('')
      handleApiError(e)
    } finally {
      setIsCreatingCampaign(false)
    }
  }

  async function handleUpdateCampaign(campaignId: number, fields: { name?: string; campaignUrl?: string }) {
    try {
      const updated = await api.updateCampaign(campaignId, fields)
      setCampaigns((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleExtractBrief(campaign: Campaign) {
    if (!campBriefUrl.trim()) { setError('Pega el link del brief (Google Docs).'); return }
    setIsExtractingBrief(true)
    setError('')
    try {
      const { campaign: updated } = await api.extractBrief(campaign.id, { briefUrl: campBriefUrl.trim() })
      setCampaigns((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))
      // Aplica el texto en pantalla obligatorio a los clips existentes.
      if (updated.rules?.onScreenText) {
        await api.applyCampaignRules(campaign.id)
        if (selectedClipSource) await loadSavedClips(selectedClipSource)
      }
    } catch (e) {
      handleApiError(e)
    } finally {
      setIsExtractingBrief(false)
    }
  }

  async function handleDeleteCampaign(campaign: Campaign) {
    if (!window.confirm(`¿Eliminar la campana "${campaign.name}"? (no borra el video ni YouTube)`)) return
    try {
      await api.deleteCampaign(campaign.id)
      setCampaigns((prev) => prev.filter((c) => c.id !== campaign.id))
      if (activeCampaignId === campaign.id) setActiveCampaignId(null)
    } catch (e) {
      handleApiError(e)
    }
  }

  async function refreshClipSources(channelId: number | null = activeChannelId) {
    try {
      const data = await api.clipSources(channelId)
      setClipSources(data)
      if (data.length > 0) {
        setSelectedClipSource(data[0].transcriptPath)
        loadSavedClips(data[0].transcriptPath)
      } else {
        setSelectedClipSource('')
        setClipCandidates([])
      }
    } catch (e) {
      handleApiError(e)
    }
  }

  async function loadSavedClips(transcriptPath: string) {
    try {
      const data = await api.savedClips(transcriptPath)
      setClipCandidates(data.clips)
    } catch (e) {
      handleApiError(e)
    }
  }

  function handleSelectClipSource(transcriptPath: string) {
    setSelectedClipSource(transcriptPath)
    setClipCandidates([])
    if (transcriptPath) loadSavedClips(transcriptPath)
  }

  async function runDetect(transcriptPath: string) {
    setIsDetectingClips(true)
    setError('')
    setClipCandidates([])
    try {
      const data = await api.detectClips(transcriptPath, clipCount, 15, 60, activeChannelId)
      setClipCandidates(data.clips)
      if (data.clips.length === 0) {
        setError('No se detectaron clips. Prueba con otra transcripcion.')
      }
    } catch (e) {
      handleApiError(e)
    } finally {
      setIsDetectingClips(false)
    }
  }

  async function handlePrepareClipSource() {
    if (!clipUrl.trim()) {
      setError('Pega una URL de video para descargar y transcribir.')
      return
    }
    setIsPreparingSource(true)
    setError('')
    setClipSourceStatus('Descargando y transcribiendo el video (puede tardar)...')
    try {
      const job = await api.clipSourceFromUrl({
        url: clipUrl.trim(),
        channelId: activeChannelId,
        cookiesFile: clipUrlCookies.trim() || undefined,
      })
      insertOrUpdateJob(job)

      // Espera a que el job termine sin salir de la pestana Clipping.
      let status = job.status
      while (status === 'queued' || status === 'running') {
        await new Promise((resolve) => setTimeout(resolve, 3000))
        const current = await api.job(job.id)
        insertOrUpdateJob(current)
        status = current.status
      }

      if (status !== 'completed') {
        setClipSourceStatus('')
        setError('Fallo la descarga o la transcripcion. Revisa el Historial para el detalle.')
        return
      }

      setClipSourceStatus('Transcripcion lista. Buscando clips...')
      const sources = await api.clipSources(activeChannelId)
      setClipSources(sources)
      const newest = sources[0]
      if (!newest) {
        setClipSourceStatus('')
        setError('No se encontro el video preparado. Pulsa "Recargar videos".')
        return
      }
      setSelectedClipSource(newest.transcriptPath)
      setClipUrl('')
      setClipSourceStatus('')
      await runDetect(newest.transcriptPath)
      setClipTab('manage')
    } catch (e) {
      setClipSourceStatus('')
      handleApiError(e)
    } finally {
      setIsPreparingSource(false)
    }
  }

  async function handleDetectClips() {
    if (!selectedClipSource) {
      setError('Selecciona un video con transcripcion.')
      return
    }
    await runDetect(selectedClipSource)
  }

  async function waitForJob(jobId: string): Promise<string> {
    let status = 'running'
    while (status === 'queued' || status === 'running') {
      await new Promise((resolve) => setTimeout(resolve, 3000))
      const current = await api.job(jobId)
      insertOrUpdateJob(current)
      status = current.status
    }
    return status
  }

  async function handleClipSettingChange(clip: ClipCandidate, patch: Partial<ClipCandidate>) {
    const merged = {
      focus: (patch.focus ?? clip.focus) as string,
      zoom: patch.zoom ?? clip.zoom,
      topRatio: patch.topRatio ?? clip.topRatio,
      subtitles: patch.subtitles ?? clip.subtitles,
      overlayText: patch.overlayText ?? clip.overlayText ?? '',
    }
    setClipCandidates((prev) => prev.map((c) => (c.id === clip.id ? { ...c, ...patch } : c)))
    try {
      await api.updateClipSettings(clip.id, merged)
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleRenderClip(clip: ClipCandidate) {
    setRenderingClipKey(clip.id)
    setError('')
    try {
      const { job } = await api.renderClip(clip.id)
      insertOrUpdateJob(job)
      await waitForJob(job.id)
      await loadSavedClips(selectedClipSource)
    } catch (e) {
      handleApiError(e)
    } finally {
      setRenderingClipKey('')
    }
  }

  async function handleGenerateSeo(clip: ClipCandidate) {
    setGeneratingSeoId(clip.id)
    setError('')
    try {
      const seo = await api.generateClipSeo(clip.id)
      setClipCandidates((prev) => prev.map((c) => (c.id === clip.id
        ? { ...c, seoTitle: seo.title, seoDescription: seo.description, seoTags: seo.tags }
        : c)))
    } catch (e) {
      handleApiError(e)
    } finally {
      setGeneratingSeoId('')
    }
  }

  async function handleUploadClip(clip: ClipCandidate) {
    setUploadingClipId(clip.id)
    setError('')
    try {
      const job = await api.uploadClip(clip.id)
      insertOrUpdateJob(job)
      const status = await waitForJob(job.id)
      if (status !== 'completed') {
        setError('Fallo la subida a YouTube. Revisa el Historial.')
      }
      await loadSavedClips(selectedClipSource)
    } catch (e) {
      handleApiError(e)
    } finally {
      setUploadingClipId('')
    }
  }

  async function handleCopyUrl(url: string) {
    try {
      await navigator.clipboard.writeText(url)
      setCopiedUrl(url)
      window.setTimeout(() => setCopiedUrl(''), 1500)
    } catch (e) {
      handleApiError(e)
    }
  }

  function getFileKind(path: string) {
    const lower = path.toLowerCase()
    if (lower.endsWith('.txt') || lower.endsWith('.vtt') || lower.endsWith('.srt') || lower.endsWith('.lang') || lower.endsWith('.md') || lower.endsWith('.json') || lower.endsWith('.log')) {
      return 'text'
    }
    if (lower.endsWith('.mp3') || lower.endsWith('.wav') || lower.endsWith('.m4a')) {
      return 'audio'
    }
    if (lower.endsWith('.mp4') || lower.endsWith('.webm') || lower.endsWith('.mov') || lower.endsWith('.avi') || lower.endsWith('.mkv')) {
      return 'video'
    }
    if (lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.jpeg') || lower.endsWith('.gif') || lower.endsWith('.webp')) {
      return 'image'
    }
    return 'other'
  }

  function replaceExtension(path: string, extension: string) {
    const dotIndex = path.lastIndexOf('.')
    if (dotIndex === -1) return `${path}${extension}`
    return `${path.slice(0, dotIndex)}${extension}`
  }

  function findSiblingFile(path: string, extension: string) {
    const siblingPath = replaceExtension(path, extension)
    return fileEntries.find((item) => item.path === siblingPath) ?? null
  }

  function findImageInSameFolder(path: string) {
    const slashIndex = path.lastIndexOf('/')
    const folder = slashIndex === -1 ? '' : path.slice(0, slashIndex + 1)
    return fileEntries.find((item) => !item.isDir && item.path.startsWith(folder) && getFileKind(item.path) === 'image') ?? null
  }

  function findFileInSameFolder(path: string, name: string) {
    const slashIndex = path.lastIndexOf('/')
    const folder = slashIndex === -1 ? '' : path.slice(0, slashIndex + 1)
    return fileEntries.find((item) => !item.isDir && item.path === `${folder}${name}`) ?? null
  }

  async function handleOpenFile(file: FileEntry) {
    setSelectedFile(file)
    setSelectedFileContent('')
    setIsLoadingFile(false)

    if (getFileKind(file.path) !== 'text') {
      return
    }

    setIsLoadingFile(true)
    try {
      const content = await api.fileText(file.path)
      setSelectedFileContent(content)
    } catch (e) {
      handleApiError(e)
    } finally {
      setIsLoadingFile(false)
    }
  }

  async function handleGenerateTranscript(file: FileEntry) {
    setIsGeneratingTranscript(true)
    setError('')

    try {
      const job = await api.runJob('transcribe_sutitles.py', `--file "${file.path}" --lang auto --format vtt`)
      insertOrUpdateJob(job)
      setSelectedJobId(job.id)
      setSelectedLog('Lanzando transcripcion...')
      setActiveSection('jobs')
    } catch (e) {
      handleApiError(e)
    } finally {
      setIsGeneratingTranscript(false)
    }
  }

  async function handleCopyText() {
    if (!selectedFileContent) return
    try {
      await navigator.clipboard.writeText(selectedFileContent)
      setCopyFeedback('Texto copiado')
      window.setTimeout(() => setCopyFeedback(''), 1500)
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleDownloadVideoFromSource() {
    if (!sourceUrlFile) return

    setIsDownloadingVideo(true)
    setError('')

    try {
      const sourceUrl = (await api.fileText(sourceUrlFile.path)).trim()
      if (!sourceUrl) {
        throw new Error('No hay URL guardada en source_url.txt')
      }

      let cookiesArg = ''
      if (sourceJsonFile) {
        const rawJson = await api.fileText(sourceJsonFile.path)
        const parsed = JSON.parse(rawJson) as { cookies_file?: string }
        if (parsed.cookies_file) {
          cookiesArg = ` --cookies "${parsed.cookies_file}"`
        }
      }

      const job = await api.runJob('download_video.py', `--url "${sourceUrl}"${cookiesArg}`)
      insertOrUpdateJob(job)
      setSelectedJobId(job.id)
      setSelectedLog('Preparando descarga de video con yt-dlp...')
      setActiveSection('jobs')
    } catch (e) {
      handleApiError(e)
    } finally {
      setIsDownloadingVideo(false)
    }
  }

  async function handleDownloadThumbnailFromSource() {
    if (!sourceUrlFile) return

    setIsDownloadingThumbnail(true)
    setError('')

    try {
      const sourceUrl = (await api.fileText(sourceUrlFile.path)).trim()
      if (!sourceUrl) {
        throw new Error('No hay URL guardada en source_url.txt')
      }

      let cookiesArg = ''
      if (sourceJsonFile) {
        const rawJson = await api.fileText(sourceJsonFile.path)
        const parsed = JSON.parse(rawJson) as { cookies_file?: string }
        if (parsed.cookies_file) {
          cookiesArg = ` --cookies "${parsed.cookies_file}"`
        }
      }

      const job = await api.runJob('download_thumbnail.py', `--url "${sourceUrl}"${cookiesArg}`)
      insertOrUpdateJob(job)
      setSelectedJobId(job.id)
      setSelectedLog('Preparando descarga de miniatura con yt-dlp...')
      setActiveSection('jobs')
    } catch (e) {
      handleApiError(e)
    } finally {
      setIsDownloadingThumbnail(false)
    }
  }

  async function handleDetectInsertedFrames(file: FileEntry) {
    const outputFolder = `${file.path.replace(/\.[^.]+$/, '')}_inserted_frames`
    setIsDetectingInsertedFrames(true)
    setError('')

    try {
      const job = await api.runJob(
        'extract_inserted_frames.py',
        `--video "${file.path}" --output "${outputFolder}"`,
      )
      insertOrUpdateJob(job)
      setSelectedJobId(job.id)
      setSelectedLog('Analizando video para detectar fotogramas incrustados...')
      setActiveSection('jobs')
    } catch (e) {
      handleApiError(e)
    } finally {
      setIsDetectingInsertedFrames(false)
    }
  }

  async function handleConvertImageToPng(file: FileEntry) {
    setIsConvertingImageToPng(true)
    setError('')

    try {
      const job = await api.runJob('convert_image_to_png.py', `--file "${file.path}"`)
      insertOrUpdateJob(job)
      setSelectedJobId(job.id)
      setSelectedLog('Convirtiendo imagen a PNG...')
      setActiveSection('jobs')
    } catch (e) {
      handleApiError(e)
    } finally {
      setIsConvertingImageToPng(false)
    }
  }

  // Bootstrap: averigua si el backend exige token y decide pantalla inicial.
  useEffect(() => {
    api
      .health()
      .then((info) => {
        if (!info.authRequired) {
          setAuthState('authed')
        } else {
          setAuthState(getToken() ? 'authed' : 'login')
        }
      })
      .catch(() => setAuthState('authed'))
  }, [])

  useEffect(() => {
    if (authState !== 'authed') return
    refreshScripts()
    refreshJobs()
    refreshFiles('output')
    refreshCookies()
    refreshComfyStatus()
    refreshClipSources()
    refreshChannels()
  }, [authState])

  useEffect(() => {
    if (authState !== 'authed') return
    const timer = setInterval(refreshJobs, 1500)
    return () => clearInterval(timer)
  }, [authState])

  const selectedJobStatus = useMemo(
    () => jobs.find((j) => j.id === selectedJobId)?.status,
    [jobs, selectedJobId],
  )

  // Log del job seleccionado: carga el contenido actual y, si sigue en marcha,
  // se suscribe al stream SSE para ver las nuevas lineas en vivo.
  useEffect(() => {
    if (authState !== 'authed' || !selectedJobId) {
      setSelectedLog('')
      return
    }

    let cancelled = false
    let source: EventSource | null = null

    api
      .jobLog(selectedJobId)
      .then((content) => {
        if (cancelled) return
        setSelectedLog(content)
        if (selectedJobStatus === 'running' || selectedJobStatus === 'queued') {
          source = api.streamJobLog(selectedJobId, {
            onLine: (line) => setSelectedLog((prev) => (prev ? `${prev}\n${line}` : line)),
            onEnd: () => refreshJobs(),
            onError: () => {},
          })
        }
      })
      .catch((e) => handleApiError(e))

    return () => {
      cancelled = true
      source?.close()
    }
  }, [authState, selectedJobId, selectedJobStatus])

  const activeChannel = useMemo(
    () => channels.find((c) => c.id === activeChannelId) ?? null,
    [channels, activeChannelId],
  )

  useEffect(() => {
    if (activeChannel) {
      setChannelDraft({ name: activeChannel.name, language: activeChannel.language, seoRules: activeChannel.seoRules })
      setYtStatus(null)
      refreshYoutubeStatus(activeChannel.id)
      refreshClipSources(activeChannel.id)
      setActiveCampaignId(null)
      setClipCandidates([])
      refreshCampaigns(activeChannel.id)
    }
  }, [activeChannelId])

  // Retorno del OAuth de YouTube: Google redirige a la raiz con ?code=&state=.
  useEffect(() => {
    if (authState !== 'authed') return
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    const state = params.get('state')
    if (code && state) {
      window.history.replaceState({}, '', window.location.pathname)
      api
        .youtubeFinish(code, state)
        .then((res) => {
          setError('')
          const channelId = Number(state)
          setActiveChannelId(channelId)
          setActiveSection('channel')
          setYtStatus({ hasSecret: true, linked: true, channelName: res.channelName })
          refreshChannels()
        })
        .catch((e) => handleApiError(e))
    }
  }, [authState])

  const selectedScriptInfo = useMemo(
    () => scripts.find((s) => s.name === selectedScript),
    [scripts, selectedScript],
  )

  const stats = useMemo(() => {
    const running = jobs.filter((j) => j.status === 'running').length
    const failed = jobs.filter((j) => j.status === 'failed').length
    const completed = jobs.filter((j) => j.status === 'completed').length
    return { total: jobs.length, running, failed, completed }
  }, [jobs])

  const transcriptFile = useMemo(
    () => (selectedFile && getFileKind(selectedFile.path) === 'audio' ? findSiblingFile(selectedFile.path, '.txt') : null),
    [selectedFile, fileEntries],
  )

  const siblingVideoFile = useMemo(
    () => (selectedFile && getFileKind(selectedFile.path) === 'audio' ? findSiblingFile(selectedFile.path, '.mp4') : null),
    [selectedFile, fileEntries],
  )

  const sourceUrlFile = useMemo(() => {
    if (!selectedFile) return null
    const kind = getFileKind(selectedFile.path)
    if (kind !== 'audio' && kind !== 'video') return null
    return findFileInSameFolder(selectedFile.path, 'source_url.txt')
  }, [selectedFile, fileEntries])

  const sourceJsonFile = useMemo(() => {
    if (!selectedFile) return null
    const kind = getFileKind(selectedFile.path)
    if (kind !== 'audio' && kind !== 'video') return null
    return findFileInSameFolder(selectedFile.path, 'source.json')
  }, [selectedFile, fileEntries])

  const thumbnailFile = useMemo(() => {
    if (!selectedFile) return null
    const kind = getFileKind(selectedFile.path)
    if (kind !== 'audio' && kind !== 'video') return null
    return (
      findSiblingFile(selectedFile.path, '.jpg')
      ?? findSiblingFile(selectedFile.path, '.jpeg')
      ?? findSiblingFile(selectedFile.path, '.png')
      ?? findSiblingFile(selectedFile.path, '.webp')
      ?? findImageInSameFolder(selectedFile.path)
    )
  }, [selectedFile, fileEntries])

  async function handleRun() {
    if (!selectedScript) return
    setIsSubmitting(true)
    setError('')
    try {
      const job = await api.runJob(selectedScript, rawArgs)
      insertOrUpdateJob(job)
      setSelectedJobId(job.id)
      setRawArgs('')
      setSelectedLog('Lanzando job...')
      setActiveSection('jobs')
    } catch (e) {
      handleApiError(e)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleLaunchContentPipeline() {
    if (!contentUrl.trim()) {
      setError('Necesito una URL para descargar el audio.')
      return
    }

    setIsLaunchingContent(true)
    setError('')

    try {
      const job = contentMode === 'audio'
        ? await api.runContentJob({
            url: contentUrl.trim(),
            browser: contentCookiesFile.trim() ? undefined : contentBrowser || undefined,
            cookiesFile: contentCookiesFile.trim() || undefined,
            ffmpeg: contentFfmpeg.trim() || undefined,
            lang: contentLang.trim() || 'auto',
            subtitleFormat: contentSubtitleFormat,
          })
        : await api.runJob(
            'download_video.py',
            `--url "${contentUrl.trim()}"${contentCookiesFile.trim() ? ` --cookies "${contentCookiesFile.trim()}"` : contentBrowser ? ` --browser ${contentBrowser}` : ''}${contentFfmpeg.trim() ? ` --ffmpeg "${contentFfmpeg.trim()}"` : ''}`,
          )
      insertOrUpdateJob(job)
      setSelectedJobId(job.id)
      setSelectedLog(contentMode === 'audio' ? 'Preparando descarga y transcripcion...' : 'Preparando descarga de video MP4...')
      refreshFiles('output')
      setActiveSection('jobs')
    } catch (e) {
      handleApiError(e)
    } finally {
      setIsLaunchingContent(false)
    }
  }

  async function handleUploadAndTranscribe() {
    if (!uploadFolderTitle.trim()) {
      setError('El titulo de carpeta es obligatorio, por ejemplo: audio_rufo_2')
      return
    }

    if (!uploadedMediaFile) {
      setError('Selecciona un archivo mp3, mp4, m4a, wav, ogg u opus.')
      return
    }

    setIsUploadingAndTranscribing(true)
    setError('')

    try {
      const response = await api.uploadAndTranscribe(
        uploadedMediaFile,
        uploadFolderTitle.trim(),
        uploadLang.trim() || 'auto',
        uploadSubtitleFormat,
      )
      insertOrUpdateJob(response.job)
      setSelectedJobId(response.job.id)
      const conversionMessage = response.convertedToMp3Path
        ? `Convertido a MP3: ${response.convertedToMp3Path}\n`
        : ''
      setSelectedLog(
        `Carpeta: ${response.folderPath}\nArchivo subido: ${response.uploadedPath}\n${conversionMessage}Fuente de transcripcion: ${response.transcriptionSourcePath}\nIniciando transcripcion...`,
      )
      setUploadedMediaFile(null)
      refreshFiles(response.folderPath)
      setActiveSection('jobs')
    } catch (e) {
      handleApiError(e)
    } finally {
      setIsUploadingAndTranscribing(false)
    }
  }

  function handleLogin() {
    if (!tokenInput.trim()) return
    setToken(tokenInput.trim())
    setTokenInput('')
    setError('')
    setAuthState('authed')
  }

  function handleLogout() {
    clearToken()
    setAuthState('login')
  }

  if (authState === 'checking') {
    return (
      <div className="login-shell">
        <p className="description">Cargando...</p>
      </div>
    )
  }

  if (authState === 'login') {
    return (
      <div className="login-shell">
        <div className="panel login-card">
          <h1>Media Ops</h1>
          <p className="description">Introduce el token de acceso para continuar.</p>
          {error && <div className="error-box">{error}</div>}
          <input
            type="password"
            placeholder="Token de acceso"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleLogin() }}
          />
          <button className="primary" onClick={handleLogin}>Entrar</button>
        </div>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <h1>Media Ops</h1>
          <p>Control panel</p>
        </div>
        <nav>
          {sections.map((item) => (
            <button
              key={item.id}
              className={item.id === activeSection ? 'nav-btn active' : 'nav-btn'}
              onClick={() => setActiveSection(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="channels-block">
          <div className="channels-head">
            <span>CANALES</span>
            <button className="channel-add" title="Nuevo canal" onClick={handleCreateChannel}>＋</button>
          </div>
          <nav>
            {channels.length === 0 && <p className="channels-empty">Sin canales todavia</p>}
            {channels.map((channel) => (
              <button
                key={channel.id}
                className={channel.id === activeChannelId ? 'nav-btn channel-btn active' : 'nav-btn channel-btn'}
                onClick={() => handleSelectChannel(channel)}
              >
                <span className="channel-avatar">{channel.name.charAt(0).toUpperCase()}</span>
                <span className="channel-name">{channel.name}</span>
                {channel.youtubeLinked && <span className="channel-yt" title="YouTube vinculado">▶</span>}
              </button>
            ))}
          </nav>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <h2>Aplicacion Web para tus Scripts Python</h2>
          <div className="actions-row">
            <button onClick={() => { refreshScripts(); refreshJobs(); refreshFiles(); refreshComfyStatus() }}>Refrescar</button>
            {getToken() && <button onClick={handleLogout}>Salir</button>}
          </div>
        </header>

        {error && <div className="error-box">{error}</div>}

        {activeSection === 'dashboard' && (
          <section className="grid-cards">
            <article className="card"><h3>Scripts</h3><strong>{scripts.length}</strong></article>
            <article className="card"><h3>Jobs Totales</h3><strong>{stats.total}</strong></article>
            <article className="card"><h3>En ejecucion</h3><strong>{stats.running}</strong></article>
            <article className="card"><h3>Fallidos</h3><strong>{stats.failed}</strong></article>
            <article className="card"><h3>Completados</h3><strong>{stats.completed}</strong></article>
            <article className="card">
              <h3>ComfyUI</h3>
              <strong>{comfyStatus?.online ? 'Online' : comfyStatus?.configured ? 'Offline' : 'Sin URL'}</strong>
              {comfyStatus?.online && (
                <p className="card-detail">
                  {comfyStatus.running ?? 0} running / {comfyStatus.pending ?? 0} pending
                </p>
              )}
              {comfyStatus?.configured && !comfyStatus.online && (
                <p className="card-detail">{comfyStatus.error ?? 'No responde'}</p>
              )}
            </article>
          </section>
        )}

        {activeSection === 'content' && (
          <section className="panel">
            <h3>Pipeline URL a Contenido</h3>
            <p className="description">
              Descarga el MP3 desde una URL de video y genera transcripcion, subtitulos y fichero de idioma
              dentro de `output/`.
            </p>

            <div className="form-grid">
              <label className="field">
                <span>Modo</span>
                <select value={contentMode} onChange={(e) => setContentMode(e.target.value as 'audio' | 'video')}>
                  <option value="audio">MP3 + transcripcion</option>
                  <option value="video">Video MP4</option>
                </select>
              </label>

              <label className="field span-2">
                <span>URL del video</span>
                <input
                  type="url"
                  placeholder="https://www.youtube.com/watch?v=..."
                  value={contentUrl}
                  onChange={(e) => setContentUrl(e.target.value)}
                />
              </label>

              <label className="field">
                <span>Navegador cookies</span>
                <select value={contentBrowser} onChange={(e) => setContentBrowser(e.target.value)}>
                  <option value="">sin cookies</option>
                  <option value="chrome">chrome</option>
                  <option value="firefox">firefox</option>
                  <option value="brave">brave</option>
                  <option value="edge">edge</option>
                </select>
              </label>

              <label className="field">
                <span>Cookies</span>
                <select
                  value={contentCookiesFile}
                  onChange={(e) => setContentCookiesFile(e.target.value)}
                >
                  <option value="">sin cookies</option>
                  {cookieEntries.map((item) => (
                    <option key={item.path} value={item.path}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>

              {contentMode === 'audio' && (
                <label className="field">
                  <span>Idioma</span>
                  <input
                    type="text"
                    placeholder="auto"
                    value={contentLang}
                    onChange={(e) => setContentLang(e.target.value)}
                  />
                </label>
              )}

              {contentMode === 'audio' && (
                <label className="field">
                  <span>Formato subtitulos</span>
                  <select
                    value={contentSubtitleFormat}
                    onChange={(e) => setContentSubtitleFormat(e.target.value as 'vtt' | 'srt')}
                  >
                    <option value="vtt">vtt</option>
                    <option value="srt">srt</option>
                  </select>
                </label>
              )}

              <label className="field">
                <span>Ruta ffmpeg</span>
                <input
                  type="text"
                  placeholder="/usr/bin/ffmpeg"
                  value={contentFfmpeg}
                  onChange={(e) => setContentFfmpeg(e.target.value)}
                />
              </label>
            </div>

            <div className="actions-row">
              <button className="primary" disabled={isLaunchingContent} onClick={handleLaunchContentPipeline}>
                {isLaunchingContent ? 'Lanzando...' : contentMode === 'audio' ? 'Descargar y transcribir' : 'Descargar video MP4'}
              </button>
              <button onClick={() => setActiveSection('jobs')}>Ver jobs</button>
              <button onClick={() => { refreshFiles('output'); setActiveSection('files') }}>Ver output</button>
            </div>

            <p className="help">
              Esta pestaña usa un pipeline dedicado para que podamos ir añadiendo nuevos pasos y pantallas sin
              depender de argumentos CLI manuales.
            </p>

            <hr style={{ width: '100%', border: 0, borderTop: '1px solid #1f2937' }} />

            <h3>Subir Archivo y Transcribir</h3>
            <p className="description">
              Sube un `.mp3`, `.mp4`, `.m4a`, `.wav`, `.ogg` u `.opus` y se generara el `.txt` automaticamente.
            </p>

            <div className="form-grid">
              <label className="field span-2">
                <span>Titulo carpeta (obligatorio)</span>
                <input
                  type="text"
                  placeholder="audio_rufo_2"
                  value={uploadFolderTitle}
                  onChange={(e) => setUploadFolderTitle(e.target.value)}
                />
              </label>

              <label className="field span-2">
                <span>Archivo local</span>
                <input
                  type="file"
                  accept=".mp3,.mp4,.m4a,.wav,.ogg,.oga,.opus,audio/*,video/mp4"
                  onChange={(e) => setUploadedMediaFile(e.target.files?.[0] ?? null)}
                />
              </label>

              <label className="field">
                <span>Idioma</span>
                <input
                  type="text"
                  placeholder="auto"
                  value={uploadLang}
                  onChange={(e) => setUploadLang(e.target.value)}
                />
              </label>

              <label className="field">
                <span>Formato subtitulos</span>
                <select
                  value={uploadSubtitleFormat}
                  onChange={(e) => setUploadSubtitleFormat(e.target.value as 'vtt' | 'srt')}
                >
                  <option value="vtt">vtt</option>
                  <option value="srt">srt</option>
                </select>
              </label>
            </div>

            {uploadedMediaFile && <p className="help">Archivo seleccionado: {uploadedMediaFile.name}</p>}

            <div className="actions-row">
              <button
                className="primary"
                disabled={isUploadingAndTranscribing || !uploadFolderTitle.trim()}
                onClick={handleUploadAndTranscribe}
              >
                {isUploadingAndTranscribing ? 'Subiendo...' : 'Subir y transcribir'}
              </button>
              <button onClick={() => { refreshFiles('output/uploads'); setActiveSection('files') }}>
                Ver uploads
              </button>
            </div>
          </section>
        )}

        {activeSection === 'clipping' && (
          <section className="panel">
            <div className="viewer-header">
              <h3>Clipping{activeChannel ? ` — ${activeChannel.name}` : ''}</h3>
            </div>

            <div className="subtabs">
              <button className={clipTab === 'create' ? 'subtab active' : 'subtab'} onClick={() => setClipTab('create')}>Crear campaña</button>
              <button className={clipTab === 'manage' ? 'subtab active' : 'subtab'} onClick={() => { setClipTab('manage'); setActiveCampaignId(null) }}>Mis campañas</button>
              <button className="subtab" onClick={() => setActiveSection('channel')}>YouTube ⚙</button>
            </div>

            {clipTab === 'create' && (
              <>
                <p className="description">
                  Crea una campaña: pega el link del vídeo de YouTube a clipear y el link de la campaña (Whop).
                  El vídeo se descarga y transcribe, y luego generas los shorts.
                </p>

                <div className="form-grid">
                  <label className="field span-2">
                    <span>Nombre de la campaña (opcional)</span>
                    <input value={campName} onChange={(e) => setCampName(e.target.value)} placeholder="Ej: Trailblazers Kate McAndrew" />
                  </label>
                  <label className="field span-2">
                    <span>Link del vídeo a clipear (YouTube o WeTransfer)</span>
                    <input type="url" value={campSourceUrl} onChange={(e) => setCampSourceUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=...  o  https://wetransfer.com/..." />
                  </label>
                  <label className="field span-2">
                    <span>Link de la campaña (Whop)</span>
                    <input type="url" value={campCampaignUrl} onChange={(e) => setCampCampaignUrl(e.target.value)} placeholder="https://whop.com/..." />
                  </label>
                  <label className="field">
                    <span>Cookies (opcional)</span>
                    <select value={campCookies} onChange={(e) => setCampCookies(e.target.value)}>
                      <option value="">sin cookies</option>
                      {cookieEntries.map((item) => (
                        <option key={item.path} value={item.path}>{item.name}</option>
                      ))}
                    </select>
                  </label>
                </div>

                <div className="actions-row">
                  <button className="primary" disabled={isCreatingCampaign || !campSourceUrl.trim()} onClick={handleCreateCampaign}>
                    {isCreatingCampaign ? 'Preparando...' : 'Crear campaña'}
                  </button>
                </div>

                {clipSourceStatus && <p className="help">⏳ {clipSourceStatus}</p>}
              </>
            )}

            {clipTab === 'manage' && (
              <>
                {!activeCampaign ? (
                  <>
                    <p className="description">Tus campañas de este canal. Abre una para ver y gestionar sus shorts.</p>
                    {campaigns.length === 0 && <p className="help">Aún no hay campañas. Crea una en “Crear campaña”.</p>}
                    <div className="jobs-list" style={{ maxHeight: 'unset' }}>
                      {campaigns.map((camp) => (
                        <article key={camp.id} className="card" style={{ boxShadow: 'none' }}>
                          <div className="viewer-header">
                            <div>
                              <h3 style={{ margin: 0 }}>{camp.name}</h3>
                              <p className="help">
                                {camp.status === 'ready' ? '✅ Listo' : camp.status === 'preparing' ? '⏳ Preparando…' : camp.status}
                                {camp.campaignUrl ? ' · con link de campaña' : ''}
                              </p>
                            </div>
                            <div className="actions-row">
                              <button className="primary" disabled={camp.status !== 'ready'} onClick={() => handleOpenCampaign(camp)}>
                                {camp.status === 'ready' ? 'Abrir' : 'Preparando…'}
                              </button>
                              <button onClick={() => handleDeleteCampaign(camp)}>Eliminar</button>
                            </div>
                          </div>
                        </article>
                      ))}
                    </div>
                    <div className="actions-row">
                      <button onClick={() => refreshCampaigns()}>Recargar campañas</button>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="viewer-header">
                      <div>
                        <h3 style={{ margin: 0 }}>{activeCampaign.name}</h3>
                        <div className="actions-row" style={{ marginTop: 6 }}>
                          {activeCampaign.campaignUrl && (
                            <a className="panel-link" href={activeCampaign.campaignUrl} target="_blank" rel="noreferrer">Campaña (Whop)</a>
                          )}
                          <a className="panel-link" href={activeCampaign.sourceUrl} target="_blank" rel="noreferrer">Vídeo original</a>
                        </div>
                      </div>
                      <button onClick={() => setActiveCampaignId(null)}>← Campañas</button>
                    </div>

                    <div className="form-grid">
                      <label className="field">
                        <span>Nombre de la campaña</span>
                        <input
                          value={activeCampaign.name}
                          onChange={(e) => setCampaigns((prev) => prev.map((c) => (c.id === activeCampaign.id ? { ...c, name: e.target.value } : c)))}
                          onBlur={() => handleUpdateCampaign(activeCampaign.id, { name: activeCampaign.name })}
                        />
                      </label>
                      <label className="field">
                        <span>Link de la campaña (Whop)</span>
                        <input
                          type="url"
                          placeholder="https://whop.com/..."
                          value={activeCampaign.campaignUrl}
                          onChange={(e) => setCampaigns((prev) => prev.map((c) => (c.id === activeCampaign.id ? { ...c, campaignUrl: e.target.value } : c)))}
                          onBlur={() => handleUpdateCampaign(activeCampaign.id, { campaignUrl: activeCampaign.campaignUrl })}
                        />
                      </label>
                    </div>

                    <hr style={{ width: '100%', border: 0, borderTop: '1px solid #1f2937' }} />
                    <h3 style={{ margin: '4px 0' }}>Reglas de la campaña (brief)</h3>
                    <div className="form-grid">
                      <label className="field span-2">
                        <span>Link del brief (Google Docs) — la IA extrae los requisitos</span>
                        <input type="url" value={campBriefUrl} onChange={(e) => setCampBriefUrl(e.target.value)} placeholder="https://docs.google.com/document/d/..." />
                      </label>
                      <div className="field" style={{ justifyContent: 'flex-end' }}>
                        <button className="primary" disabled={isExtractingBrief} onClick={() => handleExtractBrief(activeCampaign)}>
                          {isExtractingBrief ? 'Extrayendo...' : 'Extraer requisitos con IA'}
                        </button>
                      </div>
                    </div>

                    {activeCampaign.rules?.captionRequired && (
                      <div className="seo-box">
                        <p className="help">✅ Requisitos aplicados (texto en pantalla + añadidos a la descripción al subir):</p>
                        <div className="seo-field">
                          <div className="seo-head">
                            <span>Caption obligatorio</span>
                            <button className="link-btn" onClick={() => handleCopyUrl(activeCampaign.rules!.captionRequired!)}>Copiar</button>
                          </div>
                          <input readOnly value={activeCampaign.rules.captionRequired} />
                        </div>
                        <div className="seo-field">
                          <div className="seo-head"><span>Texto en pantalla (overlay)</span></div>
                          <input readOnly value={activeCampaign.rules.onScreenText || ''} />
                        </div>
                        <p className="help">
                          Tags → YouTube: {activeCampaign.rules.handles?.youtube || '—'} · TikTok: {activeCampaign.rules.handles?.tiktok || '—'} · IG: {activeCampaign.rules.handles?.instagram || '—'}
                          {activeCampaign.rules.keepWatermark ? ' · ⚠️ mantener marca de agua (no recortar)' : ''}
                        </p>
                        {activeCampaign.rules.sourceUrl && (
                          <p className="help">Metraje oficial: <a className="panel-link" href={activeCampaign.rules.sourceUrl} target="_blank" rel="noreferrer">{activeCampaign.rules.sourceUrl}</a></p>
                        )}
                      </div>
                    )}

                    <hr style={{ width: '100%', border: 0, borderTop: '1px solid #1f2937' }} />

                    <div className="actions-row" style={{ alignItems: 'flex-end' }}>
                      <label className="field" style={{ maxWidth: 130 }}>
                        <span>Nº de clips</span>
                        <input type="number" min={1} max={12} value={clipCount} onChange={(e) => setClipCount(Number(e.target.value) || 5)} />
                      </label>
                      <button className="primary" disabled={isDetectingClips || !selectedClipSource} onClick={() => runDetect(selectedClipSource)}>
                        {isDetectingClips ? 'Analizando...' : clipCandidates.length ? 'Re-detectar clips' : 'Detectar clips'}
                      </button>
                    </div>

                    {clipCandidates.length === 0 && (
                      <p className="description">Aún no hay clips. Pulsa “Detectar clips”.</p>
                    )}

                    <div className="jobs-list" style={{ maxHeight: 'unset' }}>
                  {clipCandidates.map((clip) => (
                    <article key={clip.id} className="card" style={{ boxShadow: 'none' }}>
                      <div className="viewer-header">
                        <div>
                          <h3 style={{ margin: 0 }}>
                            <span className="status completed" style={{ marginRight: 8 }}>{clip.score}</span>
                            {clip.title || 'Clip'}
                          </h3>
                          <p className="help">{formatSeconds(clip.start)} → {formatSeconds(clip.end)} ({Math.round(clip.duration)}s)</p>
                        </div>
                        <div className="actions-row">
                          {clip.uploaded ? <span className="status completed">Subido</span>
                            : clip.rendered ? <span className="status completed">Renderizado</span>
                            : <span className="status queued">Sin generar</span>}
                        </div>
                      </div>

                      <p className="card-detail">{clip.reason}</p>

                      <div className="form-grid">
                        <label className="field">
                          <span>Encuadre</span>
                          <select value={clip.focus} onChange={(e) => handleClipSettingChange(clip, { focus: e.target.value as 'left' | 'center' | 'right' })}>
                            <option value="left">Izquierda</option>
                            <option value="center">Centro</option>
                            <option value="right">Derecha</option>
                          </select>
                        </label>
                        <label className="field">
                          <span>Zoom</span>
                          <select value={String(clip.zoom)} onChange={(e) => handleClipSettingChange(clip, { zoom: Number(e.target.value) })}>
                            <option value="1">Sin zoom</option>
                            <option value="1.3">1.3×</option>
                            <option value="1.6">1.6×</option>
                            <option value="2">2×</option>
                          </select>
                        </label>
                        <label className="field">
                          <span>Proporcion</span>
                          <select value={String(clip.topRatio)} onChange={(e) => handleClipSettingChange(clip, { topRatio: Number(e.target.value) })}>
                            <option value="0.5">50 / 50</option>
                            <option value="0.6">60 / 40</option>
                            <option value="0.7">70 / 30</option>
                            <option value="0.8">80 / 20</option>
                          </select>
                        </label>
                        <label className="field">
                          <span>Subtitulos</span>
                          <select value={clip.subtitles ? 'si' : 'no'} onChange={(e) => handleClipSettingChange(clip, { subtitles: e.target.value === 'si' })}>
                            <option value="si">Si</option>
                            <option value="no">No</option>
                          </select>
                        </label>
                      </div>

                      <label className="field">
                        <span>Texto fijo (visible todo el clip, encima de los subtitulos)</span>
                        <textarea
                          rows={2}
                          placeholder="Ej: Subscribe to @thetrailblazerspod on YouTube for the full episode"
                          value={clip.overlayText || ''}
                          onChange={(e) => setClipCandidates((prev) => prev.map((c) => (c.id === clip.id ? { ...c, overlayText: e.target.value } : c)))}
                          onBlur={() => handleClipSettingChange(clip, { overlayText: clip.overlayText || '' })}
                        />
                      </label>

                      <div className="actions-row">
                        <button className="primary" disabled={renderingClipKey === clip.id} onClick={() => handleRenderClip(clip)}>
                          {renderingClipKey === clip.id ? 'Generando...' : clip.rendered ? 'Regenerar' : 'Generar vertical'}
                        </button>
                        {clip.rendered && clip.renderedPath && (
                          <a className="panel-link" href={api.fileUrl(clip.renderedPath)} target="_blank" rel="noreferrer">Ver / Descargar</a>
                        )}
                        {clip.rendered && !clip.uploaded && (
                          <button className="panel-link panel-link-button" disabled={uploadingClipId === clip.id} onClick={() => handleUploadClip(clip)}>
                            {uploadingClipId === clip.id ? 'Subiendo...' : 'Subir a YouTube'}
                          </button>
                        )}
                        <button className="panel-link panel-link-button" disabled={generatingSeoId === clip.id} onClick={() => handleGenerateSeo(clip)}>
                          {generatingSeoId === clip.id ? 'Generando textos...' : clip.seoTitle ? 'Regenerar textos SEO' : 'Generar textos SEO'}
                        </button>
                      </div>

                      {clip.seoTitle && (
                        <div className="seo-box">
                          <div className="seo-field">
                            <div className="seo-head">
                              <span>Titulo</span>
                              <button className="link-btn" onClick={() => handleCopyUrl(clip.seoTitle!)}>Copiar</button>
                            </div>
                            <input readOnly value={clip.seoTitle} />
                          </div>
                          <div className="seo-field">
                            <div className="seo-head">
                              <span>Descripcion</span>
                              <button className="link-btn" onClick={() => handleCopyUrl(clip.seoDescription || '')}>Copiar</button>
                            </div>
                            <textarea readOnly rows={6} value={clip.seoDescription || ''} />
                          </div>
                          <div className="seo-field">
                            <div className="seo-head">
                              <span>Tags</span>
                              <button className="link-btn" onClick={() => handleCopyUrl(clip.seoTags || '')}>Copiar</button>
                            </div>
                            <textarea readOnly rows={2} value={clip.seoTags || ''} />
                          </div>
                        </div>
                      )}

                      {clip.youtubeUrl && (
                        <div className="actions-row" style={{ alignItems: 'center' }}>
                          <a className="panel-link" href={clip.youtubeUrl} target="_blank" rel="noreferrer">{clip.youtubeUrl}</a>
                          <button className="panel-link panel-link-button" onClick={() => handleCopyUrl(clip.youtubeUrl!)}>
                            {copiedUrl === clip.youtubeUrl ? '¡Copiado!' : 'Copiar enlace'}
                          </button>
                        </div>
                      )}

                      {clip.rendered && clip.renderedPath && (
                        <video className="media-preview" style={{ maxHeight: '46vh', width: 'auto' }} controls src={api.fileUrl(clip.renderedPath)} />
                      )}
                    </article>
                  ))}
                    </div>
                  </>
                )}
              </>
            )}
          </section>
        )}

        {activeSection === 'channel' && (
          <section className="panel">
            {activeChannel ? (
              <>
                <h3>Configuracion del canal: {activeChannel.name}</h3>
                <div className="form-grid">
                  <label className="field span-2">
                    <span>Nombre</span>
                    <input value={channelDraft.name} onChange={(e) => setChannelDraft({ ...channelDraft, name: e.target.value })} />
                  </label>
                  <label className="field">
                    <span>Idioma (para SEO/subtitulos)</span>
                    <select value={channelDraft.language} onChange={(e) => setChannelDraft({ ...channelDraft, language: e.target.value })}>
                      <option value="es">Espanol</option>
                      <option value="en">Ingles</option>
                    </select>
                  </label>
                  <label className="field span-2">
                    <span>Reglas SEO del canal (titulos, descripcion, tags)</span>
                    <textarea rows={4} value={channelDraft.seoRules} onChange={(e) => setChannelDraft({ ...channelDraft, seoRules: e.target.value })} placeholder="Ej: titulos con curiosidad, incluir hashtag #tarot, tono misterioso..." />
                  </label>
                </div>
                <div className="actions-row">
                  <button className="primary" onClick={handleSaveChannel}>{copyFeedback || 'Guardar canal'}</button>
                  <button onClick={() => setActiveSection('clipping')}>Ir a Clipping</button>
                  <button onClick={handleDeleteChannel}>Eliminar canal</button>
                </div>

                <hr style={{ width: '100%', border: 0, borderTop: '1px solid #1f2937' }} />
                <h3>YouTube</h3>
                {ytStatus?.linked ? (
                  <>
                    <p className="description">✅ Canal de YouTube vinculado: <strong>{ytStatus.channelName || activeChannel.youtubeName || 'YouTube'}</strong></p>
                    <p className="help">Si no es el canal correcto, desvincula y vuelve a vincular eligiendo el canal adecuado en Google.</p>
                    <div className="actions-row">
                      <button onClick={handleUnlinkYoutube}>Desvincular / cambiar de canal</button>
                    </div>
                  </>
                ) : (
                  <>
                    <p className="description">
                      1. Sube el <strong>client_secret.json</strong> del proyecto de Google:
                    </p>
                    <div className="actions-row">
                      <input
                        type="file"
                        accept="application/json,.json"
                        onChange={(e) => handleUploadSecret(e.target.files?.[0] ?? null)}
                      />
                      {isUploadingSecret && <span className="help">Subiendo...</span>}
                      {ytStatus?.hasSecret && <span className="help">✅ client_secret cargado</span>}
                    </div>
                    <p className="description">2. Autoriza la cuenta con Google:</p>
                    <div className="actions-row">
                      <button
                        className="primary"
                        disabled={!ytStatus?.hasSecret}
                        onClick={handleLinkYoutube}
                      >
                        Vincular con Google
                      </button>
                    </div>
                    <p className="help">
                      Redirect OAuth: <code>https://mymovi.enguillem.es/</code> (debe estar en “URIs de
                      redireccion autorizados” del cliente OAuth en Google Cloud).
                    </p>
                  </>
                )}
              </>
            ) : (
              <div className="empty-preview">
                <h3>Canales</h3>
                <p className="description">Crea un canal con el boton ＋ de la barra lateral.</p>
              </div>
            )}
          </section>
        )}

        {activeSection === 'execute' && (
          <section className="panel">
            <h3>Lanzar Script</h3>
            <label>Script</label>
            <select value={selectedScript} onChange={(e) => setSelectedScript(e.target.value)}>
              {scripts.map((script) => (
                <option key={script.name} value={script.name}>{script.name}</option>
              ))}
            </select>

            <p className="description">{selectedScriptInfo?.description}</p>
            <p className="help">Args sugeridos: {selectedScriptInfo?.suggestedArgs.join(' ') || 'N/A'}</p>

            <label>Argumentos (formato CLI)</label>
            <textarea
              rows={5}
              placeholder="--url https://youtube.com/... --browser chrome"
              value={rawArgs}
              onChange={(e) => setRawArgs(e.target.value)}
            />

            <button className="primary" disabled={isSubmitting} onClick={handleRun}>
              {isSubmitting ? 'Lanzando...' : 'Ejecutar'}
            </button>
          </section>
        )}

        {activeSection === 'jobs' && (
          <section className="jobs-layout">
            <div className="panel">
              <h3>Historial</h3>
              <div className="jobs-list">
                {jobs.map((job) => (
                  <button key={job.id} className={selectedJobId === job.id ? 'job-item selected' : 'job-item'} onClick={() => setSelectedJobId(job.id)}>
                    <span>{job.script}</span>
                    <span className={`status ${job.status}`}>{job.status}</span>
                  </button>
                ))}
              </div>
            </div>
            <div className="panel">
              <h3>Log</h3>
              <pre>{selectedLog || 'Selecciona un job para ver salida.'}</pre>
            </div>
          </section>
        )}

        {activeSection === 'files' && (
          <section className="files-layout">
            <div className="panel">
              <h3>Explorador: {currentPath}</h3>
              <div className="actions-row">
                <button onClick={() => { setSelectedFile(null); refreshFiles('output') }}>Ir a output</button>
                <button onClick={() => {
                  const parent = currentPath.includes('/') ? currentPath.split('/').slice(0, -1).join('/') : currentPath
                  setSelectedFile(null)
                  refreshFiles(parent || 'output')
                }}>Subir nivel</button>
              </div>
              <ul className="files-list">
                {fileEntries.map((item) => (
                  <li key={item.path}>
                    {item.isDir ? (
                      <button className="link-btn" onClick={() => { setSelectedFile(null); refreshFiles(item.path) }}>📁 {item.name}</button>
                    ) : (
                      <button
                        className={selectedFile?.path === item.path ? 'link-btn file-active' : 'link-btn'}
                        onClick={() => handleOpenFile(item)}
                      >
                        📄 {item.name}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>

            <div className="panel">
              {selectedFile ? (
                <>
                  <div className="viewer-header">
                    <div>
                      <h3>Visor: {selectedFile.name}</h3>
                      <p className="help">{selectedFile.path}</p>
                    </div>
                    <div className="actions-row">
                      <a className="panel-link" href={api.fileUrl(selectedFile.path)} target="_blank" rel="noreferrer">
                        Abrir en nueva pestaña
                      </a>
                      <a className="panel-link" href={api.fileUrl(selectedFile.path)} download>
                        Descargar
                      </a>
                      {getFileKind(selectedFile.path) === 'text' && (
                        <button className="panel-link panel-link-button" onClick={handleCopyText}>
                          {copyFeedback || 'Copiar texto'}
                        </button>
                      )}
                      {getFileKind(selectedFile.path) === 'audio' && transcriptFile && (
                        <a className="panel-link" href={api.fileUrl(transcriptFile.path)} download>
                          Descargar transcripcion
                        </a>
                      )}
                      {getFileKind(selectedFile.path) === 'audio' && siblingVideoFile && (
                        <button className="panel-link panel-link-button" onClick={() => handleOpenFile(siblingVideoFile)}>
                          Ver video MP4
                        </button>
                      )}
                      {getFileKind(selectedFile.path) === 'audio' && thumbnailFile && (
                        <button className="panel-link panel-link-button" onClick={() => handleOpenFile(thumbnailFile)}>
                          Ver miniatura
                        </button>
                      )}
                      {getFileKind(selectedFile.path) === 'audio' && sourceUrlFile && !siblingVideoFile && (
                        <button
                          className="panel-link panel-link-button"
                          disabled={isDownloadingVideo}
                          onClick={handleDownloadVideoFromSource}
                        >
                          {isDownloadingVideo ? 'Lanzando yt-dlp...' : 'Descargar video con yt-dlp'}
                        </button>
                      )}
                      {getFileKind(selectedFile.path) === 'audio' && sourceUrlFile && siblingVideoFile && !thumbnailFile && (
                        <button
                          className="panel-link panel-link-button"
                          disabled={isDownloadingThumbnail}
                          onClick={handleDownloadThumbnailFromSource}
                        >
                          {isDownloadingThumbnail ? 'Lanzando yt-dlp...' : 'Descargar miniatura'}
                        </button>
                      )}
                      {getFileKind(selectedFile.path) === 'audio' && !transcriptFile && (
                        <button
                          className="panel-link panel-link-button"
                          disabled={isGeneratingTranscript}
                          onClick={() => handleGenerateTranscript(selectedFile)}
                        >
                          {isGeneratingTranscript ? 'Generando...' : 'Generar transcripcion'}
                        </button>
                      )}
                      {getFileKind(selectedFile.path) === 'video' && (
                        <button
                          className="panel-link panel-link-button"
                          disabled={isDetectingInsertedFrames}
                          onClick={() => handleDetectInsertedFrames(selectedFile)}
                        >
                          {isDetectingInsertedFrames ? 'Analizando...' : 'Detectar frames incrustados'}
                        </button>
                      )}
                      {getFileKind(selectedFile.path) === 'video' && thumbnailFile && (
                        <button className="panel-link panel-link-button" onClick={() => handleOpenFile(thumbnailFile)}>
                          Ver miniatura
                        </button>
                      )}
                      {getFileKind(selectedFile.path) === 'video' && sourceUrlFile && !thumbnailFile && (
                        <button
                          className="panel-link panel-link-button"
                          disabled={isDownloadingThumbnail}
                          onClick={handleDownloadThumbnailFromSource}
                        >
                          {isDownloadingThumbnail ? 'Lanzando yt-dlp...' : 'Descargar miniatura'}
                        </button>
                      )}
                      {getFileKind(selectedFile.path) === 'image' && !selectedFile.path.toLowerCase().endsWith('.png') && (
                        <button
                          className="panel-link panel-link-button"
                          disabled={isConvertingImageToPng}
                          onClick={() => handleConvertImageToPng(selectedFile)}
                        >
                          {isConvertingImageToPng ? 'Convirtiendo...' : 'Convertir a PNG'}
                        </button>
                      )}
                    </div>
                  </div>

                  {getFileKind(selectedFile.path) === 'text' && (
                    <pre className="file-preview">{isLoadingFile ? 'Cargando contenido...' : selectedFileContent || 'Fichero vacio.'}</pre>
                  )}

                  {getFileKind(selectedFile.path) === 'audio' && (
                    <audio className="media-preview" controls src={api.fileUrl(selectedFile.path)} />
                  )}

                  {getFileKind(selectedFile.path) === 'video' && (
                    <video className="media-preview" controls src={api.fileUrl(selectedFile.path)} />
                  )}

                  {getFileKind(selectedFile.path) === 'image' && (
                    <img className="image-preview" src={api.fileUrl(selectedFile.path)} alt={selectedFile.name} />
                  )}

                  {getFileKind(selectedFile.path) === 'other' && (
                    <div className="empty-preview">
                      <p className="description">No hay vista embebida para este tipo de fichero.</p>
                      <a className="panel-link" href={api.fileUrl(selectedFile.path)} target="_blank" rel="noreferrer">
                        Abrir o descargar fichero
                      </a>
                    </div>
                  )}
                </>
              ) : (
                <div className="empty-preview">
                  <h3>Visor</h3>
                  <p className="description">Haz clic en un fichero para visualizar su contenido aqui.</p>
                </div>
              )}
            </div>
          </section>
        )}
      </main>
    </div>
  )
}
