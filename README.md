# Intro to Python - Web App Refactor

Proyecto reorganizado en:

- `backend/`: API FastAPI + scripts Python en `backend/scripts`
- `frontend/`: interfaz web moderna en React + TypeScript + Vite

## Arranque con Docker

```bash
docker compose up --build
```

Aplicaciones:

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000/api/health

## Estructura

- `backend/app/main.py`: API para listar/ejecutar scripts y ver logs
- `backend/scripts/`: scripts originales de automatizacion multimedia
- `frontend/src/App.tsx`: panel principal con sidebar, jobs y logs
