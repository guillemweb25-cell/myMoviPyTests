import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import type { DuplicateContentCheck, FileEntry, Job, ScriptInfo } from './types'

type Section = 'dashboard' | 'content' | 'contentBlue' | 'execute' | 'jobs' | 'files'

const sections: { id: Section; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'content', label: 'Contenido Web' },
  { id: 'contentBlue', label: 'Descargar Azul' },
  { id: 'execute', label: 'Ejecutar Scripts' },
  { id: 'jobs', label: 'Historial' },
  { id: 'files', label: 'Explorador Output' },
]

const bluePresets = [
  { label: 'sin preset', value: '' },
  { label: 'posts comprados', value: '--download-type purchased' },
  { label: 'mensajes', value: '--download-type messages' },
  { label: 'timeline', value: '--download-type timeline' },
  { label: 'archivado', value: '--download-type archived' },
  { label: 'solo videos', value: '--mediatype videos' },
]

function getUnsupportedContentMessage(url: string) {
  try {
    const hostname = new URL(url.trim()).hostname.toLowerCase().replace(/^www\./, '')
    if (hostname === 'onlyfans.com') {
      return 'OnlyFans no esta soportado por este flujo con yt-dlp, aunque tengas cookies validas.'
    }
  } catch {
    return ''
  }

  return ''
}

function summarizeBlueLog(log: string) {
  if (!log.trim()) return null

  const flags = {
    authenticated: log.includes('Welcome, '),
    mediaDetected: log.includes('Returning 1 items') || /Returning \d+ items/.test(log),
    cdmError: log.includes('CDM return an error'),
    authError: log.includes('checking auth status') && (log.includes('auth failed') || log.includes('auth.json')),
    unsupportedOption: log.includes('No such option:'),
    zeroDownloads: log.includes('0 downloads total'),
    failedCount: /(\d+) failed/.exec(log)?.[1] ?? '',
  }

  if (flags.unsupportedOption) {
    return {
      tone: 'warning',
      title: 'Argumentos no validos para OF-Scraper',
      detail: 'El comando arranco, pero algun argumento extra no existe para ese subcomando.',
    }
  }

  if (flags.authError && !flags.authenticated) {
    return {
      tone: 'warning',
      title: 'Autenticacion pendiente o invalida',
      detail: 'OF-Scraper no parece haber podido completar la autenticacion con el perfil actual.',
    }
  }

  if (flags.authenticated && flags.mediaDetected && flags.cdmError) {
    return {
      tone: 'warning',
      title: 'Autenticacion correcta, pero fallo en CDM',
      detail: 'El media fue detectado, pero la descarga parece fallar en la parte protegida o cifrada.',
    }
  }

  if (flags.authenticated && flags.mediaDetected && flags.zeroDownloads) {
    return {
      tone: 'warning',
      title: 'Media detectado pero no descargado',
      detail: `OF-Scraper encontro contenido, pero termino sin descargas y con ${flags.failedCount || 'algun'} fallo.`,
    }
  }

  if (flags.authenticated && flags.mediaDetected) {
    return {
      tone: 'ok',
      title: 'Autenticacion y deteccion correctas',
      detail: 'El flujo azul esta entrando bien en la cuenta y localizando media para procesar.',
    }
  }

  return {
    tone: 'neutral',
    title: 'Log sin diagnostico claro',
    detail: 'El flujo azul se ejecuto, pero este log no encaja en uno de los patrones conocidos todavia.',
  }
}

