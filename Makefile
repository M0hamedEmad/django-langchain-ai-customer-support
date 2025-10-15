.PHONY: install migrate run check test shell reindex

install:
	pip install -r requirements.txt

migrate:
	python manage.py migrate

run:
	python manage.py runserver

check:
	python manage.py check
	python manage.py makemigrations --check --dry-run

shell:
	python manage.py shell

# Rebuild Chroma vectors for all FAQs (runs after Phase 1 wiring)
reindex:
	python manage.py shell -c "print('TODO Phase 1: wire FAQReindexAllView / reindex command')"
