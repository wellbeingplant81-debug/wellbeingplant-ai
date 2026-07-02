from fastapi import FastAPI
from app.routers.health import router as health_router
from app.routers.video import router as video_router
from app.routers.script import router as script_router
from app.routers.scene import router as scene_router
from app.routers.content import router as content_router
from app.routers.image import router as image_router
from app.routers.video_builder import router as video_builder_router
from app.routers.factory import router as factory_router
from app.routers.tts import router as tts_router
from app.routers.final_video import router as final_video_router

app = FastAPI(
    title="WellbeingPlant AI Factory",
    version="1.0.0"
)

app.include_router(health_router)
app.include_router(video_router)
app.include_router(script_router)
app.include_router(scene_router)
app.include_router(content_router)
app.include_router(image_router)
app.include_router(video_builder_router)
app.include_router(factory_router)
app.include_router(tts_router)
app.include_router(final_video_router)

@app.get("/")
def root():
    return {
        "message": "WellbeingPlant AI Factory is running!"
    }