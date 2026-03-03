.PHONY: install db-up db-down migrate run check

install:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt

db-up:
	docker compose up -d

db-down:
	docker compose down

migrate:
	alembic upgrade head

run:
	python -m src.bot

check:
	python -m src.bot --check
