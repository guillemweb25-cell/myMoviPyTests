# Banco de música de fondo (reels)

`reel_compose.py` (`pick_music`) elige un `.mp3` **aleatorio** de esta carpeta y lo
mezcla por debajo de la voz (volumen 0.10, en bucle, con fade-out al final) en TODOS
los reels, salvo que se pase `--no-music`.

- Los `.mp3` están **gitignored** (`*.mp3`), así que no se versionan (pesan ~40MB).
  Viven solo en disco; en un clon nuevo hay que repoblar la carpeta.
- Origen: pistas Suno del proyecto `videos_automaticos`
  (`D:\videos_automaticos\cache\<canal>\music\*.mp3` en el host Windows 192.168.1.46).
- Para añadir más: copia cualquier `.mp3` aquí (nombre sin espacios recomendado).
- Si la carpeta está vacía o no existe, el reel se compone **sin** música (sin error).
