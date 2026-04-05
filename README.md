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
- For production, set a strong `FLASK_SECRET_KEY` or `SECRET_KEY` in your environment.
