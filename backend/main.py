from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import pipeline, targets, structures, drugs, docking, report

app = FastAPI(title="Repurpose", description="AI-powered drug repurposing platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://*.vercel.app",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipeline.router, prefix="/api")
app.include_router(targets.router, prefix="/api")
app.include_router(structures.router, prefix="/api")
app.include_router(drugs.router, prefix="/api")
app.include_router(docking.router, prefix="/api")
app.include_router(report.router, prefix="/api")


@app.get("/")
async def root():
    return {"status": "ok", "service": "repurpose-backend"}
