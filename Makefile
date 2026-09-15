.PHONY: up down test evaluate logs
up:
	docker compose up --build -d
down:
	docker compose down
test:
	uv run --directory backend pytest -q
	npm --prefix frontend test
	npm --prefix frontend run build
evaluate:
	backend/.venv/bin/python scripts/evaluate.py
logs:
	docker compose logs -f backend worker
