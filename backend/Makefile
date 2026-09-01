.PHONY: dev test seed evaluate up down reset

up:
	docker compose up -d

down:
	docker compose down

reset:
	python -m app.db.reset

dev:
	uvicorn app.main:app --reload

test:
	pytest -q

seed:
	python -m app.simulation.seed --size 500 --seed 42

seed-demo:
	python -m app.simulation.demo_batch

evaluate:
	python -m app.evaluation.report
