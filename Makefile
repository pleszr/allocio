.PHONY: setup

# One-time developer setup after cloning: install and activate the gitleaks
# pre-commit secret-scanning hook. Safe to re-run.
setup:
	uv tool install pre-commit
	pre-commit install
	@echo "Setup complete: gitleaks pre-commit hook installed."