export default function App() {
  const [activeSection, setActiveSection] = useState<Section>('dashboard')
  const [scripts, setScripts] = useState<ScriptInfo[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
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
  const [isDetectingInsertedFrames, setIsDetectingInsertedFrames] = useState(false)
  const [copyFeedback, setCopyFeedback] = useState('')

  const [contentUrl, setContentUrl] = useState('')
  const [contentMode, setContentMode] = useState<'audio' | 'video'>('audio')
  const [contentBrowser, setContentBrowser] = useState('')
  const [contentCookiesFile, setContentCookiesFile] = useState('')
  const [contentFfmpeg, setContentFfmpeg] = useState('')
  const [contentLang, setContentLang] = useState('auto')
  const [contentSubtitleFormat, setContentSubtitleFormat] = useState<'vtt' | 'srt'>('vtt')
  const [duplicateCheck, setDuplicateCheck] = useState<DuplicateContentCheck | null>(null)
  const [isCheckingDuplicate, setIsCheckingDuplicate] = useState(false)
  const [blueTarget, setBlueTarget] = useState('')
  const [blueBinary, setBlueBinary] = useState('ofscraper')
  const [blueProfile, setBlueProfile] = useState('main')
  const [blueConfigPath, setBlueConfigPath] = useState('ofscraper/config.json')
  const [bluePreset, setBluePreset] = useState('')
  const [blueExtraArgs, setBlueExtraArgs] = useState('')
  const [isLaunchingBlue, setIsLaunchingBlue] = useState(false)

  async function refreshScripts() {
    try {
      const data = await api.scripts()
      setScripts(data)
      if (!selectedScript && data.length > 0) {
        setSelectedScript(data[0].name)
      }
    } catch (e) {
      setError(String(e))
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
      setError(String(e))
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
      setError(String(e))
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
      setError(String(e))
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
      setError(String(e))
    } finally {
      setIsGeneratingTranscript(false)
    }
  }

  async function checkDuplicateUrl(url: string) {
    const trimmedUrl = url.trim()
    if (!trimmedUrl) {
      setDuplicateCheck(null)
      return
    }

    setIsCheckingDuplicate(true)
    try {
      const data = await api.checkDuplicateContent(trimmedUrl)
      setDuplicateCheck(data)
    } catch (e) {
      setError(String(e))
    } finally {
      setIsCheckingDuplicate(false)
    }
  }

  async function handleCopyText() {
    if (!selectedFileContent) return
    try {
      await navigator.clipboard.writeText(selectedFileContent)
      setCopyFeedback('Texto copiado')
      window.setTimeout(() => setCopyFeedback(''), 1500)
    } catch (e) {
      setError(String(e))
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

      const unsupportedMessage = getUnsupportedContentMessage(sourceUrl)
      if (unsupportedMessage) {
        throw new Error(unsupportedMessage)
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
      setError(String(e))
    } finally {
      setIsDownloadingVideo(false)
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
      setError(String(e))
    } finally {
      setIsDetectingInsertedFrames(false)
    }
  }

  useEffect(() => {
    refreshScripts()
    refreshJobs()
    refreshFiles('output')
    refreshCookies()
  }, [])

  useEffect(() => {
    const timer = setInterval(refreshJobs, 1500)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    if (!selectedJobId) return
    api.jobLog(selectedJobId).then(setSelectedLog).catch((e) => setError(String(e)))
  }, [selectedJobId, jobs])

  const selectedScriptInfo = useMemo(
    () => scripts.find((s) => s.name === selectedScript),
    [scripts, selectedScript],
  )

  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedJobId) ?? null,
    [jobs, selectedJobId],
  )

  const blueLogSummary = useMemo(
    () => (selectedJob?.script === 'run_ofscraper.py' ? summarizeBlueLog(selectedLog) : null),
    [selectedJob, selectedLog],
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

  const sourceUrlFile = useMemo(
    () => (selectedFile && getFileKind(selectedFile.path) === 'audio' ? fileEntries.find((item) => item.path.endsWith('/source_url.txt') || item.name === 'source_url.txt') ?? null : null),
    [selectedFile, fileEntries],
  )

  const sourceJsonFile = useMemo(
    () => (selectedFile && getFileKind(selectedFile.path) === 'audio' ? fileEntries.find((item) => item.path.endsWith('/source.json') || item.name === 'source.json') ?? null : null),
    [selectedFile, fileEntries],
  )

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
      setError(String(e))
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleLaunchContentPipeline() {
    if (!contentUrl.trim()) {
      setError('Necesito una URL para descargar el audio.')
      return
    }

    const unsupportedMessage = getUnsupportedContentMessage(contentUrl)
    if (unsupportedMessage) {
      setError(unsupportedMessage)
      return
    }

    const duplicateData = await api.checkDuplicateContent(contentUrl.trim())
    setDuplicateCheck(duplicateData)
    if (duplicateData.exists) {
      setError('Esta URL ya existe en output. Revisa la carpeta detectada antes de descargarla de nuevo.')
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
      setError(String(e))
    } finally {
      setIsLaunchingContent(false)
    }
  }

  async function handleLaunchBlue() {
    if (!blueTarget.trim()) {
      setError('Necesito una URL o target para el flujo azul.')
      return
    }

    setIsLaunchingBlue(true)
    setError('')

    try {
      const job = await api.runBlueJob({
        target: blueTarget.trim(),
        binary: blueBinary.trim() || 'ofscraper',
        profile: blueProfile.trim() || undefined,
        configPath: blueConfigPath.trim() || undefined,
        extraArgs: [bluePreset.trim(), blueExtraArgs.trim()].filter(Boolean).join(' ') || undefined,
      })
      insertOrUpdateJob(job)
      setSelectedJobId(job.id)
      setSelectedLog('Preparando flujo aislado OF-Scraper...')
      setActiveSection('jobs')
    } catch (e) {
      setError(String(e))
    } finally {
      setIsLaunchingBlue(false)
    }
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
          <button onClick={() => { refreshScripts(); refreshJobs(); refreshFiles() }}>Refrescar</button>
        </header>

        {error && <div className="error-box">{error}</div>}

        {activeSection === 'dashboard' && (
          <section className="grid-cards">
            <article className="card"><h3>Scripts</h3><strong>{scripts.length}</strong></article>
            <article className="card"><h3>Jobs Totales</h3><strong>{stats.total}</strong></article>
            <article className="card"><h3>En ejecucion</h3><strong>{stats.running}</strong></article>
            <article className="card"><h3>Fallidos</h3><strong>{stats.failed}</strong></article>
            <article className="card"><h3>Completados</h3><strong>{stats.completed}</strong></article>
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
                  onBlur={(e) => { void checkDuplicateUrl(e.target.value) }}
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

            {isCheckingDuplicate && <p className="help">Comprobando si la URL ya existe...</p>}

            {duplicateCheck?.exists && duplicateCheck.matches[0] && (
              <div className="warning-box">
                <strong>URL duplicada detectada</strong>
                <p className="help">Ya existe contenido descargado para esta URL.</p>
                <p className="help">{duplicateCheck.matches[0].folder}</p>
                <div className="actions-row">
                  <button
                    onClick={() => {
                      setActiveSection('files')
                      setSelectedFile(null)
                      refreshFiles(duplicateCheck.matches[0].folder)
                    }}
                  >
                    Abrir carpeta existente
                  </button>
                </div>
              </div>
            )}

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
          </section>
        )}

        {activeSection === 'contentBlue' && (
          <section className="panel">
            <h3>Descargar Azul</h3>
            <p className="description">
              Esta seccion queda separada del flujo principal para probar integraciones nuevas sin interferir con
              la descarga y transcripcion que ya te funciona.
            </p>

            <div className="warning-box">
              <strong>Zona aislada de pruebas</strong>
              <p className="help">
                Aqui usamos un wrapper independiente para `ofscraper`. No reutiliza la logica de `yt-dlp` y queda
                encapsulado para no romper el flujo principal.
              </p>
            </div>

            <div className="form-grid">
              <label className="field span-2">
                <span>URL o target</span>
                <input
                  type="text"
                  placeholder="https://onlyfans.com/... o target equivalente"
                  value={blueTarget}
                  onChange={(e) => setBlueTarget(e.target.value)}
                />
              </label>

              <label className="field">
                <span>Binario</span>
                <input
                  type="text"
                  placeholder="ofscraper"
                  value={blueBinary}
                  onChange={(e) => setBlueBinary(e.target.value)}
                />
              </label>

              <label className="field">
                <span>Perfil</span>
                <input
                  type="text"
                  placeholder="main"
                  value={blueProfile}
                  onChange={(e) => setBlueProfile(e.target.value)}
                />
              </label>

              <label className="field">
                <span>Preset</span>
                <select value={bluePreset} onChange={(e) => setBluePreset(e.target.value)}>
                  {bluePresets.map((preset) => (
                    <option key={preset.label} value={preset.value}>
                      {preset.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field span-2">
                <span>Ruta config</span>
                <input
                  type="text"
                  placeholder="ofscraper/config.json"
                  value={blueConfigPath}
                  onChange={(e) => setBlueConfigPath(e.target.value)}
                />
              </label>

              <label className="field span-2">
                <span>Argumentos extra</span>
                <input
                  type="text"
                  placeholder="--download-type protected --some-other-flag"
                  value={blueExtraArgs}
                  onChange={(e) => setBlueExtraArgs(e.target.value)}
                />
              </label>
            </div>

            <div className="actions-row">
              <button className="primary" disabled={isLaunchingBlue} onClick={handleLaunchBlue}>
                {isLaunchingBlue ? 'Lanzando...' : 'Lanzar OF-Scraper'}
              </button>
              <button onClick={() => setActiveSection('jobs')}>Ver jobs</button>
              <button onClick={() => setActiveSection('content')}>Volver a Contenido Web</button>
            </div>

            <p className="help">
              Este flujo asume que `ofscraper` ya esta instalado y autenticado en el entorno del backend. Si no lo
              encuentra, el log te lo dira claramente.
            </p>
            <p className="help">
              Sugerencia: guarda tu configuracion en `ofscraper/` y combina un preset con argumentos extra solo
              cuando necesites afinar mas.
            </p>
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
              {blueLogSummary && (
                <div className={`log-summary log-summary-${blueLogSummary.tone}`}>
                  <strong>{blueLogSummary.title}</strong>
                  <p className="help">{blueLogSummary.detail}</p>
                </div>
              )}
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
                      {getFileKind(selectedFile.path) === 'audio' && sourceUrlFile && !siblingVideoFile && (
                        <button
                          className="panel-link panel-link-button"
                          disabled={isDownloadingVideo}
                          onClick={handleDownloadVideoFromSource}
                        >
                          {isDownloadingVideo ? 'Lanzando yt-dlp...' : 'Descargar video con yt-dlp'}
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
