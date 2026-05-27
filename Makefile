# ==============================================================================
# FAIRBET LAB - MAKEFILE DE COMANDOS ÚTILES (ENTORNO DOCKER)
# ==============================================================================

.PHONY: help build up down restart logs migrate makemigrations createsuperuser shell test ps clean

help:
	@echo "Comandos disponibles:"
	@echo "  make build          - Construye las imágenes de Docker"
	@echo "  make up             - Inicia los contenedores en segundo plano"
	@echo "  make down           - Detiene y remueve los contenedores"
	@echo "  make restart        - Reinicia los contenedores"
	@echo "  make logs           - Muestra los logs de los contenedores en tiempo real"
	@echo "  make migrate        - Ejecuta las migraciones de Django"
	@echo "  make makemigrations - Crea nuevas migraciones basadas en los modelos"
	@echo "  make createsuperuser - Crea un superusuario para el panel de administración"
	@echo "  make shell          - Abre el intérprete interactivo de Django"
	@echo "  make test           - Ejecuta los tests unitarios y de integración"
	@echo "  make ps             - Muestra el estado de los contenedores"
	@echo "  make clean          - Limpia volúmenes huérfanos y archivos temporales"

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f

migrate:
	docker-compose exec backend python manage.py migrate

makemigrations:
	docker-compose exec backend python manage.py makemigrations

createsuperuser:
	docker-compose exec backend python manage.py createsuperuser

shell:
	docker-compose exec backend python manage.py shell

test:
	docker-compose exec backend pytest

ps:
	docker-compose ps

clean:
	docker-compose down -v --remove-orphans
	find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
