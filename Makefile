.PHONY: install run dashboard clean test validate demo

install:
	pip install -e ".[dev]"
	playwright install chromium

run:
	@echo "Example: cat examples/urls.txt | rased -o out -v"

dashboard:
	PORT=8787 python3 dashboard/server.py

demo:
	echo "https://example.com" | python3 -m rased -o /tmp/rased-demo -v -j "document.title" --no-third-party

test:
	pytest -v

validate:
	python3 scripts/validate.py

clean:
	rm -rf out /tmp/rased-* /tmp/pf-* .pytest_cache .ruff_cache build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
