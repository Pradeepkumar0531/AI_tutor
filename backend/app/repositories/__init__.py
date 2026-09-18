"""Repository exports. Routes/services import from here, never from deep modules."""

from app.repositories.assessments import (  # noqa: F401
    AssessmentRepository,
    AttemptRepository,
    QuestionRepository,
    QuizRepository,
)
from app.repositories.base import BaseRepository  # noqa: F401
from app.repositories.intelligence import (  # noqa: F401
    EventRepository,
    GrowthRepository,
    MasteryRepository,
    RecommendationRepository,
)
from app.repositories.knowledge import (  # noqa: F401
    ConceptRelationshipRepository,
    ConceptRepository,
    ConversationRepository,
    MessageRepository,
)
from app.repositories.materials import (  # noqa: F401
    ChunkRepository,
    DocumentRepository,
    MaterialRepository,
    ProcessingJobRepository,
)
from app.repositories.projects import (  # noqa: F401
    ProjectRepository,
    SpaceRepository,
    UserRepository,
)
