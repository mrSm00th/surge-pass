from fastapi import FastAPI

from src.app.modules.events import routers as events
from src.app.modules.users import routers as users


def create_app() -> FastAPI:
    app = FastAPI(title="SurgePass")

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    app.include_router(users.router)
    app.include_router(events.router)

    return app


app = create_app()
