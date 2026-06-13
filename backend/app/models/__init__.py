# Import all models here so Alembic and SQLAlchemy can discover them
from app.models.tenant import Tenant
from app.models.user import User, Role, UserRole, RolePermission
from app.models.connection import Connection
from app.models.metadata import MetadataTable, MetadataColumn, MetadataRelation
from app.models.semantic import (
    SemanticEntity,
    SemanticAttribute,
    KpiDefinition,
    BusinessGlossary,
    SynonymMapping,
    BusinessRule,
)
from app.models.knowledge_graph import KnowledgeGraphNode, KnowledgeGraphEdge
from app.models.tool import Tool, ToolEmbedding, ToolTableDependency, ToolRankingWeight
from app.models.conversation import Conversation, ConversationTurn
from app.models.document import Document, DocumentChunk, DocumentEmbedding
from app.models.analytics import AlertRule, Alert
from app.models.feedback import UserFeedback, FeedbackCorrection
from app.models.audit import AuditLog
from app.models.dashboard import Dashboard, DashboardWidget
from app.models.report import ReportSchedule, ReportExecution

__all__ = [
    "Tenant",
    "User", "Role", "UserRole", "RolePermission",
    "Connection",
    "MetadataTable", "MetadataColumn", "MetadataRelation",
    "SemanticEntity", "SemanticAttribute", "KpiDefinition",
    "BusinessGlossary", "SynonymMapping", "BusinessRule",
    "KnowledgeGraphNode", "KnowledgeGraphEdge",
    "Tool", "ToolEmbedding", "ToolTableDependency", "ToolRankingWeight",
    "Conversation", "ConversationTurn",
    "Document", "DocumentChunk", "DocumentEmbedding",
    "AlertRule", "Alert",
    "UserFeedback", "FeedbackCorrection",
    "AuditLog",
    "Dashboard", "DashboardWidget",
    "ReportSchedule", "ReportExecution",
]
