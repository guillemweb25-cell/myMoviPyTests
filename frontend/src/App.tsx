import { useEffect, useMemo, useRef, useState } from 'react'
import { api, clearToken, getToken, setToken, UnauthorizedError } from './api'
import type { Campaign, Channel, ClipCandidate, ClipSource, ComfyStatus, FileEntry, Job, ScriptInfo } from './types'

type Section = 'dashboard' | 'content' | 'clipping' | 'reels' | 'plants' | 'eggs' | 'butterflies' | 'channel' | 'execute' | 'jobs' | 'files'

const sections: { id: Section; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'content', label: 'Contenido Web' },
  { id: 'clipping', label: 'Clipping' },
  { id: 'reels', label: '🎬 Avatar Reel' },
  { id: 'plants', label: '🪴 Macetas' },
  { id: 'eggs', label: '🥚 Huevos' },
  { id: 'butterflies', label: '🦋 Mariposas' },
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

/** Como formatSeconds pero sin perder décimas (para editar fragmentos sin redondear). */
function formatPrecise(value: number): string {
  const v = Math.max(0, Math.round(value * 10) / 10)
  const minutes = Math.floor(v / 60)
  const seconds = (v - minutes * 60).toFixed(1).replace(/\.0$/, '')
  return `${minutes}:${seconds.padStart(seconds.includes('.') ? 4 : 2, '0')}`
}

function formatSegments(segments: [number, number][]): string {
  return segments.map(([a, b]) => `${formatPrecise(a)}-${formatPrecise(b)}`).join(', ')
}

/** Tramos del vídeo fuente que usa un clip (varios si es combinado). */
function sourceRanges(c: ClipCandidate): [number, number][] {
  return c.segments?.length ? c.segments : [[c.start, c.end]]
}

/** "2:17", "1:02:17", "137" o "2:17.5" -> segundos. null si no se entiende. */
function parseTimecode(value: string): number | null {
  const v = value.trim().replace(',', '.')
  if (!/^\d+(\.\d+)?$|^\d+(:\d{1,2}){1,2}(\.\d+)?$/.test(v)) return null
  return v.split(':').reduce((acc, part) => acc * 60 + Number(part), 0)
}

type NavState = { section?: Section; channelId?: number | null; clipTab?: 'create' | 'manage' | 'youtube'; campaignId?: number | null }

function loadNav(): NavState {
  try {
    return JSON.parse(localStorage.getItem('mediaops_nav') || '{}') as NavState
  } catch {
    return {}
  }
}

// Posicion de scroll (ventana) para volver al mismo sitio tras recargar la
// pestana en el movil (al cambiar de app y volver, el navegador la recarga).
function loadScroll(): number {
  const v = Number(localStorage.getItem('mediaops_scroll') || '0')
  return Number.isFinite(v) ? v : 0
}

function saveScroll(): void {
  try {
    localStorage.setItem('mediaops_scroll', String(Math.round(window.scrollY)))
  } catch {
    /* almacenamiento no disponible */
  }
}

