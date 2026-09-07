# Initial setup

This repository contains sample data only. Do not commit production databases, exports, credentials, or a populated `.env` file.

1. Install the Python version appropriate for this legacy application and create a virtual environment.
2. Activate the environment and run `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and replace every placeholder with a newly issued value. Keep `.env` local; it is ignored by Git.
4. Set `DATABASE_URL` to a local/test database or an approved managed database. Never paste its password into source code.
5. Start the application using the command in `Procfile`, or run the primary Python entry point directly.

Generate a session secret with `python -c "import secrets; print(secrets.token_hex(32))"`. Revoke any credentials that were ever committed before using this code.

