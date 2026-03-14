# OF-Scraper

Carpeta recomendada para dejar ordenada la configuracion del flujo `Descargar Azul`.

Uso sugerido desde la web:

- `Binario`: `ofscraper`
- `Perfil`: `main`
- `Ruta config`: `ofscraper/config.json`
- `Preset`: uno de los presets del formulario
- `Argumentos extra`: solo si necesitas afinar algo puntual

Ejemplos de rutas utiles:

- `ofscraper/config.json`
- `ofscraper/profiles/main/`
- `ofscraper/output/`

Plantilla inicial:

- Copia `ofscraper/config.example.json` a `ofscraper/config.json`
- Usa `main` como perfil inicial
- Deja que la autenticacion de `ofscraper` genere sus propios ficheros de sesion dentro de `ofscraper/profiles/main/`

Ejemplo base de `config.json`:

```json
{
  "main_profile": "main",
  "file_options": {
    "save_location": "/workspace/output/ofscraper",
    "dir_format": "{model_username}/{response_type}/{media_type}",
    "file_format": "{postedAt}_{media_id}_{filename}.{ext}",
    "textlength": 80,
    "space-replacer": "-"
  }
}
```

Que hace ese ejemplo:

- `main_profile`: deja `main` como perfil por defecto
- `save_location`: guarda el contenido en `output/ofscraper` dentro del proyecto
- `dir_format`: ordena por modelo, tipo de respuesta y tipo de media
- `file_format`: crea nombres con fecha, `media_id` y nombre original

Autenticacion:

- Las credenciales y la sesion no van en este `config.json`
- El `config.json` sirve sobre todo para rutas, perfil y formato de salida
- La autenticacion real la tendras que hacer con `ofscraper` usando ese mismo `config.json` y perfil

Notas:

- Esta carpeta solo organiza tu proyecto; no instala `ofscraper` por si sola.
- La autenticacion y la configuracion real de `ofscraper` corren por tu cuenta.
- El flujo azul esta aislado para no interferir con `yt-dlp` ni con el pipeline principal.
