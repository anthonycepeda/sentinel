from fastapi import FastAPI

from api.routes import router

app = FastAPI(title="Sentinel", description="AIOps observability for a single microservice.")
app.include_router(router)
