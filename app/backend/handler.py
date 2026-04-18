from mangum import Mangum

from app.backend.main import app


handler = Mangum(app)


def get_app():
    """Expose the FastAPI app for local debug helpers and tests."""
    return app
