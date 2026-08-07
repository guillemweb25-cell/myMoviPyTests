import { useEffect, useMemo, useState } from 'react'
import { api, clearToken, getToken, setToken, UnauthorizedError } from './api'
import type { ClipCandidate, ClipSource, ComfyStatus, FileEntry, Job, ScriptInfo } from './types'

type Section = 'dashboard' | 'content' | 'clipping' | 'execute' | 'jobs' | 'files'

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

  const [clipSources, setClipSources] = useState<ClipSource[]>([])
  const [selectedClipSource, setSelectedClipSource] = useState('')
  const [clipCandidates, setClipCandidates] = useState<ClipCandidate[]>([])
  const [clipCount, setClipCount] = useState(5)
  const [clipSubtitles, setClipSubtitles] = useState(true)
  const [clipTopRatio, setClipTopRatio] = useState(0.7)
  const [clipUrl, setClipUrl] = useState('')
  const [clipUrlCookies, setClipUrlCookies] = useState('')
  const [isPreparingSource, setIsPreparingSource] = useState(false)
  const [clipSourceStatus, setClipSourceStatus] = useState('')
  const [isDetectingClips, setIsDetectingClips] = useState(false)
  const [renderingClipKey, setRenderingClipKey] = useState('')

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

  async function refreshClipSources() {
    try {
      const data = await api.clipSources()
      setClipSources(data)
      if (!selectedClipSource && data.length > 0) {
        setSelectedClipSource(data[0].transcriptPath)
      }
    } catch (e) {
      handleApiError(e)
    }
  }

  async function runDetect(transcriptPath: string) {
    setIsDetectingClips(true)
    setError('')
    setClipCandidates([])
    try {
      const data = await api.detectClips(transcriptPath, clipCount, 15, 60)
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
      const sources = await api.clipSources()
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

  async function handleRenderClip(clip: ClipCandidate) {
    const source = clipSources.find((item) => item.transcriptPath === selectedClipSource)
    if (!source) return
    const key = `${clip.start}-${clip.end}`
    setRenderingClipKey(key)
    setError('')
    try {
      const job = await api.renderClip({
        video: source.videoPath,
        start: clip.start,
        end: clip.end,
        subtitles: clipSubtitles,
        topRatio: clipTopRatio,
        title: clip.title,
      })
      insertOrUpdateJob(job)
      setSelectedJobId(job.id)
      setSelectedLog(`Renderizando clip vertical [${clip.start}s - ${clip.end}s]...`)
      setActiveSection('jobs')
    } catch (e) {
      handleApiError(e)
    } finally {
      setRenderingClipKey('')
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
            <h3>Clipping — clips verticales virales</h3>
            <p className="description">
              Elige un video con transcripcion (o descarga uno nuevo desde una URL). La IA propone los
              mejores momentos y los conviertes en clips verticales 1080×1920 (pantalla partida) con
              subtitulos karaoke opcionales.
            </p>

            <div className="form-grid">
              <label className="field span-2">
                <span>Descargar y preparar desde URL</span>
                <input
                  type="url"
                  placeholder="https://... (descarga el video y lo transcribe)"
                  value={clipUrl}
                  onChange={(e) => setClipUrl(e.target.value)}
                />
              </label>

              <label className="field">
                <span>Cookies (opcional)</span>
                <select value={clipUrlCookies} onChange={(e) => setClipUrlCookies(e.target.value)}>
                  <option value="">sin cookies</option>
                  {cookieEntries.map((item) => (
                    <option key={item.path} value={item.path}>{item.name}</option>
                  ))}
                </select>
              </label>

              <div className="field" style={{ justifyContent: 'flex-end' }}>
                <button className="primary" disabled={isPreparingSource || !clipUrl.trim()} onClick={handlePrepareClipSource}>
                  {isPreparingSource ? 'Procesando...' : 'Descargar y transcribir'}
                </button>
              </div>
            </div>

            {clipSourceStatus && <p className="help">⏳ {clipSourceStatus}</p>}

            <hr style={{ width: '100%', border: 0, borderTop: '1px solid #1f2937' }} />

            <div className="form-grid">
              <label className="field span-2">
                <span>Video (con transcripcion)</span>
                <select value={selectedClipSource} onChange={(e) => { setSelectedClipSource(e.target.value); setClipCandidates([]) }}>
                  {clipSources.length === 0 && <option value="">No hay videos con transcripcion</option>}
                  {clipSources.map((item) => (
                    <option key={item.transcriptPath} value={item.transcriptPath}>{item.name}</option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span>Nº de clips</span>
                <input type="number" min={1} max={12} value={clipCount} onChange={(e) => setClipCount(Number(e.target.value) || 5)} />
              </label>

              <label className="field">
                <span>Subtitulos karaoke</span>
                <select value={clipSubtitles ? 'si' : 'no'} onChange={(e) => setClipSubtitles(e.target.value === 'si')}>
                  <option value="si">Si, incrustados</option>
                  <option value="no">No</option>
                </select>
              </label>

              <label className="field">
                <span>Proporcion (clip arriba)</span>
                <select value={String(clipTopRatio)} onChange={(e) => setClipTopRatio(Number(e.target.value))}>
                  <option value="0.5">50 / 50</option>
                  <option value="0.6">60 / 40</option>
                  <option value="0.7">70 / 30</option>
                  <option value="0.8">80 / 20</option>
                </select>
              </label>
            </div>

            <div className="actions-row">
              <button className="primary" disabled={isDetectingClips || !selectedClipSource} onClick={handleDetectClips}>
                {isDetectingClips ? 'Analizando transcripcion...' : 'Detectar clips virales'}
              </button>
              <button onClick={refreshClipSources}>Recargar videos</button>
            </div>

            {clipCandidates.length > 0 && (
              <div className="jobs-list" style={{ maxHeight: 'unset' }}>
                {clipCandidates.map((clip) => {
                  const key = `${clip.start}-${clip.end}`
                  return (
                    <article key={key} className="card" style={{ boxShadow: 'none' }}>
                      <div className="viewer-header">
                        <div>
                          <h3 style={{ margin: 0 }}>
                            <span className="status completed" style={{ marginRight: 8 }}>{clip.score}</span>
                            {clip.title || 'Clip'}
                          </h3>
                          <p className="help">
                            {formatSeconds(clip.start)} → {formatSeconds(clip.end)} ({Math.round(clip.duration)}s)
                          </p>
                        </div>
                        <button
                          className="panel-link panel-link-button"
                          disabled={renderingClipKey === key}
                          onClick={() => handleRenderClip(clip)}
                        >
                          {renderingClipKey === key ? 'Enviando...' : 'Renderizar vertical'}
                        </button>
                      </div>
                      <p className="card-detail">{clip.reason}</p>
                      {clip.transcript && <p className="card-detail" style={{ opacity: 0.7 }}>“{clip.transcript}”</p>}
                    </article>
                  )
                })}
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
