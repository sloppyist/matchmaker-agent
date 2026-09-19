Project Title: Matchmaker Agent
Objective: Create a multi-agent system that autonomously interviews local actors to uncover "shadow problems," cross-references them with existing solutions (RAG), and generates formal "Request for Solutions" (RFS) proposals for student builders.

1. System Architecture
We will use a Multi-Agent StateGraph with Human-in-the-Loop (HITL) capabilities. The system is composed of four distinct agent personas:

The Ethnographer (Interviewer Node): Conducts natural language interviews with local actors (using interrupt for HITL) to dig for problems, similar to the BlockchainGov approach.

The Analyst (Synthesizer Node): Takes unstructured interview transcripts and distills them into a structured "Problem Statement."

The Scout (RAG Node): Searches a vector database of existing ecosystem projects. "Does a solution already exist?"

The Architect (RFP Node): Generates the final output—either a "Connection" (match found) or a "Builder Request" (new capstone opportunity).

2. LangGraph Specification

Code samples are suggestions but feel free to adjust the structure as needed.

A. The State Schema
This is the "shared memory" that passes between agents.

Python

from typing import TypedDict, List, Optional, Annotated
import operator

class AgentState(TypedDict):
    # The conversation history with the local actor
    messages: Annotated[List[str], operator.add]
    
    # Internal scratchpad for the agents
    actor_profile: Optional[str]      # e.g., "Farmer in Cordoba, focused on logistics"
    identified_pain_points: List[str] # Raw extracted issues
    
    # The Formalized Problem
    problem_statement: Optional[str]  # Structured definition
    
    # RAG Results
    existing_solutions: List[str]     # Matches found in the ecosystem
    
    # Final Output
    final_proposal: Optional[str]     # The text given to students/builders
    status: str                       # "interviewing", "analyzing", "complete"
B. The Nodes (Agents)
Node 1: ethnographer_agent

Role: Emulate a user researcher.

System Prompt: "You are a curiosity-driven researcher for Argentina Onchain. Your goal is to uncover hidden inefficiencies. Ask open-ended questions about their daily workflow. Do not pitch solutions yet. Dig for 'why'."

Logic:

If status is "interviewing": Generate a question.

CRITICAL HITL STEP: This node utilizes interrupt_before or interrupt_after to wait for the real human (local actor) to reply via the chat interface.

Node 2: analyst_agent

Role: Product Manager.

Input: The full conversation history from Node 1.

Action: Extracts "pain points" and formats them into a standardized "Problem Spec" (Context, User, Need, Insight).

Trigger: Activates when the Ethnographer detects the interview is "finished" (or after N turns).

Node 3: market_scout_agent (RAG)

Role: Ecosystem Historian.

Action: Takes the problem_statement and queries a Vector Store (Pinecone/Chroma) containing the "Repository of Solutions" (e.g., Solana ecosystem projects, previous hackathon winners).

Output: A list of existing_solutions with similarity scores.

Node 4: architect_agent

Role: The Capstone Designer.

Logic:

If High Similarity Match: "We found a match! You should talk to Project X." (Connection)

If No Match: "Opportunity Detected. Drafting Request for Product (RFP) for Student Builders."

Output: Generates a structured Markdown file for the cohort.

3. The Graph Workflow (Code Logic)
Here is the draft logic for the graph construction:

Python

from langgraph.graph import StateGraph, END

# Initialize Graph
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("ethnographer", run_ethnographer)
workflow.add_node("analyst", run_analyst)
workflow.add_node("scout", run_market_scout)
workflow.add_node("architect", run_architect)

# Add Edges
workflow.set_entry_point("ethnographer")

# Conditional Logic: Keep interviewing until sufficient data is gathered
def interview_router(state):
    # Heuristic: If 5 messages exchanged or "thank you" detected -> Analyze
    if len(state["messages"]) > 5 or "goodbye" in state["messages"][-1].lower():
        return "analyst"
    return "ethnographer" # Loop back to ask more questions

workflow.add_conditional_edges(
    "ethnographer",
    interview_router,
    {
        "ethnographer": "ethnographer", 
        "analyst": "analyst"
    }
)

workflow.add_edge("analyst", "scout")
workflow.add_edge("scout", "architect")
workflow.add_edge("architect", END)

# Compile with Persistence (Required for HITL)
from langgraph.checkpoint import MemorySaver
checkpointer = MemorySaver()
app = workflow.compile(checkpointer=checkpointer, interrupt_before=["ethnographer"])
