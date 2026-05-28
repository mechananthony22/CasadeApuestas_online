---
trigger: always_on
---

# Guía de Capacidades: Stack Django + PostgreSQL + Nginx con Docker

Este documento detalla las capacidades, ventajas y limitaciones de desarrollar una aplicación web utilizando **Django** (Backend), **PostgreSQL** (Base de Datos) y **Nginx** (Servidor Web/Reverse Proxy), todo orquestado mediante **Docker**.

## 🏗️ Arquitectura del Sistema

La arquitectura típica en este entorno consta de tres servicios principales comunicados a través de una red definida por Docker:

1.  **Web (Nginx):** Punto de entrada público. Maneja solicitudes HTTP/HTTPS, sirve archivos estáticos/media y actúa como reverse proxy hacia la aplicación Django.
2.  **App (Django/Gunicorn/Uvicorn):** Lógica de negocio. Procesa las solicitudes dinámicas, interactúa con la BD y genera respuestas HTML/JSON.
3.  **DB (PostgreSQL):** Persistencia de datos relacional.

---

## ✅ Lo que SÍ puedes hacer (Capacidades y Ventajas)

### 1. Aislamiento y Consistencia de Entornos

- **Reproducibilidad total:** El entorno de desarrollo es idéntico al de producción. Se elimina el problema "en mi máquina funciona".
- **Gestión de Dependencias:** Las librerías de Python (`requirements.txt` o `poetry.lock`) y las extensiones de sistema están encapsuladas en la imagen de Django. No contaminas el sistema operativo anfitrión.

### 2. Escalabilidad Horizontal Simplificada

- **Escalado del Backend:** Puedes levantar múltiples instancias del contenedor de Django fácilmente para manejar más carga, ya que Nginx distribuirá las solicitudes entre ellas (Load Balancing básico).
- **Independencia de Recursos:** Puedes limitar CPU y RAM por contenedor usando las opciones de Docker (`deploy.resources` en Compose o flags de `docker run`).

### 3. Gestión Eficiente de Archivos Estáticos y Media

- **Servido Optimizado:** Nginx sirve archivos estáticos (CSS, JS, Imágenes) directamente, liberando a Django de esta tarea pesada. Esto mejora significativamente el rendimiento y la latencia.
- **Volumenes Compartidos:** Uso de volúmenes Docker o bind mounts para compartir la carpeta `/static` y `/media` entre el contenedor de Django (que los genera/recopila) y Nginx (que los sirve).

### 4. Seguridad y Red

- **Aislamiento de la Base de Datos:** PostgreSQL no expone su puerto al exterior directamente si se configura correctamente la red de Docker. Solo el contenedor de Django puede comunicarse con él internamente.
- **Terminación SSL/TLS:** Nginx puede manejar certificados SSL (Let's Encrypt, por ejemplo) y descifrar el tráfico antes de pasarlo a Django en HTTP interno, simplificando la configuración de seguridad en la app.

### 5. Orquestación y Desarrollo Ágil

- **Docker Compose:** Levantar todo el stack con un solo comando (`docker-compose up`).
- **Hot Reloading:** En desarrollo, puedes montar el código fuente como volumen para que los cambios en Django se reflejen instantáneamente sin reconstruir la imagen.
- **Migraciones Automatizadas:** Puedes crear scripts de entrada (`entrypoint.sh`) que ejecuten `python manage.py migrate` y `collectstatic` automáticamente al iniciar el contenedor de Django.

---

## ❌ Lo que NO puedes hacer (Limitaciones y Consideraciones)

### 1. No es una Solución de "Alta Disponibilidad" Nativa

- **Single Point of Failure (SPOF):** Si usas Docker Compose simple en un solo host, si ese host cae, toda la aplicación cae. Docker no proporciona clustering ni failover automático entre nodos físicos por sí mismo (para esto necesitas Kubernetes, Swarm o soluciones de cloud gestionadas).
- **Estado de la BD:** PostgreSQL en un contenedor simple no tiene replicación automática ni sharding. Si el contenedor de la BD se corrompe y no hay volúmenes persistentes bien gestionados, pierdes datos.

### 2. Limitaciones en el Procesamiento de Tareas Asíncronas

- **Django es Síncrono por defecto:** Aunque Django 3.0+ tiene soporte ASGI, para tareas largas (envío de emails, procesamiento de imágenes, reportes pesados) **no debes** bloquear el hilo principal de Django.
- **Necesidad de Componentes Adicionales:** Este stack básico **NO incluye** un broker de mensajes (como Redis o RabbitMQ) ni un worker (como Celery). Para tareas asíncronas, debes añadir estos servicios al ecosistema Docker.

### 3. Complejidad en la Gestión de Volúmenes y Permisos

- **Problemas de Permisos Linux/Windows:** Los archivos generados por Django (ej. archivos media) pueden tener problemas de permisos cuando son accedidos por Nginx (que corre como usuario `www-data`) si no se gestionan bien los UID/GID en Docker.
- **Persistencia de Datos:** Si no configuras volúmenes named volumes correctamente para PostgreSQL, los datos se pierden al eliminar el contenedor. Docker no hace backups automáticos de tu BD.

### 4. Rendimiento en I/O Intensivo (Sin Optimización)

- **Overhead de Red:** La comunicación entre contenedores pasa por la red bridge de Docker. Aunque es rápida, no es tan rápida como un socket Unix local. Para alto rendimiento, se debe optimizar la configuración de Nginx y Gunicorn/Uvicorn.
- **Archivos Estáticos en Desarrollo vs Producción:** En desarrollo, servir estáticos con Django es fácil pero lento. En producción, debes asegurarte de que `collectstatic` se ejecute y que Nginx tenga acceso a esa ruta. Si olvidas esto, Nginx devolverá errores 404.

### 5. No Reemplaza la Configuración de Infraestructura Cloud

- **Gestión de Secretos:** Docker Compose permite variables de entorno, pero **no es un gestor de secretos seguro** para producción (los secretos pueden verse en `docker inspect`). Para producción real, necesitas integración con Vault, AWS Secrets Manager, etc.
- **Monitoreo y Logs:** Docker guarda logs, pero no los analiza ni alerta. Necesitas integrar herramientas como Prometheus, Grafana, ELK Stack o servicios de logging externos para una observabilidad real.

---

## 🚀 Ejemplo Básico de `docker-compose.yml`

```yaml
version: '3.8'

services:
  db:
    image: postgres:15-alpine
    volumes:
      - postgres_/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=mydb
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
    networks:
      - backend

  web:
    build: .
    command: gunicorn myproject.wsgi:application --bind 0.0.0.0:8000
    volumes:
      - static_volume:/app/static
      - media_volume:/app/media
    expose:
      - 8000
    environment:
      - DATABASE_URL=postgres://user:password@db:5432/mydb
    depends_on:
      - db
    networks:
      - backend

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf
      - static_volume:/app/static
      - media_volume:/app/media
    depends_on:
      - web
    networks:
      - backend

volumes:
  postgres_
  static_volume:
  media_volume:

networks:
  backend:
```
