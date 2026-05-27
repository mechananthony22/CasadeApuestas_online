# Bitácora de Lecciones Aprendidas e Intentos Fallidos - FairBet Lab

Este documento registra de forma honesta los intentos fallidos, deudas técnicas identificadas y aprendizajes obtenidos a lo largo de cada sprint de desarrollo de la plataforma FairBet Lab.

---

## Sprint 1: Infraestructura y Núcleo Obligatorio (Día 1-7)

### Intento Fallido #1: Servidor WSGI por defecto (runserver) vs Daphne en Desarrollo
* **Qué intentamos:** Configurar `manage.py runserver` normal en el contenedor de desarrollo.
* **Por qué falló:** Channels 4 requiere obligatoriamente un servidor ASGI. Al levantar con `runserver`, las peticiones de WebSockets fallaban inmediatamente con un error de protocolo (`Handshake failed`).
* **Cómo lo solucionamos:** Instalamos `daphne` en los requirements, lo colocamos en el tope de `INSTALLED_APPS` (para que sobreescriba el comando `runserver` por defecto de Django y levante automáticamente como servidor ASGI en desarrollo), y configuramos `ASGI_APPLICATION = 'config.asgi.application'`.

### Intento Fallido #2: Montaje de volumen de dependencias pip
* **Qué intentamos:** Copiar e instalar las librerías directamente en el contenedor durante el `docker build` y luego montar el volumen `./backend:/app` en desarrollo.
* **Por qué falló:** Si montamos el volumen completo de `./backend` en `/app`, sobrescribíamos carpetas como `.venv` o archivos intermedios del host si el desarrollador los tenía creados en su máquina física local, lo cual rompía el entorno.
* **Cómo lo solucionamos:** Mantuvimos las dependencias instaladas globalmente dentro del entorno Python de la imagen Docker en `/usr/local/lib/python3.12/site-packages` y solo montamos el código fuente de `./backend` a `/app` excluyendo dependencias virtuales en el host.

---

*(Este documento se seguirá actualizando en cada fase de desarrollo).*
