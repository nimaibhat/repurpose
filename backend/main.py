from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import pipeline, pipeline_protein, targets, structures, drugs, docking, report, admet
from config import get_settings

settings = get_settings()

app = FastAPI(
    title="Repurpose",
    description="AI-powered drug repurposing platform",
)


@app.on_event("startup")
async def load_models():
    from services.admet import load_tox21_model
    load_tox21_model()

    from services.xgb_affinity import load_xgb_model
    load_xgb_model()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "https://*.vercel.app",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipeline_protein.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(targets.router, prefix="/api")
app.include_router(structures.router, prefix="/api")
app.include_router(drugs.router, prefix="/api")
app.include_router(docking.router, prefix="/api")
app.include_router(report.router, prefix="/api")
app.include_router(admet.router, prefix="/api")


@app.get("/")
async def root():
    return {"status": "ok", "service": "repurpose-backend"}
