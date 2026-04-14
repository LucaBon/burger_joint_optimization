PY ?= python3
PYTHONPATH := .

.PHONY: test test-fast run benchmark clean help

help:
	@echo "test       Run the full unittest suite"
	@echo "test-fast  Skip the 1000-order perf regression test"
	@echo "run        Execute the single-branch sample fixture"
	@echo "benchmark  Reproduce the policy comparison tables"
	@echo "clean      Remove __pycache__ directories"

test:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m unittest discover -s tests -t .

test-fast:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m unittest discover -s tests -t . \
		-p 'test_[a-o]*.py'

run:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m orders_optimisation.order_scheduler

benchmark:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m orders_optimisation.benchmark

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
