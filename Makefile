VENV_PATH?=venv
PYTHON?=python3

clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -delete
	rm -rf dist build
	rm -rf .pytest_cache
	rm -rf .tox
	rm -rf .coverage .coverage.* htmlcov
	rm -rf "$(VENV_PATH)" *.egg-info
	rm -f docs/aiobtclientrpc.rst

venv:
	"$(PYTHON)" -m venv "$(VENV_PATH)"
	"$(VENV_PATH)"/bin/pip install --upgrade pytest pytest-asyncio pytest-mock proxy.py
	"$(VENV_PATH)"/bin/pip install --upgrade tox flake8 isort coverage pytest-cov
	"$(VENV_PATH)"/bin/pip install --editable .
