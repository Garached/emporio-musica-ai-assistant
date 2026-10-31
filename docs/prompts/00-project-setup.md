# Phase 00 — Project Setup

**Goal:** Scaffold the project structure, packaging, environment config, and virtual environment. No agent logic yet.

---

Context: I'm building a customer service AI agent in Python for "Empório da Música",
a fictional musical instrument store. This is a technical challenge for an AI
Engineer position. The agent will use Google Gemini (via the official `google-genai`
SDK) with function calling. The store's raw data is already in `data/raw/`
(6 CSVs + a policies PDF). Do NOT modify or rename anything in `data/raw/`.

Task for this step: scaffold the project only. No agent logic yet.

1. Create this structure:
   data/raw/              (already exists, leave untouched)
   docs/prompts/          (I'll store every prompt I use with you here)
   src/emporio/__init__.py
   src/emporio/config.py
   tests/__init__.py
   .env.example
   pyproject.toml
   requirements.txt

2. requirements.txt: google-genai, python-dotenv, pandas, rich, pypdf, pytest.
   Use minimum versions (>=), not exact pins.

3. pyproject.toml: minimal config so the package is installable with
   `pip install -e .` using the src layout. Require Python >= 3.11.

4. src/emporio/config.py: load settings from a `.env` file using python-dotenv.
   Settings: GEMINI_API_KEY (required) and GEMINI_MODEL (default "gemini-2.5-flash").
   If the API key is missing, raise a clear error explaining how to create the
   .env file. Keep it simple: a small frozen dataclass plus a loader function.
   Add type hints and short docstrings.

5. .env.example: both variables with placeholder values and a comment
   explaining where to get a Gemini API key (Google AI Studio).

6. Confirm `.env` is listed in `.gitignore` (add it if not).

7. Create a virtual environment in `.venv`, install the requirements and the
   package in editable mode, and verify that `import emporio.config` works.

8. Save this exact prompt to `docs/prompts/00-project-setup.md`, with a short
   header: the phase name and its goal.

Git rules:
- Make small, logical commits as you go (not one big commit).
- Commit messages: short, in English, Conventional Commits style
  (e.g. "chore: add project structure", "feat: add env config loader").
- Do NOT push. I'll review and push myself.

When done, give me a short summary: files created, commits made, and the
command to activate the venv on Windows PowerShell.
