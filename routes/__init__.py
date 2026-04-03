from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.onboarding import onboarding_bp
from routes.study import study_bp
from routes.workout import workout_bp


ALL_BLUEPRINTS = [
    auth_bp,
    onboarding_bp,
    dashboard_bp,
    study_bp,
    workout_bp,
]
