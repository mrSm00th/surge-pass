import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.app.core.config import settings
from src.app.core.redis import get_redis_client
from src.app.db.database import AsyncSessionLocal
from src.app.modules.events import routers as events
from src.app.modules.organizers import routers as organizers
from src.app.modules.users import routers as users
from src.app.modules.waiting_rooms import routers as waiting_room
from src.app.modules.waiting_rooms.service import run_admission_tick
from src.app.modules.webhooks import routers as webhooks


async def _admission_loop() -> None:

    redis = get_redis_client()
    while True:
        await asyncio.sleep(settings.waiting_room_admission_interval_seconds)
        async with AsyncSessionLocal() as db:
            await run_admission_tick(redis, db)


@asynccontextmanager
async def lifespan(app: FastAPI):

    task = asyncio.create_task(_admission_loop())
    yield
    task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="SurgePass", lifespan=lifespan)

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    app.include_router(users.router)
    app.include_router(events.router)
    app.include_router(organizers.router)
    app.include_router(waiting_room.router)
    app.include_router(webhooks.router)

    return app


app = create_app()
