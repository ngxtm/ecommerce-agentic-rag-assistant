from app.backend.main import app


def get_app():
    """Expose the FastAPI app so a future Lambda adapter can wrap it."""
    return app
