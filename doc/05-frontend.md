# 05 — Frontend (UI de clipping)

SPA de un solo componente grande (`src/App.tsx`) + `api.ts` (cliente HTTP tipado) +
`types.ts` + `styles.css` (tema oscuro).

## Navegación

- Barra lateral con secciones: Dashboard, Contenido Web, **Clipping**, Ejecutar
  Scripts, Historial, Explorador Output. Debajo, lista de **CANALES**.
- La navegación se **persiste en `localStorage`** (`mediaops_nav`: section, channelId,
  clipTab, campaignId) para no perder el sitio al recargar (HMR de Vite recarga a menudo).

## Sección Clipping

Subpestañas: **Crear campaña** / **Mis campañas** / YouTube ⚙.

### Crear campaña
Formulario: nombre, link del vídeo (YouTube/WeTransfer), link de campaña (Whop),
link del brief (Google Docs), cookies opcional. Al crear → descarga+transcribe (job).

### Mis campañas
Lista de campañas del canal. Al abrir una:
- Cabecera con links (Whop, vídeo original), edición de nombre y campaignUrl.
- **Reglas de la campaña (brief):** input del Google Doc + "Extraer requisitos con IA".
  Muestra caption obligatorio (copiable), texto en pantalla, handles por plataforma.
- **Parámetros de detección:** partes (0=auto), clips por parte, duración (s) +
  botón Detectar / Re-detectar.
- **Barra de render en cola** (`batch-render-bar`): selector **Encuadre (todos)** +
  botón **Generar todos los verticales (N)**. Lanza `render-all` en el backend.
- **Lista de clips** (`clip-card` cada uno).

### Tarjeta de clip (`clip-card`)
- Score + título + rango de tiempo con botones de trim (−5/+5s inicio, −5/+5/+10s fin).
- Selects: Encuadre, Zoom, Proporción, Subtítulos (`handleClipSettingChange`, que
  manda el objeto completo — incluido `endcardPercent` — para no resetear nada).
- Textarea "Texto fijo (overlay)".
- Acciones: Regenerar / Ver-Descargar / privacidad + Subir a YouTube / Visibilidad /
  Generar textos SEO.
- Caja SEO: Título, Descripción, Tags (cada uno con botón Copiar que muestra "¡Copiado!").
- **Cierre + miniatura:** "Ver 3 fotogramas" → elige 25/50/75% o "Sin cierre" → Regenerar.
- Link de YouTube + Copiar enlace + botón **Submiteado a Whop** + **cuenta atrás de 30 min**.
- Preview del vídeo con overlay "…regenerando…" durante el render (`renderNonce` para
  romper la caché tras regenerar).

## Patrones de estado importantes

- **Procesos largos = jobs de backend.** El render en cola no corre en el cliente: se
  lanza `api.renderAll(...)` y se **deriva** el estado de la lista de jobs
  (`jobs.find(j => j.script === 'render_all.py' && running/queued)`), así se recupera
  aunque recargues. Mientras corre, se refrescan los clips cada 4s para ver el progreso.
- **Reloj** (`now`, `setInterval` 20s) para la cuenta atrás de submit.
- `handleCopyUrl` guarda `copiedUrl` para el feedback "¡Copiado!" (título, desc, tags, link).
- Al cambiar de canal (`activeChannel?.id`) se recargan status YouTube, fuentes y campañas.

## api.ts / types.ts

- `api.ts`: helpers `getJson/postJson/patchJson/del`, auth por cabecera o `?token=`,
  `fileUrl(path)` para recursos, `streamJobLog` (EventSource).
- `types.ts`: `Channel`, `Campaign`, `CampaignRules`, `ClipCandidate`, `ClipSource`, `Job`, …
  `ClipCandidate` incluye `focus, zoom, topRatio, subtitles, overlayText, endcardPercent,
  submitted, uploadedAt, seoTitle/Description/Tags, rendered, uploaded, youtubeUrl`.
