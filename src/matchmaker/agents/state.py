"""State schema for the Matchmaker agent graph."""

from typing import Annotated, Literal, Optional

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage


class AgentState(BaseModel):
    """Shared state that passes between agents in the graph."""

    # Conversation history with the local actor (using LangGraph's message reducer)
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)

    # Actor profile extracted from conversation
    actor_profile: Optional[str] = None

    # Raw pain points identified during interview
    identified_pain_points: list[str] = Field(default_factory=list)

    # Formalized problem statement (Context, User, Need, Insight)
    problem_statement: Optional[str] = None

    # RAG results - existing solutions found
    existing_solutions: list[dict] = Field(default_factory=list)

    # Designer's proposed solution concept
    design_proposal: Optional[str] = None

    # Whether user confirmed the design proposal
    design_confirmed: Optional[bool] = None

    # Final output - RFS or Connection document
    final_proposal: Optional[str] = None

    # Current status in the workflow
    status: Literal[
        "interviewing",
        "analyzing",
        "scouting",
        "designing",
        "awaiting_design_confirmation",
        "architecting",
        "human_handoff",
        "complete",
    ] = "interviewing"

    # Number of interview turns completed
    interview_turns: int = 0

    # Flag to indicate interview should end
    interview_complete: bool = False

    # Platform context (telegram/whatsapp)
    platform: Optional[str] = None

    # User identifier
    user_id: Optional[str] = None

    # Ecosystem preference (None = multi-chain/all, or specific like "solana", "ethereum")
    preferred_ecosystem: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True
