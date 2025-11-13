.PHONY: help venv cli lint packer-dry

help:
	@echo "appliance helper targets: venv, cli, packer-dry"

venv:
	python -m venv .venv
	.venv\Scripts\pip install --upgrade pip setuptools

cli:
	.venv\Scripts\pip install -e atpctl

packer-dry:
	@echo "Run packer plan (dry)"
