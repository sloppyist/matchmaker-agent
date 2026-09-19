"""LangGraph workflow definition for the Matchmaker agent."""

import logging
from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from matchmaker.agents.nodes import (
    process_design_confirmation,
    run_analyst,
    run_architect,
    run_designer,
    run_ethnographer,
    run_human_handoff,
    run_scout,
)
from matchmaker.agents.state import AgentState

logger = logging.getLogger(__name__)


def interview_router(state: AgentState) -> Literal["ethnographer", "analyst"]:
    """
    Route based on interview status.
    
    Continue interviewing until:
    - Interview explicitly marked complete by ethnographer
    - More than 6 turns have been exchanged
    - User says goodbye/thank you
    """
    if state.interview_complete:
        return "analyst"

    if state.interview_turns >= 6:
        return "analyst"

    # Check for farewell signals in last message
    if state.messages:
        last_msg = state.messages[-1].content.lower()
        farewell_signals = ["goodbye", "bye", "thank you", "thanks", "that's all", "nothing else"]
        if any(signal in last_msg for signal in farewell_signals):
            return "analyst"

    return "ethnographer"


def design_router(state: AgentState) -> Literal["architect", "human_handoff", "designer"]:
    """
    Route based on design confirmation status.
    """
    if state.design_confirmed is True:
        return "architect"
    elif state.design_confirmed is False:
        return "human_handoff"
    else:
        # Still awaiting confirmation, will be handled by HITL
        return "designer"


def create_matchmaker_graph(checkpointer=None):
    """
    Create the Matchmaker agent graph.
    
    Flow:
    1. Ethnographer interviews user (with HITL)
    2. Analyst synthesizes problem statement
    3. Scout searches for existing solutions
    4. Designer proposes solution (with HITL for confirmation)
    5. Architect generates final document OR Human handoff
    
    Args:
        checkpointer: LangGraph checkpointer for persistence. Defaults to MemorySaver.
    
    Returns:
        Compiled LangGraph application
    """
    # Initialize graph with state schema
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("ethnographer", run_ethnographer)
    workflow.add_node("analyst", run_analyst)
    workflow.add_node("scout", run_scout)
    workflow.add_node("designer", run_designer)
    workflow.add_node("design_confirmation", process_design_confirmation)
    workflow.add_node("architect", run_architect)
    workflow.add_node("human_handoff", run_human_handoff)

    # Set entry point
    workflow.set_entry_point("ethnographer")

    # Add edges
    # Ethnographer can loop or move to analyst
    workflow.add_conditional_edges(
        "ethnographer",
        interview_router,
        {
            "ethnographer": "ethnographer",
            "analyst": "analyst",
        },
    )

    # Linear flow: analyst -> scout -> designer
    workflow.add_edge("analyst", "scout")
    workflow.add_edge("scout", "designer")

    # Designer -> confirmation handling
    workflow.add_edge("designer", "design_confirmation")

    # Confirmation routing
    workflow.add_conditional_edges(
        "design_confirmation",
        design_router,
        {
            "architect": "architect",
            "human_handoff": "human_handoff",
            "designer": "designer",  # Loop back if unclear
        },
    )

    # Terminal nodes
    workflow.add_edge("architect", END)
    workflow.add_edge("human_handoff", END)

    # Use provided checkpointer or default to MemorySaver
    if checkpointer is None:
        checkpointer = MemorySaver()

    # Compile with HITL interrupts
    # Interrupt before ethnographer (for human input) and before design_confirmation (for confirmation)
    app = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["ethnographer", "design_confirmation"],
    )

    return app


def get_graph_visualization():
    """Get a visual representation of the graph for debugging."""
    graph = create_matchmaker_graph()
    try:
        return graph.get_graph().draw_mermaid()
    except Exception:
        return "Graph visualization not available"
