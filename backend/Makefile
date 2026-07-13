.PHONY: install run dev docker-up docker-down migrate seed test lint

install:
	pip install -r requirements.txt

# Run against local SQLite, no Docker needed
run:
	uvicorn app.main:app --reload --port 8000

dev: install run

docker-up:
	docker compose up --build

docker-down:
	docker compose down

# Tables auto-create on startup (see app/main.py on_startup) — this target
# exists for parity with the blueprint's onboarding script and for CI.
migrate:
	python -c "from app.db.session import Base, engine; Base.metadata.create_all(bind=engine)"

seed:
	python -m app.seed

test:
	pytest -v

lint:
	python -m py_compile $$(find app -name '*.py')
