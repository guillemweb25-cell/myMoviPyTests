# Cookies

Ficheros `cookies.txt` en formato Netscape, exportados desde el navegador con la
sesión iniciada. Sirven para los sitios que piden login (Instagram, YouTube con
verificación, etc.).

## El nombre importa

Nómbralos **`<dominio>_cookies.txt`**, por ejemplo:

    www.instagram.com_cookies.txt
    es.pornhub.com_cookies.txt

`download_video.py` busca por el dominio de la URL y coge el fichero solo, sin
tener que elegirlo en el desplegable. El `www.` se ignora al comparar, así que
ese fichero vale igual para `instagram.com` que para `www.instagram.com`.

Si eliges uno a mano en la UI, manda el elegido.

## Avisos

- Son **sesiones vivas** de tus cuentas: trátalos como contraseñas.
- La carpeta está en `.gitignore` (solo se versiona este README), así que no se
  suben al repositorio.
- Caducan. Si un sitio vuelve a pedir login, vuelve a exportarlas.
