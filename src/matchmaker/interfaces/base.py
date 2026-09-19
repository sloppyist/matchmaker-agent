"""Base message handler for interfacing with the agent graph."""

import logging
from typing import Optional

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from matchmaker.agents.graph import create_matchmaker_graph
from matchmaker.agents.state import AgentState
from matchmaker.db.sessions import SessionStore

logger = logging.getLogger(__name__)


class MessageHandler:
    """
    Handles message processing and graph execution for messaging platforms.
    
    This class manages:
    - Session persistence
    - Graph state management
    - HITL interrupt handling
    """

    def __init__(self, session_store: Optional[SessionStore] = None):
        self.session_store = session_store or SessionStore(skip_test=True)
        self.checkpointer = MemorySaver()
        self.graph = create_matchmaker_graph(checkpointer=self.checkpointer)

    def _get_thread_config(self, platform: str, user_id: str) -> dict:
        """Get LangGraph thread configuration."""
        return {"configurable": {"thread_id": f"{platform}:{user_id}"}}

    async def handle_message(
        self,
        platform: str,
        user_id: str,
        message: str,
    ) -> list[str]:
        """
        Handle an incoming message and return agent responses.
        
        Args:
            platform: "telegram" or "whatsapp"
            user_id: User identifier from the platform
            message: The user's message
            
        Returns:
            List of response messages to send back
        """
        config = self._get_thread_config(platform, user_id)

        # Get or create session
        session = self.session_store.get_or_create_session(platform, user_id)

        # Check if this is a new conversation or continuation
        current_state = self.graph.get_state(config)

        responses = []

        try:
            if current_state.values:
                # Continuing conversation - add human message and resume
                result = await self.graph.ainvoke(
                    {"messages": [HumanMessage(content=message)]},
                    config,
                )
            else:
                # New conversation - initialize with first message
                initial_state = {
                    "messages": [HumanMessage(content=message)],
                    "platform": platform,
                    "user_id": user_id,
                }
                result = await self.graph.ainvoke(initial_state, config)

            # Extract AI responses from result
            if result and "messages" in result:
                for msg in result["messages"]:
                    if hasattr(msg, "content") and msg.type == "ai":
                        responses.append(msg.content)

            # Update session state
            state_dict = {
                "status": result.get("status", "unknown"),
                "interview_turns": result.get("interview_turns", 0),
            }
            self.session_store.update_session_state(session.id, state_dict)

            # Save proposal if complete
            if result.get("status") == "complete" and result.get("final_proposal"):
                self.session_store.save_proposal(
                    session_id=session.id,
                    problem_statement=result.get("problem_statement", ""),
                    design_proposal=result.get("design_proposal"),
                    final_rfs=result.get("final_proposal"),
                    status="complete",
                )

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            responses.append(
                "I encountered an error processing your message. Please try again or type /restart to start over."
            )

        return responses if responses else ["I'm processing your input..."]

    async def restart_conversation(self, platform: str, user_id: str) -> str:
        """Reset the conversation for a user."""
        config = self._get_thread_config(platform, user_id)

        # Clear the graph state by starting fresh
        try:
            # Delete session from database
            session_id = f"{platform}:{user_id}"
            self.session_store.delete_session(session_id)
        except Exception as e:
            logger.warning(f"Could not delete session: {e}")

        return "Conversation reset! Let's start fresh. Tell me about yourself and the challenges you face in your work."

    def get_conversation_status(self, platform: str, user_id: str) -> dict:
        """Get the current status of a conversation."""
        config = self._get_thread_config(platform, user_id)
        state = self.graph.get_state(config)

        if state.values:
            return {
                "active": True,
                "status": state.values.get("status", "unknown"),
                "turns": state.values.get("interview_turns", 0),
            }
        return {"active": False, "status": "not_started", "turns": 0}
