# Personal AI OS Setup

## Requirements

- Python 3
- `pip`

## Recommended Setup

1. Create a virtual environment:
   ```powershell
   python -m venv .venv
   ```
2. Activate it:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
3. Install project dependencies:
   ```powershell
   python -m pip install -r requirements.txt
   ```
4. Start the app:
   ```powershell
   $env:FLASK_ENV = "development"
   python app.py
   ```

## Automatic Dependency Install

`app.py` now checks for core runtime packages before the Flask app starts. If `Flask`, `Flask-Login`, or `python-dotenv` is missing, it will try to install dependencies automatically using:

```powershell
python -m pip install -r requirements.txt
```

If a virtual environment is active, the installation will happen inside that environment automatically because the app uses the current Python interpreter.

## Fallback Install

If `Flask-Login` is still missing, install it directly:

```powershell
python -m pip install flask-login
```

Then run:

```powershell
python app.py
```

## Notes

- Passwords are stored hashed in SQLite.
- `requirements.txt` is the source of truth for Python dependencies.
- Keep me signed in uses a 30-day browser cookie. Browser autofill uses the credentials saved for the app's current domain.

## Render sign-in setup

1. Set a strong, stable `FLASK_SECRET_KEY` (or `SECRET_KEY`) in the service's environment. Reuse the same value across deploys. Render startup requires a configured key. The updated session format requires users to sign in once after upgrading.
2. For SQLite on Render, point `PERSONAL_AI_OS_DB` at a file on a persistent disk, such as `/var/data/database.db` on a disk mounted at `/var/data`. Copy the existing database into the mounted path before switching to it if you need to keep existing accounts and dashboard data. Render's free web services have ephemeral storage and cannot attach a persistent disk.
3. To send password reset emails over HTTPS, configure `RESEND_API_KEY` and `PASSWORD_RESET_FROM` with a sender enabled in Resend. Reset links default to `RENDER_EXTERNAL_URL`. Set `APP_BASE_URL` to the public HTTPS origin if users sign in through a custom domain. On hosts that allow SMTP, the existing Gmail setup still works with `EMAIL_ADDRESS` and `EMAIL_PASSWORD`.
