from app.application import create_app
from app.platform.logging import configure_logging

configure_logging()
app = create_app()
