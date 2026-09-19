"""FastAPI server for Matchmaker Agent."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from matchmaker.config import settings
from matchmaker.interfaces.whatsapp import router as whatsapp_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

app = FastAPI(
    title="Matchmaker Agent API",
    description="Multi-agent system for problem discovery and solution matching",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(whatsapp_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Matchmaker Agent",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


def run_server():
    """Run the FastAPI server."""
    import uvicorn

    uvicorn.run(
        "matchmaker.server:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run_server()
