import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import type { FileEntry, Job, ScriptInfo } from './types'

type Section = 'dashboard' | 'content' | 'execute' | 'jobs' | 'files'

const sections: { id: Section; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'content', label: 'Contenido Web' },
  { id: 'execute', label: 'Ejecutar Scripts' },
  { id: 'jobs', label: 'Historial' },
  { id: 'files', label: 'Explorador Output' },
]

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
  const [uploadedMediaFile, setUploadedMediaFile] = useState<File | null>(null)
  const [uploadLang, setUploadLang] = useState('auto')
  const [uploadSubtitleFormat, setUploadSubtitleFormat] = useState<'vtt' | 'srt'>('vtt')
  const [isUploadingAndTranscribing, setIsUploadingAndTranscribing] = useState(false)

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

  async function handleUploadAndTranscribe() {
    if (!uploadedMediaFile) {
      setError('Selecciona un archivo mp3, mp4, m4a o wav.')
      return
    }

    setIsUploadingAndTranscribing(true)
    setError('')

    try {
      const response = await api.uploadAndTranscribe(
        uploadedMediaFile,
        uploadLang.trim() || 'auto',
        uploadSubtitleFormat,
      )
      insertOrUpdateJob(response.job)
      setSelectedJobId(response.job.id)
      setSelectedLog(`Archivo subido: ${response.uploadedPath}\nIniciando transcripcion...`)
      setUploadedMediaFile(null)
      refreshFiles('output/uploads')
      setActiveSection('jobs')
    } catch (e) {
      setError(String(e))
    } finally {
      setIsUploadingAndTranscribing(false)
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

            <hr style={{ width: '100%', border: 0, borderTop: '1px solid #cbd5e1' }} />

            <h3>Subir Archivo y Transcribir</h3>
            <p className="description">
              Sube un `.mp3`, `.mp4`, `.m4a` o `.wav` y se generara el `.txt` automaticamente.
            </p>

            <div className="form-grid">
              <label className="field span-2">
                <span>Archivo local</span>
                <input
                  type="file"
                  accept=".mp3,.mp4,.m4a,.wav,audio/*,video/mp4"
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
                disabled={isUploadingAndTranscribing}
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
