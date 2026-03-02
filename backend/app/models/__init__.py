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
