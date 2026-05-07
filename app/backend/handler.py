from app.backend.main import app


def get_app():
    """Expose the FastAPI app for local debug helpers and tests."""
    return app
