"""SQLAlchemy ORM models — imports all model modules so metadata is populated."""
from app.models.federation import Node, NodeIdentity  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.project import Project, ProjectMember  # noqa: F401
from app.models.epic import Epic  # noqa: F401
from app.models.task import Task  # noqa: F401
from app.models.skill import Skill, SkillVersion, SkillParent  # noqa: F401
from app.models.wiki import WikiCategory, WikiArticle, WikiVersion  # noqa: F401
from app.models.sync import SyncOutbox, SyncDeadLetter  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.audit import IdempotencyKey, McpInvocation  # noqa: F401
from app.models.settings import AppSettings  # noqa: F401
from app.models.guard import Guard, TaskGuard  # noqa: F401
from app.models.code_node import CodeNode, CodeEdge  # noqa: F401
from app.models.doc import Doc  # noqa: F401
from app.models.prompt_history import PromptHistory  # noqa: F401
from app.models.epic_proposal import EpicProposal  # noqa: F401
from app.models.context_boundary import ContextBoundary, TaskSkill  # noqa: F401
from app.models.node_bug_report import NodeBugReport  # noqa: F401
from app.models.ai_provider import AIProviderConfig  # noqa: F401
from app.models.ai_credential import AICredential  # noqa: F401
from app.models.agent_thread_session import AgentThreadSession  # noqa: F401
from app.models.project_integration import ProjectIntegration  # noqa: F401
from app.models.conductor import ConductorDispatch  # noqa: F401
from app.models.epic_run import EpicRun  # noqa: F401
from app.models.epic_run_artifact import EpicRunArtifact  # noqa: F401
from app.models.review import ReviewRecommendation  # noqa: F401
from app.models.governance_recommendation import GovernanceRecommendation  # noqa: F401
from app.models.learning_artifact import LearningArtifact  # noqa: F401
from app.models.memory import MemoryEntry, MemoryFact, MemorySession, MemorySummary  # noqa: F401
