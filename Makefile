.PHONY: install run test clean

install:
	python -m pip install -r requirements.txt

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -q

clean:
	rm -f data/evals.db data/evals.db-shm data/evals.db-wal
