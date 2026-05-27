# Declaración de Uso de Inteligencia Artificial (Anti-AI Disclosure)

* **Proyecto:** FairBet Lab
* **Integrante:** ANTHONY

---

## Declaración de Honestidad y Autoría
En cumplimiento con las políticas de evaluación y autoría del reto **FairBet Lab**, declaro que he utilizado herramientas de Inteligencia Artificial Generativa (en específico, **Google Gemini**) bajo una modalidad de **Pair Programming y Asistente Técnico**, asegurándome de comprender a cabalidad cada línea de código incorporada al proyecto.

---

## Detalle de Asistencia de IA por Fase

### Fase 0: Infraestructura y Estructura Base (Día 1)
* **¿Para qué se utilizó la IA?**
  * Para generar el scaffolding inicial de directorios, organizar la modularización de configuraciones (`settings/base.py`, `dev.py`, `prod.py`), y definir los archivos de dependencias base (`base.txt`, `dev.txt`, `prod.txt`).
  * Para estructurar la redacción técnica del **ADR 0001** sobre el modelo de contenedores.
* **Código Boilerplate / Trivial generado:**
  * Estructura estándar de carpetas `apps/` y archivos `apps.py` de configuración para las 7 aplicaciones Django locales.
  * Configuración básica de `celery.py` y `asgi.py` (Channels).
* **Comprensión del código:**
  * Entiendo perfectamente el funcionamiento de la variable de sistema `sys.path.insert` en `base.py` para permitir la importación limpia de modelos entre las diferentes aplicaciones de `apps/` sin requerir prefijos repetitivos.
  * Conozco a detalle por qué Daphne debe cargarse al tope de `INSTALLED_APPS` para anular el servidor WSGI nativo de Django en entorno local de desarrollo.

---

*(Este documento será ampliado en cada commit de desarrollo con el sufijo [ai-assisted] para mantener total transparencia).*
