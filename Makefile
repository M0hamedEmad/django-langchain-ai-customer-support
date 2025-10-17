.PHONY: install install-dev migrate run check test lint format shell reindex worker-outbox worker-inbox

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

migrate:
	python manage.py migrate

run:
	python manage.py runserver

check:
	python manage.py check
	python manage.py makemigrations --check --dry-run

test:
	pytest

lint:
	ruff check apps config tests
	ruff format --check apps config tests

format:
	ruff check --fix apps config tests
	ruff format apps config tests

shell:
	python manage.py shell

# Rebuild Chroma vectors for all FAQs (runs after Phase 1 wiring)
reindex:
	python manage.py shell -c "print('TODO Phase 1: wire FAQReindexAllView / reindex command')"

# Background workers (run under supervisord/systemd in prod)
worker-outbox:
	python manage.py process_outbox --loop

worker-inbox:
	python manage.py process_inbox --loop
