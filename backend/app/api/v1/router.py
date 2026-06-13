from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    alerts,
    auth,
    connections,
    conversations,
    dashboards,
    discovery,
    documents,
    embeddings,
    export,
    feedback,
    health,
    knowledge_graph,
    reports,
    semantic,
    tenants,
    tools,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(tenants.router)
api_router.include_router(connections.router)
api_router.include_router(discovery.router)
api_router.include_router(semantic.router)
api_router.include_router(knowledge_graph.router)
api_router.include_router(tools.router)
api_router.include_router(embeddings.router)
api_router.include_router(conversations.router)
api_router.include_router(feedback.router)
api_router.include_router(documents.router)
api_router.include_router(export.router)
api_router.include_router(dashboards.router)
api_router.include_router(alerts.router)
api_router.include_router(reports.router)
api_router.include_router(admin.router)
