import redis.asyncio as redis
import uvicorn
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import RedirectResponse

from tortoise.contrib.fastapi import register_tortoise

from examples import settings
from examples.models import Admin
from fastapi_admin.app import admin_app
import logging


def create_app():
    logging.basicConfig(level="INFO")

    app = FastAPI()
    app.mount("/admin", admin_app, name="admin_app")

    @app.get("/")
    async def index():
        return RedirectResponse(url="/admin")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    register_tortoise(
        app,
        config={
            "connections": {"default": settings.DATABASE_URL},
            "apps": {
                "models": {
                    "models": ["examples.models"],
                    "default_connection": "default",
                }
            },
        },
        generate_schemas=True,
    )

    @app.on_event("startup")
    async def on_startup():
        await admin_app.configure(
            app,
            admin_model=Admin,
            redis=redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                encoding="utf8",
            ),
        )

    return app


app_ = create_app()

if __name__ == "__main__":
    uvicorn.run("main:app_", reload=True)