export default function App() {
  const [authState, setAuthState] = useState<'checking' | 'authed' | 'login'>('checking')
  const [tokenInput, setTokenInput] = useState('')
  const [activeSection, setActiveSection] = useState<Section>(() => loadNav().section || 'dashboard')
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
  const [manualStart, setManualStart] = useState('')
  const [manualEnd, setManualEnd] = useState('')
  const [manualTitle, setManualTitle] = useState('')
  const [isAddingManual, setIsAddingManual] = useState(false)
  const [combineIds, setCombineIds] = useState<string[]>([])
  const [combineTarget, setCombineTarget] = useState(45)
  const [isCombining, setIsCombining] = useState(false)
  const [segmentDrafts, setSegmentDrafts] = useState<Record<string, string>>({})
  const [savingSegmentsId, setSavingSegmentsId] = useState<string | null>(null)
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
  const [activeChannelId, setActiveChannelId] = useState<number | null>(() => loadNav().channelId ?? null)
  const [channelDraft, setChannelDraft] = useState<{ name: string; language: string; seoRules: string }>({ name: '', language: 'es', seoRules: '' })
  const [ytStatus, setYtStatus] = useState<{ hasSecret: boolean; linked: boolean; channelName: string } | null>(null)
  const [isUploadingSecret, setIsUploadingSecret] = useState(false)

  const [clipSources, setClipSources] = useState<ClipSource[]>([])
  const [selectedClipSource, setSelectedClipSource] = useState('')
  const [clipCandidates, setClipCandidates] = useState<ClipCandidate[]>([])
  const [clipParts, setClipParts] = useState(4)
  const [clipsPerPart, setClipsPerPart] = useState(5)
  const [clipTargetDur, setClipTargetDur] = useState(40)
  const [clipUrl, setClipUrl] = useState('')
  const [clipUrlCookies, setClipUrlCookies] = useState('')
  const [isPreparingSource, setIsPreparingSource] = useState(false)
  const [clipSourceStatus, setClipSourceStatus] = useState('')
  const [isDetectingClips, setIsDetectingClips] = useState(false)
  const [renderingClipKey, setRenderingClipKey] = useState('')
  const [uploadingClipId, setUploadingClipId] = useState('')
  const [generatingSeoId, setGeneratingSeoId] = useState('')
  const [uploadPrivacy, setUploadPrivacy] = useState('public')
  const [renderNonce, setRenderNonce] = useState<Record<string, number>>({})
  const [clipFrames, setClipFrames] = useState<Record<string, { percent: number; path: string }[]>>({})
  const [extractingFramesId, setExtractingFramesId] = useState('')
  const [clipPersons, setClipPersons] = useState<Record<string, { id: number; thumb: string; frames: number }[]>>({})
  const [clipSegments, setClipSegments] = useState<Record<string, { start: number; end: number; autoPersonId: number; persons: { id: number; thumb: string }[] }[]>>({})
  const [detectingPersonsId, setDetectingPersonsId] = useState('')
  const [lightbox, setLightbox] = useState<{ clipId: string; index: number } | null>(null)
  type Rect = { x: number; y: number; w: number; h: number }
  const [manualEditor, setManualEditor] = useState<{ clipId: string; frame: string; regions: Rect[] } | null>(null)
  const [drawRect, setDrawRect] = useState<Rect | null>(null)
  const drawStart = useRef<{ x: number; y: number } | null>(null)
  const restoredPersonsRef = useRef<Set<string>>(new Set())
  const [focusPicker, setFocusPicker] = useState<{ clipId: string; segIdx: number; frame: string; cx: number; segments: SegList } | null>(null)
  const [videoDuration, setVideoDuration] = useState<number | null>(null)
  // Avatar Reel (guion + voz)
  const [reelTrigger, setReelTrigger] = useState('')
  const [reelAngle, setReelAngle] = useState('')
  const [reelSeconds, setReelSeconds] = useState(40)
  const [reelScript, setReelScript] = useState('')
  const [reelVoices, setReelVoices] = useState<string[]>([])
  const [reelVoiceId, setReelVoiceId] = useState('')
  const [reelAudio, setReelAudio] = useState('')
  const [reelTitle, setReelTitle] = useState('')
  const [reelDescription, setReelDescription] = useState('')
  const [reelSubs, setReelSubs] = useState(true)
  const [reelVideo, setReelVideo] = useState('')
  const [reelId, setReelId] = useState('')
  const [reels, setReels] = useState<import('./types').ReelItem[]>([])
  const [reelBusy, setReelBusy] = useState<'' | 'script' | 'voice' | 'compose' | 'broll' | 'upload' | 'thumb' | 'match' | 'seo'>('')
  const [reelMatchUrl, setReelMatchUrl] = useState('')
  const [reelSourceVideo, setReelSourceVideo] = useState('')
  const [reelChannelId, setReelChannelId] = useState<number | null>(null)
  const [reelPrivacy, setReelPrivacy] = useState('public')
  const [reelYoutubeUrl, setReelYoutubeUrl] = useState('')
  const [reelHook, setReelHook] = useState('')
  const [reelThumbPos, setReelThumbPos] = useState<'top' | 'center' | 'bottom'>('bottom')
  const [reelThumbImg, setReelThumbImg] = useState('')
  const [reelThumb, setReelThumb] = useState('')
  const [reelThumbV, setReelThumbV] = useState(0)
  const [reelVideoV, setReelVideoV] = useState(0)
  // Vídeos de macetas (WAN)
  const [plantName, setPlantName] = useState('')
  const [plantAspect, setPlantAspect] = useState<'9:16' | '16:9'>('9:16')
  const [plantProvider, setPlantProvider] = useState<'grok' | 'veo' | 'wan'>('grok')
  const [plantDuration, setPlantDuration] = useState(15)
  const [plantBatchText, setPlantBatchText] = useState('')
  const [plantChannelId, setPlantChannelId] = useState<number | null>(null)
  const [plantRowBusy, setPlantRowBusy] = useState('')
  const [plantMusicList, setPlantMusicList] = useState<{ name: string; label: string; path: string }[]>([])
  const [plantMusic, setPlantMusic] = useState('')  // '' = aleatoria
  const plantKind: 'plant' | 'egg' | 'butterfly' =
    activeSection === 'eggs' ? 'egg' : activeSection === 'butterflies' ? 'butterfly' : 'plant'
  const KIND_UI = {
    plant: { title: '🪴 Macetas — crecimiento en time-lapse', subject: 'Planta (fruta, flor, verdura…)',
      ph: 'Ej: limón, girasol, tomate, fresa…', batch: 'limón\ngirasol\ntomate\nfresa\nlavanda',
      list: 'Mis vídeos de macetas', empty: 'una planta', create: '🪴 Crear vídeo',
      d15: '15s · crecimiento', d30: '30s · mano + cosecha',
      desc: 'Vídeo satisfactorio de una planta creciendo de semilla a cosecha. Con 30s: la mano planta la semilla y al final recoge el fruto. Todo IA, sin copyright.' },
    egg: { title: '🥚 Huevos — animal gracioso eclosionando', subject: 'Animal (que salga del huevo)',
      ph: 'Ej: pollito, dinosaurio, dragón, pingüino…', batch: 'pollito\ndinosaurio\ndragón\npingüino\ntortuga',
      list: 'Mis vídeos de huevos', empty: 'un animal', create: '🥚 Crear vídeo',
      d15: '15s · eclosión', d30: '30s · eclosión + gracia',
      desc: 'Vídeo tierno y gracioso de un animal (pollito, dinosaurio, dragón…) saliendo de un huevo. Con 30s: el huevo se rompe y el animalito sale y hace algo gracioso. Todo IA, sin copyright.' },
    butterfly: { title: '🦋 Mariposas — metamorfosis en time-lapse', subject: 'Mariposa (tipo/color)',
      ph: 'Ej: monarca, azul morpho, colorida…', batch: 'monarca\nazul morpho\ncolorida\namarilla\nnaranja',
      list: 'Mis vídeos de mariposas', empty: 'una mariposa', create: '🦋 Crear vídeo',
      d15: '15s · metamorfosis', d30: '30s · crisálida + mariposa',
      desc: 'Metamorfosis satisfactoria: oruga → crisálida → mariposa que despliega sus alas. Con 30s: clip 1 oruga→crisálida, clip 2 emerge la mariposa. Todo IA, sin copyright.' },
  }[plantKind]
  const [plantIdeasList, setPlantIdeasList] = useState<{ name: string; note: string }[]>([])
  const [plants, setPlants] = useState<import('./types').PlantItem[]>([])
  const [plantBusy, setPlantBusy] = useState<'' | 'ideas' | 'create'>('')
  const [facecamEditor, setFacecamEditor] = useState<{ campaignId: number; frame: string; rect: Rect | null; zoom: number } | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [globalFocus, setGlobalFocus] = useState<'left' | 'center' | 'right' | 'follow' | 'facecam'>('center')
  // Presets de motion graphics que ofrece el worker de FX. Lista vacía = no hay
  // worker: se ocultan los selectores y todo va por el camino ASS de siempre.
  const [tagHandleDraft, setTagHandleDraft] = useState('')
  const [tagBusy, setTagBusy] = useState('')
  const [fxPresets, setFxPresets] = useState<string[]>([])
  const [globalFxPreset, setGlobalFxPreset] = useState<string>('none')
  const [clipTab, setClipTab] = useState<'create' | 'manage' | 'youtube'>(() => loadNav().clipTab || 'create')
  const [copiedUrl, setCopiedUrl] = useState('')

  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [activeCampaignId, setActiveCampaignId] = useState<number | null>(() => loadNav().campaignId ?? null)
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
    if (channel.id !== activeChannelId) {
      setActiveCampaignId(null)
      setClipCandidates([])
    }
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
      const data = await api.campaigns(channelId)
      setCampaigns(data)
      // Restaura los clips de la campana activa (p.ej. tras recargar la pestana).
      const open = activeCampaignId != null ? data.find((c) => c.id === activeCampaignId) : null
      if (open && open.transcriptPath) {
        setSelectedClipSource(open.transcriptPath)
        loadSavedClips(open.transcriptPath)
      }
    } catch (e) {
      handleApiError(e)
    }
  }

  const activeCampaign = useMemo(
    () => campaigns.find((c) => c.id === activeCampaignId) ?? null,
    [campaigns, activeCampaignId],
  )

  // Ruta del vídeo recién descargado, que download_video.py deja en el log como
  // "VIDEO_PATH: ...". Sirve para ofrecerlo desde aquí y no tener que volver al
  // sitio de origen a por él.
  const downloadedVideoPath = useMemo(() => {
    const match = /^VIDEO_PATH:\s*(.+)$/m.exec(selectedLog)
    return match ? match[1].trim() : ''
  }, [selectedLog])

  // El borrador del canal a etiquetar sigue a la campaña abierta; si no, al
  // cambiar de campaña se quedaría el valor de la anterior en el recuadro.
  useEffect(() => {
    setTagHandleDraft(activeCampaign?.tagHandle || '')
  }, [activeCampaign?.id, activeCampaign?.tagHandle])

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
      let ready = await api.campaign(campaign.id)

      // Si se paso un brief, extrae los requisitos y aplicalos.
      if (campBriefUrl.trim()) {
        setClipSourceStatus('Leyendo el brief y extrayendo requisitos con IA...')
        try {
          const { campaign: withRules } = await api.extractBrief(ready.id, { briefUrl: campBriefUrl.trim() })
          if (withRules.rules?.onScreenText) await api.applyCampaignRules(ready.id)
          ready = await api.campaign(ready.id)
        } catch (e) {
          handleApiError(e)
        }
      }

      setCampaigns((prev) => prev.map((c) => (c.id === ready.id ? ready : c)))
      setCampName(''); setCampSourceUrl(''); setCampCampaignUrl(''); setCampBriefUrl('')
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
    if (!campBriefUrl.trim()) { setError('Pega el link del brief (Google Docs o página web de la campaña).'); return }
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

  async function handleOpenFacecam(campaign: Campaign) {
    setError('')
    try {
      const { frame } = await api.campaignSceneFrame(campaign.id, 30)
      const fc = campaign.facecam || null
      setFacecamEditor({ campaignId: campaign.id, frame, rect: fc ? { x: fc.x, y: fc.y, w: fc.w, h: fc.h } : null, zoom: fc?.zoom ?? 1.4 })
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleSaveFacecam() {
    if (!facecamEditor || !facecamEditor.rect) { setFacecamEditor(null); return }
    const { campaignId, rect, zoom } = facecamEditor
    try {
      const { facecam } = await api.setCampaignFacecam(campaignId, { ...rect, zoom })
      setCampaigns((prev) => prev.map((c) => (c.id === campaignId ? { ...c, facecam } : c)))
    } catch (e) {
      handleApiError(e)
    }
    setFacecamEditor(null)
    drawStart.current = null
  }

  async function handleDeleteFacecam(campaign: Campaign) {
    try {
      await api.deleteCampaignFacecam(campaign.id)
      setCampaigns((prev) => prev.map((c) => (c.id === campaign.id ? { ...c, facecam: null } : c)))
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleSaveCreator(campaign: Campaign, creator: string) {
    try {
      const { campaign: updated } = await api.setCampaignCreator(campaign.id, creator)
      setCampaigns((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleUploadWatermark(campaign: Campaign, file: File) {
    setError('')
    try {
      const { watermarkPath } = await api.uploadCampaignWatermark(campaign.id, file)
      setCampaigns((prev) => prev.map((c) => (c.id === campaign.id ? { ...c, watermarkPath } : c)))
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleDeleteWatermark(campaign: Campaign) {
    setError('')
    try {
      await api.deleteCampaignWatermark(campaign.id)
      setCampaigns((prev) => prev.map((c) => (c.id === campaign.id ? { ...c, watermarkPath: '' } : c)))
    } catch (e) {
      handleApiError(e)
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

  // Desplaza hasta una tarjeta de clip y la resalta un momento (para retomar el
  // sitio tras submitear en el móvil).
  function goToClip(clipId: string) {
    const el = document.getElementById(`clip-${clipId}`)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.add('flash')
    window.setTimeout(() => el.classList.remove('flash'), 1600)
  }

  async function handleGenReelScript() {
    if (!reelTrigger.trim()) { setError('Escribe un disparador (tema, noticia, idea).'); return }
    setReelBusy('script'); setError('')
    try {
      const { script } = await api.reelScript({ trigger: reelTrigger, angle: reelAngle, seconds: reelSeconds })
      setReelScript(script); setReelAudio('')
    } catch (e) { handleApiError(e) } finally { setReelBusy('') }
  }

  async function handleGenReelVoice() {
    if (!reelScript.trim()) { setError('Primero genera o escribe el guion.'); return }
    if (!reelVoiceId) { setError('Elige una voz (arranca el TTS del Windows si la lista está vacía).'); return }
    setReelBusy('voice'); setError('')
    try {
      const { audio, reelId: id } = await api.reelVoice({ script: reelScript, voiceId: reelVoiceId, trigger: reelTrigger, reelId })
      setReelAudio(audio); setReelVideo(''); setReelId(id)
      api.reelsList().then((d) => setReels(d.reels)).catch(() => {})
    } catch (e) { handleApiError(e) } finally { setReelBusy('') }
  }

  async function handleComposeReel() {
    if (!reelAudio) { setError('Primero genera la voz.'); return }
    setReelBusy('compose'); setError('')
    try {
      const { video } = await api.reelCompose({ audio: reelAudio, title: reelTitle, subtitles: reelSubs, reelId })
      setReelVideo(video)
      api.reelsList().then((d) => setReels(d.reels)).catch(() => {})
    } catch (e) { handleApiError(e) } finally { setReelBusy('') }
  }

  async function handlePlantIdeas() {
    setPlantBusy('ideas'); setError('')
    try { const { ideas } = await api.plantIdeas(); setPlantIdeasList(ideas) }
    catch (e) { handleApiError(e) } finally { setPlantBusy('') }
  }

  async function handleBatchPlants() {
    const names = plantBatchText.split('\n').map((s) => s.trim()).filter(Boolean)
    if (names.length === 0) { setError('Pega al menos una planta (una por línea).'); return }
    const per = plantProvider === 'wan' ? 0 : plantProvider === 'veo' ? (plantDuration > 15 ? 5 : 2.5) : (plantDuration > 15 ? 3 : 1.2)
    const est = plantProvider === 'wan' ? 'GPU local (gratis, lento)' : `~$${(names.length * per).toFixed(1)} aprox.`
    if (!window.confirm(`Encolar ${names.length} vídeos con ${plantProvider}. Coste estimado: ${est}. ¿Seguir?`)) return
    setPlantBusy('create'); setError('')
    try {
      await api.plantBatch({ plants: names, aspect: plantAspect, provider: plantProvider, duration: plantDuration, music: plantMusic, kind: plantKind })
      setPlantBatchText('')
      const started = Date.now()
      const poll = async () => {
        let pending = true
        try {
          const { plants: list } = await api.plantsList(); setPlants(list)
          pending = list.some((p) => !p.video)
        } catch { /* reintenta */ }
        if (!pending || Date.now() - started > 8 * 60 * 60 * 1000) { setPlantBusy(''); return }
        window.setTimeout(poll, 20000)
      }
      window.setTimeout(poll, 20000)
    } catch (e) { handleApiError(e); setPlantBusy('') }
  }

  async function handleCreatePlant() {
    if (!plantName.trim()) { setError('Escribe una planta (o elige una idea).'); return }
    setPlantBusy('create'); setError('')
    try {
      const { plantId } = await api.plantCreate({ plant: plantName.trim(), aspect: plantAspect, provider: plantProvider, duration: plantDuration, music: plantMusic, kind: plantKind })
      api.plantsList().then((d) => setPlants(d.plants)).catch(() => {})
      const started = Date.now()
      const poll = async () => {
        try {
          const { plants: list } = await api.plantsList()
          setPlants(list)
          const me = list.find((p) => p.id === plantId)
          if (me?.video) { setPlantBusy(''); return }
        } catch { /* reintenta */ }
        if (Date.now() - started > 30 * 60 * 1000) { setPlantBusy(''); setError('El vídeo de maceta tarda; revisa el Historial (plant_video).'); return }
        window.setTimeout(poll, 8000)
      }
      window.setTimeout(poll, 8000)
    } catch (e) { handleApiError(e); setPlantBusy('') }
  }

  async function handlePlantSeo(p: import('./types').PlantItem) {
    setPlantRowBusy(p.id + ':seo'); setError('')
    try {
      await api.plantSeo(p.id, plantChannelId)
      const { plants: list } = await api.plantsList(); setPlants(list)
    } catch (e) { handleApiError(e) } finally { setPlantRowBusy('') }
  }

  async function handlePlantUpload(p: import('./types').PlantItem) {
    if (!plantChannelId) { setError('Elige un canal de YouTube.'); return }
    setPlantRowBusy(p.id + ':up'); setError('')
    try {
      await api.plantUpload(p.id, { channelId: plantChannelId })
      const started = Date.now()
      const poll = async () => {
        try {
          const { plants: list } = await api.plantsList(); setPlants(list)
          if (list.find((x) => x.id === p.id)?.youtubeUrl) { setPlantRowBusy(''); return }
        } catch { /* reintenta */ }
        if (Date.now() - started > 8 * 60 * 1000) { setPlantRowBusy(''); return }
        window.setTimeout(poll, 4000)
      }
      window.setTimeout(poll, 4000)
    } catch (e) { handleApiError(e); setPlantRowBusy('') }
  }

  async function handleDeletePlant(p: import('./types').PlantItem) {
    if (!window.confirm('¿Borrar este vídeo de maceta (imágenes y clips incluidos)?')) return
    try { await api.plantDelete(p.id); setPlants((prev) => prev.filter((x) => x.id !== p.id)) }
    catch (e) { handleApiError(e) }
  }

  async function handleRenderReel() {
    if (!reelId) return
    setReelBusy('compose'); setError('')
    const cur = reelId
    try {
      await api.reelRender(cur)  // job: re-monta con los fotogramas del partido
      const started = Date.now()
      const poll = async () => {
        try {
          const { reels: list } = await api.reelsList()
          setReels(list)
          const me = list.find((r) => r.id === cur)
          if (me?.video) { setReelVideo(me.video); setReelVideoV((v) => v + 1); setReelBusy(''); return }
        } catch { /* reintenta */ }
        if (Date.now() - started > 10 * 60 * 1000) { setReelBusy(''); setError('El montaje tarda; revisa el Historial (reel_match).'); return }
        window.setTimeout(poll, 5000)
      }
      window.setTimeout(poll, 5000)
    } catch (e) { handleApiError(e); setReelBusy('') }
  }

  async function handleGenBroll() {
    if (!reelId || !reelAudio) { setError('Primero genera la voz.'); return }
    setReelBusy('broll'); setError('')
    const currentId = reelId
    try {
      await api.reelBroll({ reelId: currentId, title: reelTitle, subtitles: reelSubs })  // encola el job
      const started = Date.now()
      const poll = async () => {
        try {
          const { reels: list } = await api.reelsList()
          setReels(list)
          const me = list.find((r) => r.id === currentId)
          if (me?.video) { setReelVideo(me.video); setReelBusy(''); return }
        } catch { /* reintenta */ }
        if (Date.now() - started > 10 * 60 * 1000) {
          setReelBusy(''); setError('El b-roll tarda más de lo normal; revisa el Historial (job reel_broll).'); return
        }
        window.setTimeout(poll, 5000)
      }
      window.setTimeout(poll, 5000)
    } catch (e) { handleApiError(e); setReelBusy('') }
  }

  async function handleMatchReel() {
    if (!reelMatchUrl.trim()) { setError('Pega el enlace de YouTube del resumen del partido.'); return }
    if (!reelVoiceId) { setError('Elige una voz para la narración (arranca el TTS del Windows si la lista está vacía).'); return }
    setReelBusy('match'); setError('')
    try {
      const { reelId: newId } = await api.reelMatch({ url: reelMatchUrl.trim(), voiceId: reelVoiceId, seconds: reelSeconds })
      setReelMatchUrl('')
      api.reelsList().then((d) => setReels(d.reels)).catch(() => {})
      const started = Date.now()
      const poll = async () => {
        try {
          const { reels: list } = await api.reelsList()
          setReels(list)
          const me = list.find((r) => r.id === newId)
          if (me?.video) { handleOpenReel(me); setReelBusy(''); return }
        } catch { /* reintenta */ }
        if (Date.now() - started > 15 * 60 * 1000) {
          setReelBusy(''); setError('El partido tarda más de lo normal; revisa el Historial (job reel_match).'); return
        }
        window.setTimeout(poll, 6000)
      }
      window.setTimeout(poll, 6000)
    } catch (e) { handleApiError(e); setReelBusy('') }
  }

  async function handleGenHook() {
    if (!reelId) return
    try { const { hook } = await api.reelHook(reelId); setReelHook(hook) } catch (e) { handleApiError(e) }
  }

  async function handleGenReelTitle() {
    if (!reelId) return
    setReelBusy('seo'); setError('')
    try { const { title } = await api.reelSeoTitle(reelId, reelChannelId); setReelTitle(title) }
    catch (e) { handleApiError(e) } finally { setReelBusy('') }
  }

  async function handleGenReelDesc() {
    if (!reelId) return
    setReelBusy('seo'); setError('')
    try { const { description } = await api.reelSeoDescription(reelId, reelChannelId); setReelDescription(description) }
    catch (e) { handleApiError(e) } finally { setReelBusy('') }
  }

  async function handleUploadThumbImg(file: File) {
    if (!reelId) return
    try { const { image } = await api.reelThumbnailImage(reelId, file); setReelThumbImg(image) } catch (e) { handleApiError(e) }
  }

  function pollJob(jobId: string, onDone: () => void, onFail?: () => void) {
    const started = Date.now()
    const tick = async () => {
      try {
        const j = await api.job(jobId)
        if (j.status === 'completed') { onDone(); return }
        if (j.status === 'failed') { setReelBusy(''); if (onFail) onFail(); else setError('El job falló; revisa el Historial.'); return }
      } catch { /* reintenta */ }
      if (Date.now() - started > 8 * 60 * 1000) { setReelBusy(''); return }
      window.setTimeout(tick, 4000)
    }
    window.setTimeout(tick, 3000)
  }

  // Previsualiza la miniatura (genera imagen nueva o reusa la actual re-quemando el texto).
  async function handlePreviewThumb(regenImage: boolean) {
    if (!reelId || !reelVideo) { setError('Primero compón el vídeo.'); return }
    if (!reelHook.trim()) { setError('Escribe un gancho para la miniatura.'); return }
    setReelBusy('thumb'); setError('')
    try {
      const { job, thumbPath } = await api.reelThumbPreview(reelId, { hook: reelHook, position: reelThumbPos, image: reelThumbImg, regenImage })
      pollJob(job.id, () => { setReelThumb(thumbPath); setReelThumbV((v) => v + 1); setReelBusy('') },
              () => setError('Falló la miniatura; revisa el Historial (reel_thumbnail).'))
    } catch (e) { handleApiError(e); setReelBusy('') }
  }

  async function handleApplyThumb() {
    if (!reelId || !reelThumb) { setError('Primero genera la miniatura.'); return }
    setReelBusy('thumb'); setError('')
    try {
      const { job } = await api.reelThumbApply(reelId)
      pollJob(job.id, () => { setReelVideoV((v) => v + 1); setReelBusy('') })
    } catch (e) { handleApiError(e); setReelBusy('') }
  }

  async function handleUploadReel() {
    if (!reelId || !reelVideo) { setError('Primero compón el vídeo.'); return }
    if (!reelChannelId) { setError('Elige un canal.'); return }
    setReelBusy('upload'); setError(''); setReelYoutubeUrl('')
    const cur = reelId
    try {
      await api.reelUpload(cur, { channelId: reelChannelId, privacy: reelPrivacy })
      const started = Date.now()
      const poll = async () => {
        try {
          const { reels: list } = await api.reelsList()
          setReels(list)
          const me = list.find((r) => r.id === cur)
          if (me?.youtubeUrl) { setReelYoutubeUrl(me.youtubeUrl); setReelBusy(''); return }
        } catch { /* reintenta */ }
        if (Date.now() - started > 8 * 60 * 1000) { setReelBusy(''); setError('La subida tarda; revisa el Historial (reel_upload).'); return }
        window.setTimeout(poll, 4000)
      }
      window.setTimeout(poll, 4000)
    } catch (e) { handleApiError(e); setReelBusy('') }
  }

  function handleOpenReel(r: import('./types').ReelItem) {
    setReelId(r.id); setReelTrigger(r.trigger); setReelScript(r.script)
    setReelVoiceId(r.voiceId || reelVoiceId); setReelTitle(r.title)
    setReelAudio(r.audio); setReelVideo(r.video); setReelYoutubeUrl(r.youtubeUrl || '')
    setReelHook(r.hook || ''); setReelThumbPos((r.thumbPosition as 'top' | 'center' | 'bottom') || 'bottom')
    setReelThumb(''); setReelThumbImg(''); setReelDescription(r.seoDescription || '')
    setReelSourceVideo(r.sourceVideo || '')
  }

  function handleNewReel() {
    setReelId(''); setReelTrigger(''); setReelAngle(''); setReelScript('')
    setReelTitle(''); setReelAudio(''); setReelVideo('')
    setReelHook(''); setReelThumb(''); setReelThumbImg(''); setReelThumbPos('bottom'); setReelDescription('')
    setReelSourceVideo('')
  }

  async function handleDeleteReel(r: import('./types').ReelItem) {
    if (!window.confirm('¿Borrar esta generación (audio y vídeo incluidos)?')) return
    try {
      await api.reelDelete(r.id)
      setReels((prev) => prev.filter((x) => x.id !== r.id))
      if (reelId === r.id) handleNewReel()
    } catch (e) { handleApiError(e) }
  }

  async function loadSavedClips(transcriptPath: string) {
    try {
      const data = await api.savedClips(transcriptPath)
      setClipCandidates(data.clips)
      restorePersonPanels(data.clips)
    } catch (e) {
      handleApiError(e)
    }
  }

  // Restaura el panel de blur/enfoque tras recargar: la detección está cacheada
  // en disco (pdisplay_*.json), así que se re-pide barato para los clips que la
  // tienen (hasPersons). SECUENCIAL (una a una) para no saturar el límite de
  // conexiones del navegador y bloquear un "Detectar" manual. La guarda evita
  // repetir clips ya restaurados (loadSavedClips puede llamarse varias veces).
  async function restorePersonPanels(clips: ClipCandidate[]) {
    for (const c of clips) {
      if (!c.hasPersons || restoredPersonsRef.current.has(c.id)) continue
      restoredPersonsRef.current.add(c.id)
      try {
        const { persons, segments } = await api.detectPersons(c.id)
        setClipPersons((prev) => ({ ...prev, [c.id]: persons }))
        setClipSegments((prev) => ({ ...prev, [c.id]: segments }))
      } catch {
        restoredPersonsRef.current.delete(c.id)  // reintentar la próxima vez
      }
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
      const data = await api.detectClips(transcriptPath, clipParts, clipsPerPart, clipTargetDur, activeChannelId)
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

  async function handleSaveTagHandle(campaign: Campaign) {
    const handle = tagHandleDraft.trim()
    if (handle === (campaign.tagHandle || '')) return
    try {
      const updated = await api.updateCampaign(campaign.id, { tagHandle: handle })
      setCampaigns((prev) => prev.map((c) => (c.id === campaign.id ? updated : c)))
      setTagHandleDraft(updated.tagHandle || '')
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleTagDescriptions(campaign: Campaign) {
    setTagBusy('tag')
    setError('')
    try {
      const r = await api.tagCampaignDescriptions(campaign.id)
      await loadSavedClips(campaign.transcriptPath)
      setError(`✅ ${r.handle}: añadido a ${r.updated} descripcion(es). `
        + `${r.alreadyTagged} ya lo tenían, ${r.withoutSeo} sin SEO todavía.`)
    } catch (e) {
      handleApiError(e)
    } finally {
      setTagBusy('')
    }
  }

  async function handleSyncYoutube(campaign: Campaign) {
    setTagBusy('sync')
    setError('')
    try {
      // Primero se simula: cambiar descripciones de vídeos publicados no se
      // deshace solo, así que se enseña la lista y se pide confirmación.
      const plan = await api.syncCampaignYoutube(campaign.id, true)
      if (!plan.updated) {
        setError(`No hay vídeos que actualizar (${plan.skipped} clips sin subir o sin descripción).`)
        return
      }
      const ok = window.confirm(
        `Se va a REEMPLAZAR la descripción en YouTube de ${plan.updated} vídeo(s) ya publicados.\n\n`
        + plan.clips.slice(0, 8).map((c) => `· ${c.firstLine || c.videoId}`).join('\n')
        + (plan.clips.length > 8 ? `\n· ...y ${plan.clips.length - 8} más` : '')
        + '\n\nEl título, los tags y la categoría no se tocan. ¿Continuar?')
      if (!ok) return
      const r = await api.syncCampaignYoutube(campaign.id, false)
      setError(`✅ Actualizados ${r.updated} vídeo(s) en YouTube.`
        + (r.errors.length ? ` ⚠️ ${r.errors.length} con error: ${r.errors[0].error}` : ''))
    } catch (e) {
      handleApiError(e)
    } finally {
      setTagBusy('')
    }
  }

  async function handleClipSettingChange(clip: ClipCandidate, patch: Partial<ClipCandidate>) {
    const merged = {
      focus: (patch.focus ?? clip.focus) as string,
      zoom: patch.zoom ?? clip.zoom,
      topRatio: patch.topRatio ?? clip.topRatio,
      subtitles: patch.subtitles ?? clip.subtitles,
      overlayText: patch.overlayText ?? clip.overlayText ?? '',
      endcardPercent: patch.endcardPercent ?? clip.endcardPercent ?? 0,
      fxPreset: patch.fxPreset ?? clip.fxPreset ?? 'none',
    }
    setClipCandidates((prev) => prev.map((c) => (c.id === clip.id ? { ...c, ...patch } : c)))
    try {
      await api.updateClipSettings(clip.id, merged)
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleAddManualClip() {
    const start = parseTimecode(manualStart)
    const end = parseTimecode(manualEnd)
    if (start === null || end === null) {
      setError('Pon inicio y fin como 2:17, 1:02:17 o en segundos.')
      return
    }
    if (end - start < 1) {
      setError('El fin tiene que ser posterior al inicio.')
      return
    }
    setIsAddingManual(true)
    setError('')
    try {
      const clip = await api.addManualClip({ transcriptPath: selectedClipSource, start, end, title: manualTitle, channelId: activeChannelId })
      setClipCandidates((prev) => [clip, ...prev])
      setManualStart('')
      setManualEnd('')
      setManualTitle('')
    } catch (e) {
      handleApiError(e)
    } finally {
      setIsAddingManual(false)
    }
  }

  async function handleCombineClips() {
    if (combineIds.length < 2) return
    setIsCombining(true)
    setError('')
    try {
      const clip = await api.combineClips(combineIds, combineTarget)
      setClipCandidates((prev) => [clip, ...prev])
      setCombineIds([])
      goToClip(clip.id)
    } catch (e) {
      handleApiError(e)
    } finally {
      setIsCombining(false)
    }
  }

  async function handleSaveSegments(clip: ClipCandidate) {
    const draft = segmentDrafts[clip.id]
    if (draft === undefined) return
    const segments: [number, number][] = []
    for (const part of draft.split(',').map((p) => p.trim()).filter(Boolean)) {
      const [a, b] = part.split(/\s*[-–]\s*/)
      const s = parseTimecode(a || ''), e = parseTimecode(b || '')
      if (s === null || e === null || e - s < 0.5) {
        setError(`Fragmento no válido: "${part}". Formato: 20:06-20:14, 50:00.5-50:10`)
        return
      }
      segments.push([s, e])
    }
    if (!segments.length) return
    setSavingSegmentsId(clip.id)
    setError('')
    try {
      const updated = await api.updateClipSegments(clip.id, segments)
      setClipCandidates((prev) => prev.map((c) => (c.id === clip.id ? updated : c)))
      setSegmentDrafts((prev) => { const next = { ...prev }; delete next[clip.id]; return next })
    } catch (e) {
      handleApiError(e)
    } finally {
      setSavingSegmentsId(null)
    }
  }

  async function handleTrimClip(clip: ClipCandidate, startDelta: number, endDelta: number) {
    const newStart = Math.max(0, clip.start + startDelta)
    const newEnd = clip.end + endDelta
    if (newEnd - newStart < 1) return
    setClipCandidates((prev) => prev.map((c) => (c.id === clip.id ? { ...c, start: newStart, end: newEnd, duration: Math.round((newEnd - newStart) * 100) / 100 } : c)))
    try {
      await api.trimClip(clip.id, newStart, newEnd)
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
      setRenderNonce((prev) => ({ ...prev, [clip.id]: Date.now() }))
    } catch (e) {
      handleApiError(e)
    } finally {
      setRenderingClipKey('')
    }
  }

  async function handleStopQueue() {
    setError('')
    try {
      await api.stopRenderAll()
      if (selectedClipSource) await loadSavedClips(selectedClipSource)
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleRenderAllClips() {
    // Encola el render en el BACKEND (un solo job). Corre en el servidor, así que
    // sobrevive a recargas de la página o cambios de pestaña del navegador.
    if (!selectedClipSource) return
    const pending = clipCandidates.filter((c) => !c.rendered)
    if (!pending.length) return
    setError('')
    try {
      const { job } = await api.renderAll(selectedClipSource, globalFocus, globalFxPreset)
      insertOrUpdateJob(job)
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleDetectPersons(clip: ClipCandidate, force = false) {
    setDetectingPersonsId(clip.id)
    setError('')
    try {
      const { persons, segments } = await api.detectPersons(clip.id, force)
      setClipPersons((prev) => ({ ...prev, [clip.id]: persons }))
      setClipSegments((prev) => ({ ...prev, [clip.id]: segments }))
    } catch (e) {
      handleApiError(e)
    } finally {
      setDetectingPersonsId('')
    }
  }

  type SegList = { start: number; end: number; autoPersonId: number; persons: { id: number; thumb: string }[] }[]
  type FocusPlanItem = { start: number; end: number; personId: number; cx?: number | null }

  // Construye el plan completo aplicando un override en el tramo idx y preservando
  // el resto (persona o punto manual cx) de lo que ya había guardado.
  async function saveFocusPlan(clip: ClipCandidate, segments: SegList, idx: number, override: Partial<FocusPlanItem>) {
    let existing: FocusPlanItem[] = []
    try { existing = JSON.parse(clip.focusSegments || '[]') } catch { existing = [] }
    const plan: FocusPlanItem[] = segments.map((seg, i) => {
      if (i === idx) {
        return { start: seg.start, end: seg.end, personId: seg.autoPersonId, ...override }
      }
      const e = existing[i]
      return { start: seg.start, end: seg.end, personId: e?.personId ?? seg.autoPersonId, ...(e?.cx != null ? { cx: e.cx } : {}) }
    })
    setClipCandidates((prev) => prev.map((c) => (c.id === clip.id ? { ...c, focusSegments: JSON.stringify(plan) } : c)))
    try {
      await api.setFocusPlan(clip.id, plan)
    } catch (e) {
      handleApiError(e)
    }
  }

  // Elegir persona (o centro): fija personId y BORRA el punto manual de ese tramo.
  function handleSetSegmentFocus(clip: ClipCandidate, segments: SegList, idx: number, personId: number) {
    return saveFocusPlan(clip, segments, idx, { personId, cx: null })
  }

  // Elegir punto manual en el frame: fija cx (personId pasa a -1/centro como base).
  function handleSetSegmentFocusPoint(clip: ClipCandidate, segments: SegList, idx: number, cx: number) {
    return saveFocusPlan(clip, segments, idx, { personId: -1, cx })
  }

  // Abre el selector de punto de enfoque: extrae un frame en la mitad del tramo.
  async function handleOpenFocusPoint(clip: ClipCandidate, segments: SegList, idx: number) {
    setError('')
    const seg = segments[idx]
    let existing: FocusPlanItem[] = []
    try { existing = JSON.parse(clip.focusSegments || '[]') } catch { existing = [] }
    const curCx = existing[idx]?.cx ?? 0.5
    try {
      const { frame } = await api.sceneFrame(clip.id, (seg.start + seg.end) / 2)
      setFocusPicker({ clipId: clip.id, segIdx: idx, frame, cx: curCx, segments })
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleSaveFocusPoint() {
    if (!focusPicker) return
    const clip = clipCandidates.find((c) => c.id === focusPicker.clipId)
    if (clip) await handleSetSegmentFocusPoint(clip, focusPicker.segments, focusPicker.segIdx, focusPicker.cx)
    setFocusPicker(null)
  }

  async function handleSetFocusPerson(clip: ClipCandidate, personId: number) {
    const next = clip.focusPerson === personId ? -1 : personId  // toggle
    setClipCandidates((prev) => prev.map((c) => (c.id === clip.id ? { ...c, focusPerson: next } : c)))
    try {
      await api.setFocusPerson(clip.id, next)
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleToggleBlurPerson(clip: ClipCandidate, personId: number) {
    let ids: number[] = []
    try { ids = JSON.parse(clip.blurPersons || '[]') } catch { ids = [] }
    const next = ids.includes(personId) ? ids.filter((i) => i !== personId) : [...ids, personId]
    const nextStr = JSON.stringify(next)
    setClipCandidates((prev) => prev.map((c) => (c.id === clip.id ? { ...c, blurPersons: nextStr } : c)))
    try {
      await api.setBlurPersons(clip.id, next)
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleOpenManualBlur(clip: ClipCandidate) {
    setError('')
    let regions: Rect[] = []
    try {
      const raw = JSON.parse(clip.manualBlur || '[]')
      regions = Array.isArray(raw) ? raw.filter((r) => r && typeof r.x === 'number') : []
    } catch { regions = [] }
    try {
      const { frame } = await api.sceneFrame(clip.id)
      setManualEditor({ clipId: clip.id, frame, regions })
    } catch (e) {
      handleApiError(e)
    }
  }

  // Punto normalizado [0,1] dentro del stage a partir de un evento de puntero.
  function normPoint(e: React.PointerEvent, el: HTMLElement) {
    const r = el.getBoundingClientRect()
    return {
      x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
      y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)),
    }
  }

  async function handleSaveManualBlur() {
    if (!manualEditor) return
    const regions = manualEditor.regions
    // Optimista en el estado del clip para que Regenerar ya lo use.
    setClipCandidates((prev) => prev.map((c) => (c.id === manualEditor.clipId ? { ...c, manualBlur: JSON.stringify(regions) } : c)))
    try {
      await api.setManualBlur(manualEditor.clipId, regions)
    } catch (e) {
      handleApiError(e)
    }
    setManualEditor(null)
    setDrawRect(null)
    drawStart.current = null
  }

  async function handleExtractFrames(clip: ClipCandidate) {
    setExtractingFramesId(clip.id)
    setError('')
    try {
      const { frames } = await api.extractFrames(clip.id)
      setClipFrames((prev) => ({ ...prev, [clip.id]: frames }))
    } catch (e) {
      handleApiError(e)
    } finally {
      setExtractingFramesId('')
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

  async function handleReuploadClip(clip: ClipCandidate) {
    // YouTube NO reemplaza el fichero de un vídeo ya publicado: esto sube uno
    // nuevo y el anterior se queda donde está. Por eso se avisa con su enlace
    // delante, que es lo que hace falta para ir a ocultarlo.
    const lines = [
      'YouTube no puede sustituir el vídeo de una publicación.',
      '',
      'Se subirá un vídeo NUEVO y el anterior SEGUIRÁ PUBLICADO:',
      clip.youtubeUrl || '(sin enlace)',
      '',
    ]
    if (clip.submitted) {
      lines.push('⚠️ Este clip ya está marcado como ENVIADO a la campaña.')
      lines.push('Si enviaste ese enlace, al ocultarlo puedes perder el pago.')
      lines.push('')
    }
    lines.push('Después tendrás los dos enlaces para decidir qué hacer con el viejo.')
    lines.push('')
    lines.push('¿Subir de nuevo?')
    if (!window.confirm(lines.join('\n'))) return
    await handleUploadClip(clip)
  }

  async function handleUploadClip(clip: ClipCandidate) {
    setUploadingClipId(clip.id)
    setError('')
    try {
      const job = await api.uploadClip(clip.id, uploadPrivacy)
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

  async function handleSetVisibility(clip: ClipCandidate, privacy: string) {
    setClipCandidates((prev) => prev.map((c) => (c.id === clip.id ? { ...c, youtubePrivacy: privacy } : c)))
    try {
      await api.setClipVisibility(clip.id, privacy)
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleToggleSubmitted(clip: ClipCandidate) {
    const next = !clip.submitted
    setClipCandidates((prev) => prev.map((c) => (c.id === clip.id ? { ...c, submitted: next } : c)))
    try {
      await api.setClipSubmitted(clip.id, next)
    } catch (e) {
      setClipCandidates((prev) => prev.map((c) => (c.id === clip.id ? { ...c, submitted: !next } : c)))
      handleApiError(e)
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
  // Reloj para la cuenta atrás de la ventana de submit (30 min tras subir).
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 20000)
    return () => window.clearInterval(t)
  }, [])

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

  // Render en cola del backend: se deriva de la lista de jobs, así se detecta
  // aunque recargues la página (el job sigue vivo en el servidor).
  const runningBatchJob = useMemo(
    () => jobs.find((j) => j.script === 'render_all.py' && (j.status === 'running' || j.status === 'queued')),
    [jobs],
  )

  // Mientras hay render en cola, refresca los clips para ver el progreso; al
  // terminar, un refresco final.
  const wasBatchRunning = useRef(false)
  useEffect(() => {
    if (runningBatchJob && selectedClipSource) {
      wasBatchRunning.current = true
      const t = setInterval(() => loadSavedClips(selectedClipSource), 4000)
      return () => clearInterval(t)
    }
    if (wasBatchRunning.current && selectedClipSource) {
      wasBatchRunning.current = false
      loadSavedClips(selectedClipSource)
    }
  }, [runningBatchJob?.id, selectedClipSource])

  useEffect(() => {
    if (activeChannel) {
      setChannelDraft({ name: activeChannel.name, language: activeChannel.language, seoRules: activeChannel.seoRules })
      setYtStatus(null)
      refreshYoutubeStatus(activeChannel.id)
      refreshClipSources(activeChannel.id)
      refreshCampaigns(activeChannel.id)
    }
  }, [activeChannel?.id])

  // Presets de motion graphics. Si el worker no está, la lista llega vacía y los
  // selectores de efectos no se pintan.
  useEffect(() => {
    if (authState !== 'authed') return
    api.fxPresets()
      .then((d) => setFxPresets(d.available ? d.presets : []))
      .catch(() => setFxPresets([]))
  }, [authState])

  // Carga voces + generaciones guardadas al abrir Avatar Reel.
  useEffect(() => {
    if (activeSection !== 'reels' || authState !== 'authed') return
    api.reelVoices().then((d) => {
      setReelVoices(d.voices)
      setReelVoiceId((cur) => cur || d.voices[0] || '')
    }).catch(() => {})
    api.reelsList().then((d) => setReels(d.reels)).catch(() => {})
    setReelChannelId((cur) => cur ?? (channels[0]?.id ?? null))
  }, [activeSection, authState, channels])

  // Carga los vídeos de macetas al abrir la sección.
  useEffect(() => {
    if (!['plants', 'eggs', 'butterflies'].includes(activeSection) || authState !== 'authed') return
    api.plantsList().then((d) => setPlants(d.plants)).catch(() => {})
    api.plantMusic().then((d) => setPlantMusicList(d.tracks)).catch(() => {})
    setPlantChannelId((cur) => cur ?? (channels[0]?.id ?? null))
    // Música por defecto por pestaña: Huevos → "crecepollito"; Mariposas → "maripositacrece".
    const DEFAULT_MUSIC: Record<string, string> = { eggs: 'crecepollito.mp3', butterflies: 'maripositacrece.mp3' }
    const def = DEFAULT_MUSIC[activeSection] || ''
    setPlantMusic((cur) => def || (Object.values(DEFAULT_MUSIC).includes(cur) ? '' : cur))
  }, [activeSection, authState, channels])

  // Duración del vídeo de la campaña activa (para el mapa de cobertura).
  useEffect(() => {
    if (activeCampaignId == null) { setVideoDuration(null); return }
    let cancelled = false
    api.campaignCoverage(activeCampaignId)
      .then((d) => { if (!cancelled) setVideoDuration(d.duration || 0) })
      .catch(() => { if (!cancelled) setVideoDuration(null) })
    return () => { cancelled = true }
  }, [activeCampaignId])

  // Lightbox de personas: navegar con flechas y cerrar con Esc.
  useEffect(() => {
    if (!lightbox) return
    const onKey = (e: KeyboardEvent) => {
      const n = clipPersons[lightbox.clipId]?.length || 0
      if (e.key === 'Escape') setLightbox(null)
      else if (n && e.key === 'ArrowLeft') setLightbox((lb) => (lb ? { ...lb, index: (lb.index - 1 + n) % n } : lb))
      else if (n && e.key === 'ArrowRight') setLightbox((lb) => (lb ? { ...lb, index: (lb.index + 1) % n } : lb))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [lightbox, clipPersons])

  // Persiste la navegacion para no perder el sitio al recargar la pestana.
  useEffect(() => {
    localStorage.setItem('mediaops_nav', JSON.stringify({
      section: activeSection, channelId: activeChannelId, clipTab, campaignId: activeCampaignId,
    }))
  }, [activeSection, activeChannelId, clipTab, activeCampaignId])

  // Guarda la posicion de scroll (throttle con rAF) y, sobre todo, al ocultar
  // la pestana (el movil dispara pagehide/visibilitychange al cambiar de app).
  useEffect(() => {
    let ticking = false
    const onScroll = () => {
      if (ticking) return
      ticking = true
      requestAnimationFrame(() => {
        saveScroll()
        ticking = false
      })
    }
    const onHide = () => saveScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('pagehide', onHide)
    document.addEventListener('visibilitychange', onHide)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('pagehide', onHide)
      document.removeEventListener('visibilitychange', onHide)
    }
  }, [])

  // Restaura el scroll una sola vez, cuando ya se han pintado los clips de la
  // campana restaurada (la pagina ya tiene altura). Asi el movil vuelve al
  // clip exacto donde estabas, no al principio.
  const pendingScrollRef = useRef<number>(loadScroll())
  useEffect(() => {
    if (pendingScrollRef.current <= 0) return
    if (activeSection !== 'clipping' || !activeCampaignId || clipCandidates.length === 0) return
    const target = pendingScrollRef.current
    pendingScrollRef.current = 0
    requestAnimationFrame(() => window.scrollTo(0, target))
  }, [activeSection, activeCampaignId, clipCandidates.length])

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
                <p className="help">
                  ▶ Los shorts de este canal se subirán a YouTube: <strong>{ytStatus?.linked ? ytStatus.channelName : 'sin vincular — ve a YouTube ⚙'}</strong>
                </p>

                <div className="form-grid">
                  <label className="field span-2">
                    <span>Nombre de la campaña (opcional)</span>
                    <input value={campName} onChange={(e) => setCampName(e.target.value)} placeholder="Ej: Trailblazers Kate McAndrew" />
                  </label>
                  <label className="field span-2">
                    <span>Link del vídeo a clipear (YouTube, Twitch VOD, Google Drive o WeTransfer)</span>
                    <input type="url" value={campSourceUrl} onChange={(e) => setCampSourceUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=...  ·  twitch.tv/videos/...  ·  drive.google.com/..." />
                  </label>
                  <label className="field span-2">
                    <span>Link de la campaña Whop <em style={{ color: 'var(--ink-soft)', fontStyle: 'normal' }}>(opcional — déjalo vacío si es un short sin campaña)</em></span>
                    <input type="url" value={campCampaignUrl} onChange={(e) => setCampCampaignUrl(e.target.value)} placeholder="https://whop.com/...  (opcional)" />
                  </label>
                  <label className="field span-2">
                    <span>Link del brief <em style={{ color: 'var(--ink-soft)', fontStyle: 'normal' }}>(opcional</em> — Google Docs o web: Reach, ClipFarm…; la IA extrae los requisitos)</span>
                    <input type="url" value={campBriefUrl} onChange={(e) => setCampBriefUrl(e.target.value)} placeholder="(opcional) https://docs.google.com/...  o  https://reachclipping.com/..." />
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
                {!activeCampaign && activeCampaignId != null && campaigns.length === 0 ? (
                  <p className="help">⏳ Restaurando campaña…</p>
                ) : !activeCampaign ? (
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
                              {camp.clipStats && camp.clipStats.total > 0 && (() => {
                                const s = camp.clipStats!
                                const hasWhop = !!camp.campaignUrl?.trim()
                                const completa = hasWhop ? (s.uploaded === s.total && s.submitted === s.total) : (s.uploaded === s.total)
                                return (
                                  <p className={completa ? 'campaign-status complete' : 'campaign-status'} style={{ margin: '6px 0 0', display: 'inline-block' }}>
                                    {completa
                                      ? (hasWhop ? '✅ Completada — todo subido y submiteado' : '✅ Completada — todo subido a YouTube')
                                      : `${s.rendered}/${s.total} renderizados · ${s.uploaded}/${s.total} subidos${hasWhop ? ` · ${s.submitted}/${s.total} submiteados` : ''}`}
                                  </p>
                                )
                              })()}
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

                    {clipCandidates.length > 0 && (() => {
                      const hasWhop = !!activeCampaign.campaignUrl?.trim()
                      const total = clipCandidates.length
                      const subidos = clipCandidates.filter((c) => c.uploaded).length
                      const submiteados = clipCandidates.filter((c) => c.submitted).length
                      const completa = hasWhop ? (subidos === total && submiteados === total) : (subidos === total)
                      const lastSubmitted = hasWhop ? [...clipCandidates].reverse().find((c) => c.submitted) : undefined
                      const lastUploaded = [...clipCandidates].reverse().find((c) => c.uploaded)
                      return (
                        <div className={completa ? 'campaign-status complete' : 'campaign-status'} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                          <span>
                            {completa
                              ? (hasWhop ? '✅ Campaña totalmente subida y submiteada' : '✅ Todos los shorts subidos a YouTube')
                              : (hasWhop
                                  ? `Progreso — ${subidos}/${total} subidos · ${submiteados}/${total} submiteados a Whop`
                                  : `Progreso — ${subidos}/${total} subidos a YouTube`)}
                          </span>
                          <span style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                            {lastUploaded && (
                              <button className="goto-submitted" onClick={() => goToClip(lastUploaded.id)}>
                                ↓ Último subido a YouTube
                              </button>
                            )}
                            {lastSubmitted && (
                              <button className="goto-submitted" onClick={() => goToClip(lastSubmitted.id)}>
                                ↓ Último submiteado
                              </button>
                            )}
                          </span>
                        </div>
                      )
                    })()}

                    {videoDuration != null && videoDuration > 0 && clipCandidates.length > 0 && (() => {
                      const dur = videoDuration
                      const CELLS = Math.min(240, Math.max(60, Math.round(dur / 30)))
                      const cellSec = dur / CELLS
                      // Unión de rangos clipeados (sin contar solapes) para % y minutos restantes.
                      const sorted = clipCandidates.flatMap(sourceRanges).sort((a, b) => a[0] - b[0])
                      let union = 0, curS = -1, curE = -1
                      for (const [s, e] of sorted) {
                        if (s > curE) { union += Math.max(0, curE - curS); curS = s; curE = e }
                        else { curE = Math.max(curE, e) }
                      }
                      union += Math.max(0, curE - curS)
                      const pct = Math.min(100, Math.round((union / dur) * 100))
                      const remainMin = Math.max(0, Math.round((dur - union) / 60))
                      const cells = Array.from({ length: CELLS }, (_, i) => {
                        const t0 = i * cellSec, t1 = (i + 1) * cellSec
                        let cov = 0, count = 0
                        for (const c of clipCandidates) {
                          const ov = sourceRanges(c).reduce((acc, [s, e]) => acc + Math.max(0, Math.min(t1, e) - Math.max(t0, s)), 0)
                          if (ov > 0) { cov += ov; count++ }
                        }
                        const level = cov / cellSec < 0.05 ? 0 : Math.min(4, count)
                        return { i, t0, t1, level, count }
                      })
                      return (
                        <div className="coverage">
                          <div className="seo-head">
                            <span>🗺️ Cobertura del vídeo ({formatSeconds(dur)}) — <strong>{pct}%</strong> clipeado · quedan ~{remainMin} min sin clipear</span>
                          </div>
                          <div className="cov-grid">
                            {cells.map((c) => (
                              <span
                                key={c.i}
                                className={`cov-cell l${c.level}`}
                                title={`${formatSeconds(c.t0)}–${formatSeconds(c.t1)} · ${c.count} clip${c.count !== 1 ? 's' : ''}`}
                                onClick={() => { const cl = clipCandidates.find((x) => sourceRanges(x).some(([s, e]) => Math.min(c.t1, e) > Math.max(c.t0, s))); if (cl) goToClip(cl.id) }}
                              />
                            ))}
                          </div>
                          <div className="cov-legend">
                            <span>Menos</span>
                            <span className="cov-cell l0" /><span className="cov-cell l1" /><span className="cov-cell l2" /><span className="cov-cell l3" /><span className="cov-cell l4" />
                            <span>Más · clic en una celda salta a su clip</span>
                          </div>
                        </div>
                      )
                    })()}

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
                        <span>Link del brief (Google Docs o web: Reach, ClipFarm…) — la IA extrae los requisitos</span>
                        <input type="url" value={campBriefUrl} onChange={(e) => setCampBriefUrl(e.target.value)} placeholder="https://docs.google.com/document/d/..." />
                      </label>
                      <div className="field" style={{ justifyContent: 'flex-end' }}>
                        <button className="primary" disabled={isExtractingBrief} onClick={() => handleExtractBrief(activeCampaign)}>
                          {isExtractingBrief ? 'Extrayendo...' : 'Extraer requisitos con IA'}
                        </button>
                      </div>
                    </div>

                    <div className="seo-box">
                      <div className="seo-head"><span>🎙️ Invitado/creador a nombrar en el título (si la campaña lo exige)</span></div>
                      <input
                        placeholder="Ej: Kate McAndrew — el título dejará claro que es una entrevista con esta persona"
                        value={activeCampaign.rules?.creator || ''}
                        onChange={(e) => setCampaigns((prev) => prev.map((c) => (c.id === activeCampaign.id ? { ...c, rules: { ...(c.rules || {}), creator: e.target.value } } : c)))}
                        onBlur={(e) => handleSaveCreator(activeCampaign, e.target.value)}
                      />
                      <p className="help">Al generar el SEO, el título incluirá este nombre y lo enmarcará como entrevista. Regenera los textos SEO de los clips ya hechos para aplicarlo.</p>
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

                    <div className="seo-box">
                      <div className="seo-head">
                        <span>Canal a etiquetar en la descripción</span>
                      </div>
                      <div className="seo-field">
                        <input
                          value={tagHandleDraft}
                          placeholder={activeCampaign.rules?.handles?.youtube || '@elcanal'}
                          onChange={(e) => setTagHandleDraft(e.target.value)}
                          onBlur={() => handleSaveTagHandle(activeCampaign)}
                        />
                      </div>
                      <p className="help">
                        Va como primera línea de la descripción SEO, en su propia línea, para
                        poder convertirlo en chip enlazado desde Studio. Si lo dejas vacío se usa
                        el del brief ({activeCampaign.rules?.handles?.youtube || 'ninguno'}).
                      </p>
                      <div className="batch-render-bar">
                        <button
                          className="link-btn"
                          disabled={tagBusy !== ''}
                          onClick={() => handleTagDescriptions(activeCampaign)}
                        >
                          {tagBusy === 'tag' ? 'Añadiendo...' : 'Añadir a las descripciones ya hechas'}
                        </button>
                        <button
                          className="link-btn"
                          disabled={tagBusy !== ''}
                          onClick={() => handleSyncYoutube(activeCampaign)}
                        >
                          {tagBusy === 'sync' ? 'Actualizando...' : 'Actualizar descripciones en YouTube'}
                        </button>
                      </div>
                      <p className="help">
                        El primero solo toca lo guardado aquí; el segundo reemplaza la descripción
                        en los vídeos ya publicados (enseña antes la lista y pide confirmación).
                        Ni uno ni otro cambian el título ni los tags.
                      </p>
                    </div>

                    <div className="seo-box" style={{ marginTop: 4 }}>
                      <div className="seo-head"><span>💧 Watermark de la campaña (se superpone arriba centrado en todos los clips)</span></div>
                      {activeCampaign.watermarkPath ? (
                        <div className="actions-row" style={{ alignItems: 'center', gap: 12 }}>
                          <img src={api.fileUrl(activeCampaign.watermarkPath)} alt="watermark" style={{ maxHeight: 54, maxWidth: 180, background: '#0b1120', borderRadius: 6, padding: 4 }} />
                          <span className="help" style={{ color: 'var(--ok)' }}>✅ Se aplicará al renderizar.</span>
                          <label className="link-btn" style={{ cursor: 'pointer' }}>
                            Cambiar
                            <input type="file" accept="image/*" style={{ display: 'none' }} onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUploadWatermark(activeCampaign, f); e.currentTarget.value = '' }} />
                          </label>
                          <button className="link-btn" onClick={() => handleDeleteWatermark(activeCampaign)}>Quitar</button>
                        </div>
                      ) : (
                        <div className="actions-row" style={{ alignItems: 'center', gap: 12 }}>
                          <label className="primary" style={{ cursor: 'pointer', padding: '10px 14px', borderRadius: 10 }}>
                            Subir PNG del watermark
                            <input type="file" accept="image/*" style={{ display: 'none' }} onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUploadWatermark(activeCampaign, f); e.currentTarget.value = '' }} />
                          </label>
                          <span className="help">Descarga el PNG del brief (recurso "Watermark") y súbelo aquí. Ideal PNG con transparencia.</span>
                        </div>
                      )}
                    </div>

                    <div className="seo-box" style={{ marginTop: 4 }}>
                      <div className="seo-head"><span>🎥 Facecam + pantalla (tutoriales: cara arriba, pantalla abajo)</span></div>
                      {activeCampaign.facecam ? (
                        <div className="actions-row" style={{ alignItems: 'center', gap: 12 }}>
                          <span className="help" style={{ color: 'var(--ok)' }}>✅ Recuadro marcado (zoom pantalla {activeCampaign.facecam.zoom}×). Elige el encuadre “🎥 Facecam + pantalla” en los clips.</span>
                          <button className="link-btn" onClick={() => handleOpenFacecam(activeCampaign)}>Cambiar</button>
                          <button className="link-btn" onClick={() => handleDeleteFacecam(activeCampaign)}>Quitar</button>
                        </div>
                      ) : (
                        <div className="actions-row" style={{ alignItems: 'center', gap: 12 }}>
                          <button className="primary" style={{ padding: '10px 14px', borderRadius: 10 }} onClick={() => handleOpenFacecam(activeCampaign)}>
                            Marcar recuadro de la cámara
                          </button>
                          <span className="help">Dibuja el recuadro de tu webcam sobre un frame del vídeo. Es fijo para todo el vídeo. Requiere el vídeo ya descargado.</span>
                        </div>
                      )}
                    </div>

                    <hr style={{ width: '100%', border: 0, borderTop: '1px solid #1f2937' }} />

                    <div className="actions-row" style={{ alignItems: 'flex-end', flexWrap: 'wrap' }}>
                      <label className="field" style={{ maxWidth: 150 }}>
                        <span>Partes (0 = auto)</span>
                        <input type="number" min={0} max={20} value={clipParts} onChange={(e) => setClipParts(Number(e.target.value))} />
                      </label>
                      <label className="field" style={{ maxWidth: 150 }}>
                        <span>Clips por parte</span>
                        <input type="number" min={1} max={10} value={clipsPerPart} onChange={(e) => setClipsPerPart(Number(e.target.value) || 5)} />
                      </label>
                      <label className="field" style={{ maxWidth: 150 }}>
                        <span>Duración (s)</span>
                        <input type="number" min={10} max={90} value={clipTargetDur} onChange={(e) => setClipTargetDur(Number(e.target.value) || 40)} />
                      </label>
                      <button className="primary" disabled={isDetectingClips || !selectedClipSource} onClick={() => runDetect(selectedClipSource)}>
                        {isDetectingClips ? 'Analizando...' : clipCandidates.length ? 'Re-detectar clips' : 'Detectar clips'}
                      </button>
                    </div>
                    <p className="help">
                      Divide la transcripción en partes y saca varios clips de cada una (más cobertura, peticiones más pequeñas). Auto ≈ 1 parte por cada 15 min.
                    </p>

                    <div className="actions-row" style={{ alignItems: 'flex-end', flexWrap: 'wrap' }}>
                      <label className="field" style={{ maxWidth: 110 }}>
                        <span>Inicio</span>
                        <input placeholder="2:17" value={manualStart} onChange={(e) => setManualStart(e.target.value)} />
                      </label>
                      <label className="field" style={{ maxWidth: 110 }}>
                        <span>Fin</span>
                        <input placeholder="4:03" value={manualEnd} onChange={(e) => setManualEnd(e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter') handleAddManualClip() }} />
                      </label>
                      <label className="field" style={{ maxWidth: 320 }}>
                        <span>Título (opcional)</span>
                        <input placeholder="Clip manual 2:17 – 4:03" value={manualTitle} onChange={(e) => setManualTitle(e.target.value)} />
                      </label>
                      <button disabled={isAddingManual || !selectedClipSource || !manualStart.trim() || !manualEnd.trim()} onClick={handleAddManualClip}>
                        {isAddingManual ? 'Añadiendo...' : '➕ Añadir clip'}
                      </button>
                    </div>
                    <p className="help">
                      Añade un clip a mano con su inicio y fin (2:17, 1:02:17 o segundos). Re-detectar no lo borra.
                    </p>

                    {clipCandidates.length === 0 && (
                      <p className="description">Aún no hay clips. Pulsa “Detectar clips”.</p>
                    )}

                    {clipCandidates.length > 0 && (() => {
                      const pendientes = clipCandidates.filter((c) => !c.rendered).length
                      const renderizados = clipCandidates.filter((c) => c.rendered).length
                      const enCola = !!runningBatchJob
                      return (
                        <div className="batch-render-bar">
                          <label className="batch-focus">
                            <span>Encuadre (todos)</span>
                            <select
                              value={globalFocus}
                              disabled={enCola}
                              onChange={(e) => {
                                const f = e.target.value as 'left' | 'center' | 'right' | 'follow' | 'facecam'
                                setGlobalFocus(f)
                                if (f === 'facecam' && activeCampaign && !activeCampaign.facecam) handleOpenFacecam(activeCampaign)
                              }}
                            >
                              <option value="left">Izquierda</option>
                              <option value="center">Centro</option>
                              <option value="right">Derecha</option>
                              <option value="follow">🎙 Seguir al hablante</option>
                              <option value="facecam">🎥 Facecam + pantalla</option>
                            </select>
                          </label>
                          {fxPresets.length > 0 && (
                            <label className="batch-focus">
                              <span>Efectos (todos)</span>
                              <select
                                value={globalFxPreset}
                                disabled={enCola}
                                onChange={(e) => setGlobalFxPreset(e.target.value)}
                              >
                                <option value="none">Sin efectos</option>
                                {fxPresets.map((name) => (
                                  <option key={name} value={name}>{`✨ ${name}`}</option>
                                ))}
                              </select>
                            </label>
                          )}
                          <button
                            className="primary"
                            disabled={enCola || pendientes === 0}
                            onClick={handleRenderAllClips}
                          >
                            {enCola
                              ? `Renderizando en cola... (${renderizados}/${clipCandidates.length})`
                              : pendientes === 0
                                ? 'Todos los verticales renderizados ✓'
                                : `Generar todos los verticales (${pendientes})`}
                          </button>
                          {enCola && (
                            <button className="stop-queue" onClick={handleStopQueue} title="Matar la cola de render en marcha">
                              ⏹ Parar cola
                            </button>
                          )}
                          <span className="help" style={{ margin: 0 }}>
                            {enCola
                              ? '⚙ Corre en el servidor: puedes cerrar la pestaña o cambiar de sección; sigue renderizando.'
                              : `Aplica el encuadre "${globalFocus === 'left' ? 'Izquierda' : globalFocus === 'right' ? 'Derecha' : globalFocus === 'follow' ? '🎙 Seguir al hablante' : 'Centro'}" a todos y los renderiza en cola en el servidor; luego solo queda subir a YT.`}
                          </span>
                        </div>
                      )
                    })()}

                    {combineIds.length > 0 && (
                      <div className="campaign-status" style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                        <span>🔗 {combineIds.length} clip{combineIds.length !== 1 ? 's' : ''} para combinar{combineIds.length < 2 ? ' — elige al menos otro' : ''}</span>
                        <label className="field" style={{ maxWidth: 140, flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                          <span>Duración (s)</span>
                          <input type="number" min={10} max={170} value={combineTarget} onChange={(e) => setCombineTarget(Number(e.target.value) || 45)} style={{ width: 70 }} />
                        </label>
                        <button className="primary" disabled={isCombining || combineIds.length < 2} onClick={handleCombineClips}>
                          {isCombining ? 'Montando…' : '🔗 Combinar con IA'}
                        </button>
                        <button disabled={isCombining} onClick={() => setCombineIds([])}>Cancelar</button>
                        <span className="help">La IA monta un short nuevo con fragmentos de estos clips, con corte seco. Los originales no se tocan.</span>
                      </div>
                    )}

                    <div className="jobs-list clip-list" style={{ maxHeight: 'unset' }}>
                  {clipCandidates.map((clip) => (
                    <article key={clip.id} id={`clip-${clip.id}`} className="clip-card">
                      <div className="viewer-header">
                        <div>
                          <h3 style={{ margin: 0 }}>
                            {!clip.segments?.length && (
                              <input
                                type="checkbox"
                                title="Elegir para combinar con otros clips"
                                checked={combineIds.includes(clip.id)}
                                onChange={(e) => setCombineIds((prev) => e.target.checked ? [...prev, clip.id] : prev.filter((id) => id !== clip.id))}
                                style={{ marginRight: 8, verticalAlign: 'middle' }}
                              />
                            )}
                            <span className="status completed" style={{ marginRight: 8 }}>{clip.segments?.length ? '🔗 combinado' : clip.manual ? '✋ manual' : clip.score}</span>
                            {clip.title || 'Clip'}
                          </h3>
                          {clip.segments?.length
                            ? <p className="help">{clip.segments.length} fragmentos ({Math.round(clip.duration)}s)</p>
                            : <p className="help">{formatSeconds(clip.start)} → {formatSeconds(clip.end)} ({Math.round(clip.duration)}s)</p>}
                          <div className="actions-row" style={{ gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
                            <span className="help">Inicio</span>
                            <button className="link-btn" onClick={() => handleTrimClip(clip, -5, 0)}>−5s</button>
                            <button className="link-btn" onClick={() => handleTrimClip(clip, 5, 0)}>+5s</button>
                            <span className="help" style={{ marginLeft: 8 }}>Fin</span>
                            <button className="link-btn" onClick={() => handleTrimClip(clip, 0, -5)}>−5s</button>
                            <button className="link-btn" onClick={() => handleTrimClip(clip, 0, 5)}>+5s</button>
                            <button className="link-btn" onClick={() => handleTrimClip(clip, 0, 10)}>+10s</button>
                            <span className="help" style={{ opacity: 0.6 }}>(luego Regenerar)</span>
                          </div>
                        </div>
                        <div className="actions-row">
                          {clip.uploaded ? <span className="status completed">Subido</span>
                            : clip.rendered ? <span className="status completed">Renderizado</span>
                            : <span className="status queued">Sin generar</span>}
                        </div>
                      </div>

                      <p className="card-detail">{clip.reason}</p>

                      {!!clip.segments?.length && (
                        <div className="actions-row" style={{ alignItems: 'flex-end', flexWrap: 'wrap' }}>
                          <label className="field" style={{ flex: 1, minWidth: 260 }}>
                            <span>Fragmentos (en orden, tiempos del vídeo original)</span>
                            <input
                              value={segmentDrafts[clip.id] ?? formatSegments(clip.segments)}
                              onChange={(e) => setSegmentDrafts((prev) => ({ ...prev, [clip.id]: e.target.value }))}
                              disabled={clip.uploaded}
                            />
                          </label>
                          {segmentDrafts[clip.id] !== undefined && segmentDrafts[clip.id] !== formatSegments(clip.segments) && (
                            <button className="primary" disabled={savingSegmentsId === clip.id} onClick={() => handleSaveSegments(clip)}>
                              {savingSegmentsId === clip.id ? 'Montando…' : 'Aplicar fragmentos'}
                            </button>
                          )}
                        </div>
                      )}

                      <div className="form-grid">
                        <label className="field">
                          <span>Encuadre</span>
                          <select value={clip.focus} onChange={(e) => {
                            const f = e.target.value as 'left' | 'center' | 'right' | 'follow' | 'facecam'
                            handleClipSettingChange(clip, { focus: f })
                            if (f === 'facecam' && activeCampaign && !activeCampaign.facecam) handleOpenFacecam(activeCampaign)
                          }}>
                            <option value="left">Izquierda</option>
                            <option value="center">Centro</option>
                            <option value="right">Derecha</option>
                            <option value="follow">🎙 Seguir al hablante</option>
                            <option value="facecam">🎥 Facecam + pantalla</option>
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
                        {fxPresets.length > 0 && (
                          <label className="field">
                            <span>Efectos</span>
                            <select
                              value={clip.fxPreset || 'none'}
                              onChange={(e) => handleClipSettingChange(clip, { fxPreset: e.target.value })}
                            >
                              <option value="none">Sin efectos</option>
                              {fxPresets.map((name) => (
                                <option key={name} value={name}>{`✨ ${name}`}</option>
                              ))}
                            </select>
                          </label>
                        )}
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
                        <a className="panel-link" href={api.clipHorizontalUrl(clip.id)} download title="Tramo original en 16:9, sin subtítulos ni nada encima (720p, para WhatsApp). Tarda unos segundos la primera vez.">16:9 para WhatsApp</a>
                        {clip.rendered && clip.rawPath && (
                          <a className="panel-link" href={api.fileUrl(clip.rawPath)} download title="Vertical con encuadre y blur, sin subtítulos, texto fijo, watermark ni cierre">Descargar sin subtítulos</a>
                        )}
                        {clip.rendered && !clip.uploaded && (
                          <>
                            <select value={uploadPrivacy} onChange={(e) => setUploadPrivacy(e.target.value)} style={{ padding: '8px 10px', borderRadius: 8 }}>
                              <option value="private">Privado</option>
                              <option value="unlisted">Oculto (unlisted)</option>
                              <option value="public">Público</option>
                            </select>
                            <button className="panel-link panel-link-button" disabled={uploadingClipId === clip.id} onClick={() => handleUploadClip(clip)}>
                              {uploadingClipId === clip.id ? 'Subiendo...' : 'Subir a YouTube'}
                            </button>
                          </>
                        )}
                        {clip.uploaded && (
                          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                            <span className="help">Visibilidad:</span>
                            <select value={clip.youtubePrivacy || 'private'} onChange={(e) => handleSetVisibility(clip, e.target.value)} style={{ padding: '8px 10px', borderRadius: 8 }}>
                              <option value="private">Privado</option>
                              <option value="unlisted">Oculto</option>
                              <option value="public">Público</option>
                            </select>
                          </label>
                        )}
                        {clip.rendered && clip.uploaded && (
                          <button
                            className="panel-link panel-link-button"
                            /* Una sola resubida. A la segunda habría ya dos vídeos
                               huérfanos en el canal y solo se guarda el enlace de
                               uno, así que el viejo se perdería de vista. */
                            disabled={uploadingClipId === clip.id || !!clip.previousYoutubeUrl}
                            onClick={() => handleReuploadClip(clip)}
                            title={clip.previousYoutubeUrl
                              ? 'Este clip ya se resubió una vez. Oculta o borra el vídeo antiguo antes de volver a subirlo.'
                              : 'Sube de nuevo el clip renderizado. YouTube crea un vídeo nuevo: el anterior sigue publicado.'}
                          >
                            {uploadingClipId === clip.id
                              ? 'Subiendo...'
                              : clip.previousYoutubeUrl ? '✓ Ya resubido' : 'Resubir a YouTube'}
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
                              <button className="link-btn" onClick={() => handleCopyUrl(clip.seoTitle!)}>
                                {copiedUrl && copiedUrl === clip.seoTitle ? '¡Copiado!' : 'Copiar'}
                              </button>
                            </div>
                            <input readOnly value={clip.seoTitle} />
                          </div>
                          <div className="seo-field">
                            <div className="seo-head">
                              <span>Descripcion</span>
                              <button className="link-btn" onClick={() => handleCopyUrl(clip.seoDescription || '')}>
                                {copiedUrl && copiedUrl === (clip.seoDescription || '') ? '¡Copiado!' : 'Copiar'}
                              </button>
                            </div>
                            <textarea readOnly rows={6} value={clip.seoDescription || ''} />
                          </div>
                          <div className="seo-field">
                            <div className="seo-head">
                              <span>Tags</span>
                              <button className="link-btn" onClick={() => handleCopyUrl(clip.seoTags || '')}>
                                {copiedUrl && copiedUrl === (clip.seoTags || '') ? '¡Copiado!' : 'Copiar'}
                              </button>
                            </div>
                            <textarea readOnly rows={2} value={clip.seoTags || ''} />
                          </div>
                        </div>
                      )}

                      {clip.rendered && (
                        <div className="seo-box">
                          <div className="seo-head">
                            <span>Cierre + miniatura (fadeout de audio + fotograma final con el caption grande). Por defecto el del 50%; cámbialo y regenera si quieres otro.</span>
                            <button className="link-btn" disabled={extractingFramesId === clip.id} onClick={() => handleExtractFrames(clip)}>
                              {extractingFramesId === clip.id ? 'Extrayendo...' : 'Ver 3 fotogramas'}
                            </button>
                          </div>
                          {clipFrames[clip.id] && (
                            <div className="frame-choices">
                              {clipFrames[clip.id].map((f) => (
                                <button
                                  key={f.percent}
                                  className={clip.endcardPercent === f.percent ? 'frame-choice selected' : 'frame-choice'}
                                  onClick={() => handleClipSettingChange(clip, { endcardPercent: f.percent })}
                                >
                                  <img src={api.fileUrl(f.path)} alt={`${f.percent}%`} />
                                  <span>{f.percent}%</span>
                                </button>
                              ))}
                              <button
                                className={!clip.endcardPercent ? 'frame-choice selected' : 'frame-choice'}
                                onClick={() => handleClipSettingChange(clip, { endcardPercent: 0 })}
                              >
                                <span style={{ padding: '30px 10px' }}>Sin cierre</span>
                              </button>
                            </div>
                          )}
                          {clip.endcardPercent ? (
                            <p className="help">✅ Cierre con el fotograma del {clip.endcardPercent}%. Si eliges otro, pulsa <strong>Regenerar</strong> para aplicarlo.</p>
                          ) : null}
                        </div>
                      )}

                      {clip.previousYoutubeUrl && (
                        <p className="help">
                          ⚠️ Resubido. El vídeo anterior sigue publicado:{' '}
                          <a className="panel-link" href={clip.previousYoutubeUrl} target="_blank" rel="noreferrer">
                            {clip.previousYoutubeUrl}
                          </a>{' '}
                          — ocúltalo o bórralo en Studio si ya no lo quieres.
                        </p>
                      )}

                      {clip.youtubeUrl && (
                        <div className="actions-row" style={{ alignItems: 'center' }}>
                          <a className="panel-link" href={clip.youtubeUrl} target="_blank" rel="noreferrer">{clip.youtubeUrl}</a>
                          <button className="panel-link panel-link-button" onClick={() => handleCopyUrl(clip.youtubeUrl!)}>
                            {copiedUrl === clip.youtubeUrl ? '¡Copiado!' : 'Copiar enlace'}
                          </button>
                          {activeCampaign?.campaignUrl?.trim() && (
                            <>
                              <button
                                className={clip.submitted ? 'submit-flag submitted' : 'submit-flag'}
                                onClick={() => handleToggleSubmitted(clip)}
                                title="Marcar si ya has enviado este clip a la campaña de Whop"
                              >
                                {clip.submitted ? '✅ Submiteado a Whop' : 'Marcar submiteado'}
                              </button>
                              {!clip.submitted && clip.uploadedAt && (() => {
                                const remainingMin = Math.floor((30 * 60000 - (now - new Date(clip.uploadedAt).getTime())) / 60000)
                                return remainingMin >= 0 ? (
                                  <span className={remainingMin <= 5 ? 'submit-timer urgent' : 'submit-timer'}>
                                    ⏱ {remainingMin} min para submitear
                                  </span>
                                ) : (
                                  <span className="submit-timer expired">⛔ fuera de plazo (&gt;30 min)</span>
                                )
                              })()}
                            </>
                          )}
                        </div>
                      )}

                      <div className="clip-media-row">
                        {clip.rendered && clip.renderedPath && (
                          <div className="clip-preview">
                            <video
                              key={renderNonce[clip.id] || 0}
                              className="media-preview"
                              style={{ maxHeight: '46vh', width: 'auto' }}
                              controls
                              src={`${api.fileUrl(clip.renderedPath)}&_=${renderNonce[clip.id] || 0}`}
                            />
                            {renderingClipKey === clip.id && (
                              <div className="clip-preview-overlay">…regenerando…</div>
                            )}
                          </div>
                        )}

                        <div className="blur-panel">
                          <div className="seo-head">
                            <span>Blur de personas (marca a quién difuminar)</span>
                            <span style={{ display: 'flex', gap: 10 }}>
                              {(() => {
                                let n = 0
                                try { n = (JSON.parse(clip.manualBlur || '[]') as unknown[]).length } catch { n = 0 }
                                return (
                                  <button className="link-btn" title="Dibujar un rectángulo fijo a difuminar en todo el clip" onClick={() => handleOpenManualBlur(clip)}>
                                    ▭ Región manual{n ? ` (${n})` : ''}
                                  </button>
                                )
                              })()}
                              <button className="link-btn" disabled={detectingPersonsId === clip.id} onClick={() => handleDetectPersons(clip, (clipPersons[clip.id]?.length ?? 0) > 0)}>
                                {detectingPersonsId === clip.id ? 'Detectando...' : ((clipPersons[clip.id]?.length ?? 0) > 0 ? 'Re-detectar' : 'Detectar personas')}
                              </button>
                            </span>
                          </div>
                          {detectingPersonsId === clip.id && !clipPersons[clip.id] && (
                            <p className="help" style={{ margin: '8px 0 0' }}>
                              ⏳ Detectando personas… en clips largos puede tardar 1–2 min (corta y analiza todo el tramo). No cierres la página.
                            </p>
                          )}
                          {clipPersons[clip.id] && (() => {
                            let selected: number[] = []
                            try { selected = JSON.parse(clip.blurPersons || '[]') } catch { selected = [] }
                            return (
                              <>
                                <div className="person-grid">
                                  {clipPersons[clip.id].map((p, idx) => {
                                    const isBlur = selected.includes(p.id)
                                    return (
                                      <button
                                        key={p.id}
                                        className={`person-thumb${isBlur ? ' selected' : ''}`}
                                        title="Ampliar y difuminar"
                                        onClick={() => setLightbox({ clipId: clip.id, index: idx })}
                                      >
                                        {p.thumb ? <img src={api.fileUrl(p.thumb)} alt={`#${p.id}`} /> : <span className="person-noimg">#{p.id}</span>}
                                        <span className="person-tag">{isBlur ? '🌫' : `#${p.id}`}</span>
                                      </button>
                                    )
                                  })}
                                </div>
                                <p className="help" style={{ margin: '6px 0 0' }}>
                                  Clic en un crop para <strong>ampliarlo</strong> (flechas ← → para navegar) y difuminar ahí.
                                  Marca a las mujeres → se difuminan al <strong>Regenerar</strong>. Ante la duda, marca de más.
                                  También puedes usar el 🌫 de cada miniatura en los tramos de abajo.
                                </p>

                                {clipSegments[clip.id] && clipSegments[clip.id].length > 0 && (() => {
                                  let plan: FocusPlanItem[] = []
                                  try { plan = JSON.parse(clip.focusSegments || '[]') } catch { plan = [] }
                                  return (
                                    <div className="focus-plan">
                                      <div className="seo-head" style={{ marginTop: 10 }}>
                                        <span>🎯 Enfoque por tramo — clic en la miniatura para centrar (o auto = quien habla); 🌫 para difuminar; 📍 punto para elegir el enfoque clicando en el frame (planos generales)</span>
                                      </div>
                                      {clipSegments[clip.id].map((seg, i) => {
                                        const hasCx = plan[i]?.cx != null
                                        const cur = hasCx ? -999 : (plan[i]?.personId ?? seg.autoPersonId)
                                        return (
                                          <div key={i} className="focus-seg">
                                            <span className="focus-seg-time">{seg.start.toFixed(0)}–{seg.end.toFixed(0)}s</span>
                                            <div className="focus-seg-choices">
                                              {seg.persons.map((pp) => {
                                                const isBlur = selected.includes(pp.id)
                                                return (
                                                  <div
                                                    key={pp.id}
                                                    className={`fs-p${cur === pp.id ? ' sel' : ''}${isBlur ? ' blur' : ''}`}
                                                  >
                                                    <button
                                                      className="fs-pick"
                                                      title={pp.id === seg.autoPersonId ? 'Quien habla (auto)' : 'Centrar en esta persona'}
                                                      onClick={() => handleSetSegmentFocus(clip, clipSegments[clip.id], i, pp.id)}
                                                    >
                                                      {pp.thumb ? <img src={api.fileUrl(pp.thumb)} alt={`#${pp.id}`} /> : <span>#{pp.id}</span>}
                                                      {pp.id === seg.autoPersonId && <span className="fs-auto">auto</span>}
                                                    </button>
                                                    <button
                                                      className="fs-blur"
                                                      title={isBlur ? 'Se difuminará (clic para quitar)' : 'Difuminar a esta persona (mujer)'}
                                                      onClick={() => handleToggleBlurPerson(clip, pp.id)}
                                                    >
                                                      {isBlur ? '🌫' : '○'}
                                                    </button>
                                                  </div>
                                                )
                                              })}
                                              <button className={cur === -1 ? 'fs-p ctr sel' : 'fs-p ctr'} title="Centro (sin seguir a nadie)" onClick={() => handleSetSegmentFocus(clip, clipSegments[clip.id], i, -1)}>centro</button>
                                              <button className={hasCx ? 'fs-p ctr sel' : 'fs-p ctr'} title="Elegir el punto de enfoque clicando en el frame (ideal en planos generales)" onClick={() => handleOpenFocusPoint(clip, clipSegments[clip.id], i)}>📍 punto</button>
                                            </div>
                                          </div>
                                        )
                                      })}
                                    </div>
                                  )
                                })()}
                              </>
                            )
                          })()}
                        </div>
                      </div>
                    </article>
                  ))}
                    </div>
                  </>
                )}
              </>
            )}
          </section>
        )}

        {activeSection === 'reels' && (
          <section className="panel">
            <div className="viewer-header">
              <h3 style={{ margin: 0 }}>🎬 Avatar Reel — guion + voz clonada</h3>
              <button onClick={handleNewReel}>➕ Nueva generación</button>
            </div>
            <p className="description">
              Contenido propio con IA. Fase 1: de un disparador → guion → tu voz clonada (XTTS local) → vídeo con karaoke.
              El avatar (HeyGen) y el b-roll generado llegan en fases siguientes.
            </p>

            <div className="seo-box" style={{ marginBottom: 14 }}>
              <div className="seo-head"><span>⚽ Reel desde un resumen de partido (YouTube)</span></div>
              <p className="help" style={{ marginTop: 0 }}>
                Pega el enlace del resumen: transcribe, saca los momentos clave (como en Clipping), redacta un guion
                explicativo con tu voz y monta el vídeo con <b>fotogramas reales del partido</b> recortados a vertical.
              </p>
              <div className="actions-row" style={{ alignItems: 'flex-end', flexWrap: 'wrap' }}>
                <label className="field" style={{ flex: 1, minWidth: 220 }}>
                  <span>Enlace de YouTube del resumen</span>
                  <input value={reelMatchUrl} onChange={(e) => setReelMatchUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=..." />
                </label>
                <label className="field" style={{ minWidth: 180 }}>
                  <span>Voz {reelVoices.length === 0 && '(⚠️ arranca el TTS)'}</span>
                  <select value={reelVoiceId} onChange={(e) => setReelVoiceId(e.target.value)}>
                    {reelVoices.length === 0 && <option value="">— sin voces —</option>}
                    {reelVoices.map((v) => <option key={v} value={v}>{v}</option>)}
                  </select>
                </label>
                <button className="primary" disabled={reelBusy !== '' || !reelMatchUrl.trim() || !reelVoiceId} onClick={handleMatchReel}>
                  {reelBusy === 'match' ? 'Creando reel del partido…' : '⚽ Crear reel del partido'}
                </button>
              </div>
              {reelBusy === 'match' && <p className="help">Descargando, transcribiendo, sacando momentos, voz y montaje… puede tardar varios minutos. Puedes seguir en otra pestaña; aparecerá en «Mis generaciones».</p>}
            </div>

            <label className="field span-2">
              <span>Disparador (tema, noticia, tweet, idea)</span>
              <textarea rows={3} value={reelTrigger} onChange={(e) => setReelTrigger(e.target.value)} placeholder="Ej: La BBC estrenó una cámara libre 3D para ver el mundial como en el FIFA" />
            </label>
            <div className="actions-row" style={{ alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <label className="field" style={{ flex: 1, minWidth: 220 }}>
                <span>Ángulo (opcional)</span>
                <input value={reelAngle} onChange={(e) => setReelAngle(e.target.value)} placeholder="Enfoque o gancho que quieres darle" />
              </label>
              <label className="field" style={{ maxWidth: 150 }}>
                <span>Duración (s)</span>
                <input type="number" min={15} max={90} value={reelSeconds} onChange={(e) => setReelSeconds(Number(e.target.value) || 40)} />
              </label>
              <button className="primary" disabled={reelBusy !== ''} onClick={handleGenReelScript}>
                {reelBusy === 'script' ? 'Generando…' : 'Generar guion'}
              </button>
            </div>

            {reelScript && (
              <>
                <label className="field span-2" style={{ marginTop: 12 }}>
                  <span>Guion (editable — lo que se locutará)</span>
                  <textarea rows={7} value={reelScript} onChange={(e) => setReelScript(e.target.value)} />
                </label>
                <div className="actions-row" style={{ alignItems: 'flex-end', flexWrap: 'wrap' }}>
                  <label className="field" style={{ minWidth: 220 }}>
                    <span>Voz {reelVoices.length === 0 && '(⚠️ arranca el TTS en el Windows)'}</span>
                    <select value={reelVoiceId} onChange={(e) => setReelVoiceId(e.target.value)}>
                      {reelVoices.length === 0 && <option value="">— sin voces —</option>}
                      {reelVoices.map((v) => <option key={v} value={v}>{v}</option>)}
                    </select>
                  </label>
                  <button className="primary" disabled={reelBusy !== '' || !reelVoiceId} onClick={handleGenReelVoice}>
                    {reelBusy === 'voice' ? 'Generando voz… (puede tardar)' : '🎙 Generar voz'}
                  </button>
                </div>
              </>
            )}

            {reelAudio && (
              <div className="seo-box" style={{ marginTop: 12 }}>
                <div className="seo-head"><span>🔊 Voz generada — compón el vídeo</span></div>
                <audio controls src={api.fileUrl(reelAudio)} style={{ width: '100%' }} />
                <div className="actions-row" style={{ alignItems: 'flex-end', flexWrap: 'wrap', marginTop: 10 }}>
                  <label className="field" style={{ maxWidth: 160 }}>
                    <span>Subtítulos karaoke</span>
                    <select value={reelSubs ? 'si' : 'no'} onChange={(e) => setReelSubs(e.target.value === 'si')}>
                      <option value="si">Sí</option>
                      <option value="no">No</option>
                    </select>
                  </label>
                  {reelSourceVideo && (
                    <button className="primary" disabled={reelBusy !== ''} onClick={handleRenderReel}
                            title="Re-monta el vídeo con los fotogramas reales del partido (reusa guion+voz).">
                      {reelBusy === 'compose' ? 'Renderizando…' : '🎬 Renderizar (fotogramas del partido)'}
                    </button>
                  )}
                  <button disabled={reelBusy !== ''} onClick={handleComposeReel}>
                    {reelBusy === 'compose' ? 'Componiendo…' : '⬛ Fondo simple'}
                  </button>
                  <button disabled={reelBusy !== ''} onClick={handleGenBroll} title="Genera imágenes con IA (ComfyUI) que ilustran el guion. Usa la GPU del Windows.">
                    {reelBusy === 'broll' ? 'Generando imágenes… (1-3 min)' : '🎨 Con imágenes IA'}
                  </button>
                </div>
                <p className="help">
                  {reelSourceVideo
                    ? <><strong>Renderizar</strong>: monta el vídeo con los fotogramas reales del partido (recomendado). </>
                    : null}
                  <strong>Fondo simple</strong>: negro + karaoke (sin GPU). <strong>Con imágenes IA</strong>: b-roll con ComfyUI (usa tu GPU).
                </p>
              </div>
            )}

            {reelId && (reelAudio || reelScript) && (
              <div className="seo-box" style={{ marginTop: 12 }}>
                <div className="seo-head">
                  <span>🔎 SEO para YouTube (título y descripción)</span>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <button className="link-btn" disabled={reelBusy !== ''} onClick={handleGenReelTitle}>
                      {reelBusy === 'seo' ? '…' : '✨ Generar título'}
                    </button>
                    <button className="link-btn" disabled={reelBusy !== ''} onClick={handleGenReelDesc}>
                      {reelBusy === 'seo' ? '…' : '✨ Generar descripción'}
                    </button>
                  </div>
                </div>
                <input value={reelTitle} onChange={(e) => setReelTitle(e.target.value)} placeholder="Título del vídeo (SEO) — también se usa como título en pantalla" maxLength={100} style={{ width: '100%' }} />
                <textarea rows={5} value={reelDescription} onChange={(e) => setReelDescription(e.target.value)}
                          placeholder="Descripción SEO (pulsa «Generar descripción»; incluye el enlace de YouTube si el reel ya está publicado)" style={{ marginTop: 8, width: '100%' }} />
                <p className="help">Se guardan y se usan al subir a YouTube. La descripción incluye el enlace ▶️ si el reel ya tiene URL de YouTube.</p>
              </div>
            )}

            {reelVideo && (
              <div className="seo-box" style={{ marginTop: 12 }}>
                <div className="seo-head">
                  <span>✅ Reel compuesto — súbelo a un canal</span>
                  <a className="link-btn" href={api.fileUrl(reelVideo)} target="_blank" rel="noreferrer">Descargar</a>
                </div>
                <div className="clip-media-row" style={{ alignItems: 'flex-start' }}>
                  <video key={reelVideoV} controls src={`${api.fileUrl(reelVideo)}${reelVideoV ? `&_v=${reelVideoV}` : ''}`} style={{ width: 200, borderRadius: 10, background: '#000' }} />
                  <div style={{ flex: 1, minWidth: 240 }}>
                    <div className="seo-box" style={{ marginBottom: 10 }}>
                      <div className="seo-head">
                        <span>🖼 Miniatura final (portada del Short)</span>
                        <button className="link-btn" onClick={handleGenHook}>Generar gancho IA</button>
                      </div>
                      <input value={reelHook} onChange={(e) => setReelHook(e.target.value)} placeholder="Gancho en la miniatura (ej: EL SECRETO DEL MUNDIAL)" />
                      <div className="actions-row" style={{ alignItems: 'center', flexWrap: 'wrap', marginTop: 8 }}>
                        <span className="help">Texto:</span>
                        {(['top', 'center', 'bottom'] as const).map((p) => (
                          <button key={p} className={reelThumbPos === p ? 'primary' : ''} style={{ padding: '6px 10px', borderRadius: 8 }} onClick={() => setReelThumbPos(p)}>
                            {p === 'top' ? 'Arriba' : p === 'center' ? 'Centro' : 'Abajo'}
                          </button>
                        ))}
                        <label className="link-btn" style={{ cursor: 'pointer' }}>
                          {reelThumbImg ? '✅ Imagen propia' : 'Subir propia'}
                          <input type="file" accept="image/*" style={{ display: 'none' }} onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUploadThumbImg(f); e.currentTarget.value = '' }} />
                        </label>
                        <button disabled={reelBusy !== ''} onClick={() => handlePreviewThumb(true)}>
                          {reelBusy === 'thumb' ? '…' : '🖼 Generar miniatura'}
                        </button>
                        <button disabled={reelBusy !== '' || !reelThumb} onClick={() => handlePreviewThumb(false)} title="Reusa la imagen y solo cambia el texto/posición">
                          ✏️ Actualizar texto
                        </button>
                      </div>
                      {reelThumb && (
                        <div style={{ marginTop: 10, display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                          <img src={`${api.fileUrl(reelThumb)}${reelThumbV ? `&_v=${reelThumbV}` : ''}`} alt="miniatura"
                               style={{ width: 120, borderRadius: 8, border: '1px solid #333' }} />
                          <div style={{ flex: 1, minWidth: 180 }}>
                            <p className="help" style={{ marginTop: 0 }}>Previsualización. Ajusta el texto/posición y pulsa «Actualizar texto», o «Generar miniatura» para otra imagen.</p>
                            <button className="primary" disabled={reelBusy !== ''} onClick={handleApplyThumb}>
                              {reelBusy === 'thumb' ? 'Añadiendo…' : '✅ Añadir al final del vídeo'}
                            </button>
                          </div>
                        </div>
                      )}
                      <p className="help">Imagen {reelThumbImg ? 'propia' : 'generada con IA'} + gancho, pegada al final para elegirla como portada en el móvil.</p>
                    </div>

                    <div className="actions-row" style={{ alignItems: 'flex-end', flexWrap: 'wrap' }}>
                      <label className="field" style={{ minWidth: 180 }}>
                        <span>Canal de YouTube</span>
                        <select value={reelChannelId ?? ''} onChange={(e) => setReelChannelId(Number(e.target.value) || null)}>
                          {channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                        </select>
                      </label>
                      <label className="field" style={{ maxWidth: 140 }}>
                        <span>Visibilidad</span>
                        <select value={reelPrivacy} onChange={(e) => setReelPrivacy(e.target.value)}>
                          <option value="public">Público</option>
                          <option value="unlisted">Oculto</option>
                          <option value="private">Privado</option>
                        </select>
                      </label>
                      <button className="primary" disabled={reelBusy !== '' || !reelChannelId} onClick={handleUploadReel}>
                        {reelBusy === 'upload' ? 'Subiendo…' : '📤 Subir a YouTube'}
                      </button>
                    </div>
                    {reelYoutubeUrl && (
                      <p className="help" style={{ marginTop: 8 }}>
                        ✅ Subido: <a className="panel-link" href={reelYoutubeUrl} target="_blank" rel="noreferrer">{reelYoutubeUrl}</a>
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}

            {reels.length > 0 && (
              <div style={{ marginTop: 18 }}>
                <div className="seo-head"><span>📁 Mis generaciones ({reels.length})</span></div>
                <div className="jobs-list" style={{ maxHeight: 'unset' }}>
                  {reels.map((r) => (
                    <article key={r.id} className={`card${reelId === r.id ? ' selected' : ''}`} style={{ boxShadow: 'none' }}>
                      <div className="viewer-header">
                        <div style={{ minWidth: 0 }}>
                          <p className="help" style={{ margin: 0 }}>
                            {r.video ? '🎬 vídeo' : r.audio ? '🔊 voz' : '📝 guion'} · {new Date(r.createdAt).toLocaleString()}
                          </p>
                          <p style={{ margin: '2px 0 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {r.title || r.trigger || (r.script || '').slice(0, 80) || 'Sin título'}
                          </p>
                        </div>
                        <div className="actions-row">
                          <button className="primary" onClick={() => handleOpenReel(r)}>Abrir</button>
                          <button className="link-btn" onClick={() => handleDeleteReel(r)}>Borrar</button>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            )}
          </section>
        )}

        {['plants', 'eggs', 'butterflies'].includes(activeSection) && (
          <section className="panel">
            <div className="viewer-header">
              <h3 style={{ margin: 0 }}>{KIND_UI.title}</h3>
            </div>
            <p className="description">{KIND_UI.desc}</p>

            <div className="actions-row" style={{ alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <label className="field" style={{ flex: 1, minWidth: 220 }}>
                <span>{KIND_UI.subject}</span>
                <input value={plantName} onChange={(e) => setPlantName(e.target.value)} placeholder={KIND_UI.ph} />
              </label>
              <label className="field" style={{ maxWidth: 130 }}>
                <span>Formato</span>
                <select value={plantAspect} onChange={(e) => setPlantAspect(e.target.value as '9:16' | '16:9')}>
                  <option value="9:16">9:16 (Short)</option>
                  <option value="16:9">16:9 (largo)</option>
                </select>
              </label>
              <label className="field" style={{ maxWidth: 150 }}>
                <span>Motor</span>
                <select value={plantProvider} onChange={(e) => setPlantProvider(e.target.value as 'grok' | 'veo' | 'wan')}>
                  <option value="grok">Grok (~$1.2)</option>
                  <option value="veo">Google Veo (~$2.5)</option>
                  <option value="wan">WAN local (GPU)</option>
                </select>
              </label>
              {plantProvider !== 'wan' && (
                <label className="field" style={{ maxWidth: 200 }}>
                  <span>Duración</span>
                  <select value={plantDuration} onChange={(e) => setPlantDuration(Number(e.target.value))}>
                    <option value={15}>{KIND_UI.d15}</option>
                    <option value={30}>{KIND_UI.d30}</option>
                  </select>
                </label>
              )}
              <label className="field" style={{ minWidth: 170 }}>
                <span>Música</span>
                <select value={plantMusic} onChange={(e) => setPlantMusic(e.target.value)}>
                  <option value="">🎲 Aleatoria</option>
                  {plantMusicList.map((t) => <option key={t.name} value={t.name}>{t.label}</option>)}
                </select>
              </label>
              {plantMusic && (() => { const t = plantMusicList.find((x) => x.name === plantMusic); return t
                ? <audio key={plantMusic} controls src={api.fileUrl(t.path)} style={{ height: 34, maxWidth: 220 }} /> : null })()}
              {plantKind === 'plant' && (
                <button disabled={plantBusy !== ''} onClick={handlePlantIdeas}>
                  {plantBusy === 'ideas' ? '…' : '💡 Ideas'}
                </button>
              )}
              <button className="primary" disabled={plantBusy !== '' || !plantName.trim()} onClick={handleCreatePlant}>
                {plantBusy === 'create' ? 'Generando…' : KIND_UI.create}
              </button>
            </div>
            {plantBusy === 'create' && <p className="help">Generando (plan → primera imagen → clip(s) → montaje). Puedes seguir en otra pestaña; aparece abajo.</p>}

            <div className="seo-box" style={{ marginTop: 12 }}>
              <div className="seo-head"><span>📋 Tanda (cola) — uno por línea</span></div>
              <textarea rows={4} value={plantBatchText} onChange={(e) => setPlantBatchText(e.target.value)}
                        placeholder={KIND_UI.batch} style={{ width: '100%' }} />
              <div className="actions-row" style={{ alignItems: 'center', flexWrap: 'wrap', marginTop: 8 }}>
                <span className="help">
                  {(() => { const n = plantBatchText.split('\n').filter((s) => s.trim()).length
                    const per = plantProvider === 'wan' ? 0 : plantProvider === 'veo' ? (plantDuration > 15 ? 5 : 2.5) : (plantDuration > 15 ? 3 : 1.2)
                    return n ? `${n} vídeos · ${plantProvider === 'wan' ? 'GPU local (gratis)' : '~$' + (n * per).toFixed(1)}` : 'Se generan en cadena, uno tras otro.' })()}
                </span>
                <button className="primary" disabled={plantBusy !== ''} onClick={handleBatchPlants}>
                  {plantBusy === 'create' ? 'En cola…' : '▶️ Encolar tanda'}
                </button>
              </div>
              <p className="help">Con {plantProvider === 'wan' ? 'WAN es gratis pero lento (GPU)' : 'Grok/Veo cada vídeo gasta crédito'}. Ideal para dejar generando de noche.</p>
            </div>

            {plantIdeasList.length > 0 && (
              <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {plantIdeasList.map((idea) => (
                  <button key={idea.name} className={plantName === idea.name ? 'primary' : ''} title={idea.note}
                          style={{ padding: '6px 10px', borderRadius: 999 }} onClick={() => setPlantName(idea.name)}>
                    {idea.name}
                  </button>
                ))}
              </div>
            )}

            <div className="seo-box" style={{ marginTop: 16 }}>
              <div className="seo-head">
                <span>📁 {KIND_UI.list} ({plants.filter((p) => (p.kind || 'plant') === plantKind).length})</span>
                <label className="field" style={{ maxWidth: 200 }}>
                  <span>Canal YouTube (para subir)</span>
                  <select value={plantChannelId ?? ''} onChange={(e) => setPlantChannelId(Number(e.target.value) || null)}>
                    <option value="">— elige canal —</option>
                    {channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </label>
              </div>
              {plants.filter((p) => (p.kind || 'plant') === plantKind).length === 0 && <p className="help">Aún no hay vídeos. Escribe {KIND_UI.empty} y pulsa «Crear vídeo».</p>}
              {plants.filter((p) => (p.kind || 'plant') === plantKind).map((p) => (
                <div key={p.id} className="clip-media-row" style={{ alignItems: 'flex-start', marginTop: 10, gap: 12 }}>
                  {p.video
                    ? <video controls src={api.fileUrl(p.video)} style={{ width: 160, borderRadius: 10, background: '#000' }} />
                    : p.image
                      ? <img src={api.fileUrl(p.image)} alt="frame" style={{ width: 160, borderRadius: 10 }} />
                      : <div style={{ width: 160, height: 90, borderRadius: 10, background: '#0b1120', display: 'flex', alignItems: 'center', justifyContent: 'center' }} className="help">⏳</div>}
                  <div style={{ flex: 1, minWidth: 220 }}>
                    <div style={{ fontWeight: 600 }}>🪴 {p.plant} · {p.aspect}</div>
                    <p className="help" style={{ margin: '2px 0' }}>
                      {p.video ? '✅ Listo' : '⏳ Procesando…'} · {new Date(p.createdAt).toLocaleString()}
                    </p>
                    {p.title && <div style={{ fontSize: 13, margin: '4px 0' }}><b>{p.title}</b></div>}
                    {p.seoDescription && <p className="help" style={{ whiteSpace: 'pre-wrap', maxHeight: 90, overflow: 'auto', margin: '2px 0' }}>{p.seoDescription}</p>}
                    {p.video && (
                      <div className="actions-row" style={{ gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
                        <button disabled={plantRowBusy !== ''} onClick={() => handlePlantSeo(p)}>
                          {plantRowBusy === p.id + ':seo' ? '…' : '✨ SEO inglés'}
                        </button>
                        {p.youtubeUrl
                          ? <a className="link-btn" href={p.youtubeUrl} target="_blank" rel="noreferrer">▶️ Ver en YouTube</a>
                          : <button className="primary" disabled={plantRowBusy !== '' || !plantChannelId} onClick={() => handlePlantUpload(p)}>
                              {plantRowBusy === p.id + ':up' ? 'Subiendo…' : '📤 Subir a YouTube'}
                            </button>}
                      </div>
                    )}
                    <button className="link-btn" style={{ marginTop: 4 }} onClick={() => handleDeletePlant(p)}>Borrar</button>
                  </div>
                </div>
              ))}
            </div>
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
              {downloadedVideoPath && (
                <div className="actions-row" style={{ alignItems: 'center', marginBottom: 10 }}>
                  <a
                    className="panel-link"
                    href={api.fileUrl(downloadedVideoPath)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    ⬇️ {downloadedVideoPath.split('/').pop()}
                  </a>
                  <button
                    className="panel-link panel-link-button"
                    onClick={() => handleCopyUrl(`${window.location.origin}${api.fileUrl(downloadedVideoPath)}`)}
                  >
                    {copiedUrl === `${window.location.origin}${api.fileUrl(downloadedVideoPath)}`
                      ? '¡Copiado!' : 'Copiar enlace'}
                  </button>
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
                      {getFileKind(selectedFile.path) === 'audio' && (
                        <button
                          className="panel-link panel-link-button"
                          disabled={isGeneratingTranscript}
                          onClick={() => {
                            if (transcriptFile && !window.confirm('Ya hay transcripción. ¿Volver a transcribir con AssemblyAI? Sobrescribe .txt/.vtt/.json y gasta crédito.')) return
                            handleGenerateTranscript(selectedFile)
                          }}
                        >
                          {isGeneratingTranscript ? 'Generando...' : transcriptFile ? 'Regenerar transcripción' : 'Generar transcripcion'}
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

      {lightbox && (() => {
        const persons = clipPersons[lightbox.clipId] || []
        const clip = clipCandidates.find((c) => c.id === lightbox.clipId)
        if (!persons.length || !clip) return null
        const idx = Math.max(0, Math.min(lightbox.index, persons.length - 1))
        const p = persons[idx]
        let selected: number[] = []
        try { selected = JSON.parse(clip.blurPersons || '[]') } catch { selected = [] }
        const isBlur = selected.includes(p.id)
        const go = (d: number) => setLightbox({ clipId: lightbox.clipId, index: (idx + d + persons.length) % persons.length })
        return (
          <div className="lightbox-backdrop" onClick={() => setLightbox(null)}>
            <div className="lightbox" onClick={(e) => e.stopPropagation()}>
              <button className="lb-close" title="Cerrar (Esc)" onClick={() => setLightbox(null)}>✕</button>
              <button className="lb-nav lb-prev" title="Anterior (←)" onClick={() => go(-1)}>‹</button>
              <div className="lb-stage">
                {p.thumb ? <img src={api.fileUrl(p.thumb)} alt={`#${p.id}`} /> : <div className="lb-noimg">Persona #{p.id}<br />(sin miniatura)</div>}
              </div>
              <button className="lb-nav lb-next" title="Siguiente (→)" onClick={() => go(1)}>›</button>
              <div className="lb-bar">
                <span className="lb-count">Persona #{p.id} · {idx + 1}/{persons.length}</span>
                <button
                  className={`lb-blur${isBlur ? ' on' : ''}`}
                  onClick={() => handleToggleBlurPerson(clip, p.id)}
                >
                  {isBlur ? '🌫 Se difuminará — quitar' : 'Difuminar a esta persona'}
                </button>
              </div>
            </div>
          </div>
        )
      })()}

      {manualEditor && (() => {
        const ed = manualEditor
        const close = () => { setManualEditor(null); setDrawRect(null); drawStart.current = null }
        const setRegions = (regions: Rect[]) => setManualEditor({ ...ed, regions })
        return (
          <div className="lightbox-backdrop" onClick={close}>
            <div className="manual-editor" onClick={(e) => e.stopPropagation()}>
              <div className="me-head">
                <span>▭ Región manual — arrastra para dibujar el rectángulo a difuminar (fijo, todo el clip)</span>
                <button className="lb-close" title="Cerrar" onClick={close}>✕</button>
              </div>
              <div
                className="me-stage"
                onPointerDown={(e) => {
                  const el = e.currentTarget
                  el.setPointerCapture(e.pointerId)
                  const pt = normPoint(e, el)
                  drawStart.current = pt
                  setDrawRect({ x: pt.x, y: pt.y, w: 0, h: 0 })
                }}
                onPointerMove={(e) => {
                  if (!drawStart.current) return
                  const pt = normPoint(e, e.currentTarget)
                  const s = drawStart.current
                  setDrawRect({ x: Math.min(s.x, pt.x), y: Math.min(s.y, pt.y), w: Math.abs(pt.x - s.x), h: Math.abs(pt.y - s.y) })
                }}
                onPointerUp={() => {
                  if (drawRect && drawRect.w > 0.01 && drawRect.h > 0.01) setRegions([...ed.regions, drawRect])
                  setDrawRect(null)
                  drawStart.current = null
                }}
              >
                <img src={api.fileUrl(ed.frame)} alt="fotograma del clip" draggable={false} />
                {ed.regions.map((r, i) => (
                  <div key={i} className="me-rect" style={{ left: `${r.x * 100}%`, top: `${r.y * 100}%`, width: `${r.w * 100}%`, height: `${r.h * 100}%` }}>
                    <button className="me-rect-del" title="Quitar" onPointerDown={(e) => e.stopPropagation()} onClick={() => setRegions(ed.regions.filter((_, j) => j !== i))}>✕</button>
                  </div>
                ))}
                {drawRect && <div className="me-rect drawing" style={{ left: `${drawRect.x * 100}%`, top: `${drawRect.y * 100}%`, width: `${drawRect.w * 100}%`, height: `${drawRect.h * 100}%` }} />}
              </div>
              <div className="me-bar">
                <span className="lb-count">{ed.regions.length} región(es). Se difuminan al <strong>Regenerar</strong>.</span>
                <span style={{ display: 'flex', gap: 8 }}>
                  {ed.regions.length > 0 && <button onClick={() => setRegions([])}>Borrar todas</button>}
                  <button className="lb-blur on" onClick={handleSaveManualBlur}>Guardar</button>
                </span>
              </div>
            </div>
          </div>
        )
      })()}

      {focusPicker && (() => {
        const fp = focusPicker
        const close = () => setFocusPicker(null)
        const setCx = (e: React.PointerEvent) => {
          const r = e.currentTarget.getBoundingClientRect()
          setFocusPicker({ ...fp, cx: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) })
        }
        return (
          <div className="lightbox-backdrop" onClick={close}>
            <div className="manual-editor" onClick={(e) => e.stopPropagation()}>
              <div className="me-head">
                <span>📍 Punto de enfoque — clic (o arrastra) donde quieres centrar el recorte de arriba en este tramo</span>
                <button className="lb-close" title="Cerrar" onClick={close}>✕</button>
              </div>
              <div
                className="me-stage"
                onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); drawStart.current = { x: 0, y: 0 }; setCx(e) }}
                onPointerMove={(e) => { if (drawStart.current) setCx(e) }}
                onPointerUp={() => { drawStart.current = null }}
              >
                <img src={api.fileUrl(fp.frame)} alt="fotograma del tramo" draggable={false} />
                <div className="fp-band" style={{ left: `${fp.cx * 100}%` }} />
                <div className="fp-line" style={{ left: `${fp.cx * 100}%` }} />
              </div>
              <div className="me-bar">
                <span className="lb-count">Enfoque en x={Math.round(fp.cx * 100)}%. La franja marca la zona aproximada del recorte.</span>
                <button className="lb-blur on" onClick={handleSaveFocusPoint}>Guardar</button>
              </div>
            </div>
          </div>
        )
      })()}

      {facecamEditor && (() => {
        const ed = facecamEditor
        const close = () => { setFacecamEditor(null); setDrawRect(null); drawStart.current = null }
        const cur = drawRect || ed.rect
        return (
          <div className="lightbox-backdrop" onClick={close}>
            <div className="manual-editor" onClick={(e) => e.stopPropagation()}>
              <div className="me-head">
                <span>🎥 Marca el recuadro de tu cámara (webcam) — arrastra sobre él. Irá arriba; la pantalla, abajo.</span>
                <button className="lb-close" title="Cerrar" onClick={close}>✕</button>
              </div>
              <div
                className="me-stage"
                onPointerDown={(e) => {
                  const el = e.currentTarget; el.setPointerCapture(e.pointerId)
                  const pt = normPoint(e, el); drawStart.current = pt; setDrawRect({ x: pt.x, y: pt.y, w: 0, h: 0 })
                }}
                onPointerMove={(e) => {
                  if (!drawStart.current) return
                  const pt = normPoint(e, e.currentTarget); const s = drawStart.current
                  setDrawRect({ x: Math.min(s.x, pt.x), y: Math.min(s.y, pt.y), w: Math.abs(pt.x - s.x), h: Math.abs(pt.y - s.y) })
                }}
                onPointerUp={() => {
                  if (drawRect && drawRect.w > 0.02 && drawRect.h > 0.02) setFacecamEditor({ ...ed, rect: drawRect })
                  setDrawRect(null); drawStart.current = null
                }}
              >
                <img src={api.fileUrl(ed.frame)} alt="fotograma del vídeo" draggable={false} />
                {cur && <div className="me-rect" style={{ left: `${cur.x * 100}%`, top: `${cur.y * 100}%`, width: `${cur.w * 100}%`, height: `${cur.h * 100}%` }} />}
              </div>
              <div className="me-bar">
                <label className="help" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  Zoom pantalla: {ed.zoom.toFixed(1)}×
                  <input type="range" min={1} max={2.5} step={0.1} value={ed.zoom} onChange={(e) => setFacecamEditor({ ...ed, zoom: Number(e.target.value) })} />
                </label>
                <button className="lb-blur on" disabled={!ed.rect && !drawRect} onClick={handleSaveFacecam}>Guardar</button>
              </div>
            </div>
          </div>
        )
      })()}
    </div>
  )
}
