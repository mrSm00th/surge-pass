from fastapi import FastAPI
from src.app.modules.users import routers as users


def create_app() -> FastAPI:
    app = FastAPI(title="SurgePass")

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    app.include_router(users.router)

    return app


app = create_app()
