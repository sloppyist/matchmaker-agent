"""Agent node implementations for the Matchmaker graph."""

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from matchmaker.agents.prompts import (
    ANALYST_SYSTEM_PROMPT,
    ARCHITECT_SYSTEM_PROMPT,
    DESIGNER_SYSTEM_PROMPT,
    ETHNOGRAPHER_SYSTEM_PROMPT,
    HUMAN_HANDOFF_MESSAGE,
    SCOUT_SYSTEM_PROMPT,
)
from matchmaker.agents.state import AgentState
from matchmaker.db.problems import ProblemDatabase
from matchmaker.research.case_studies import CaseStudyIngester
from matchmaker.llm.client import get_llm_client

logger = logging.getLogger(__name__)


def run_ethnographer(state: AgentState) -> dict[str, Any]:
    """
    Ethnographer agent: Conducts the interview with the local actor.
    
    This node generates questions and waits for human input via HITL interrupt.
    """
    llm = get_llm_client()

    # Convert messages to format for LLM
    chat_messages = []
    for msg in state.messages:
        if isinstance(msg, HumanMessage):
            chat_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            chat_messages.append({"role": "assistant", "content": msg.content})

    # Generate next question or response
    if not chat_messages:
        # First message - introduce and ask opening question
        response = llm.generate(
            prompt="Start the interview. Introduce yourself briefly and ask an opening question about their daily work and challenges.",
            system_prompt=ETHNOGRAPHER_SYSTEM_PROMPT,
        )
    else:
        response = llm.chat(
            messages=chat_messages,
            system_prompt=ETHNOGRAPHER_SYSTEM_PROMPT,
        )

    # Check if interview is complete
    interview_complete = "[INTERVIEW_COMPLETE]" in response
    if interview_complete:
        response = response.replace("[INTERVIEW_COMPLETE]", "").strip()

    return {
        "messages": [AIMessage(content=response)],
        "status": "analyzing" if interview_complete else "interviewing",
        "interview_turns": state.interview_turns + 1,
        "interview_complete": interview_complete,
    }


def run_analyst(state: AgentState) -> dict[str, Any]:
    """
    Analyst agent: Synthesizes interview into structured problem statement.
    """
    llm = get_llm_client()

    # Compile transcript
    transcript_parts = []
    for msg in state.messages:
        role = "Interviewer" if isinstance(msg, AIMessage) else "Actor"
        transcript_parts.append(f"{role}: {msg.content}")
    transcript = "\n\n".join(transcript_parts)

    prompt = f"""Analyze this interview transcript and extract the problem statement:

{transcript}

Provide:
1. Actor Profile
2. Identified Pain Points (as a list)
3. Structured Problem Statement (Context, User, Need, Insight)"""

    response = llm.generate(prompt=prompt, system_prompt=ANALYST_SYSTEM_PROMPT)

    # Extract pain points (simple parsing)
    pain_points = []
    if "Pain Point" in response:
        lines = response.split("\n")
        for line in lines:
            if line.strip().startswith("-") or line.strip().startswith("•"):
                pain_points.append(line.strip().lstrip("-•").strip())

    return {
        "problem_statement": response,
        "identified_pain_points": pain_points if pain_points else state.identified_pain_points,
        "status": "scouting",
    }


def run_scout(state: AgentState) -> dict[str, Any]:
    """
    Scout agent: Searches problem database for relevant use cases, solutions,
    and real-world case studies.
    
    Finds similar problems that have been solved before, with existing solutions,
    potential approaches, and actual implementations.
    """
    llm = get_llm_client()
    problem_db = ProblemDatabase(skip_test=True)
    case_study_ingester = CaseStudyIngester()

    # Check if user expressed ecosystem preference
    ecosystem = state.preferred_ecosystem
    
    # Search for relevant use cases based on problem statement
    use_cases = []
    case_studies = []
    
    if state.problem_statement:
        # Search use cases
        try:
            results = problem_db.search_use_cases(
                query=state.problem_statement,
                limit=5,
                similarity_threshold=0.2,
                chain=ecosystem,
            )
            use_cases = [
                {
                    "name": uc.name,
                    "problem_statement": uc.problem_statement,
                    "existing_solutions": uc.existing_solutions,
                    "potential_approaches": uc.potential_approaches,
                    "blockchain_justification": uc.blockchain_justification,
                    "implementation_complexity": uc.implementation_complexity,
                    "chains": uc.chains,
                    "similarity": uc.similarity,
                }
                for uc in results
            ]
        except Exception as e:
            logger.warning(f"Problem search failed: {e}")

        # Search case studies (real-world implementations)
        try:
            cs_results = case_study_ingester.search_case_studies(
                query=state.problem_statement,
                limit=3,
                chain=ecosystem,
            )
            case_studies = [
                {
                    "title": cs.title,
                    "entity": cs.entity,
                    "location": cs.location,
                    "summary": cs.summary,
                    "chains": cs.chains,
                    "status": cs.status,
                    "url": cs.url,
                }
                for cs in cs_results
            ]
        except Exception as e:
            logger.warning(f"Case study search failed: {e}")

    # Format use cases for analysis
    if use_cases:
        use_cases_text = ""
        for uc in use_cases:
            use_cases_text += f"\n### {uc['name']} (similarity: {uc['similarity']:.2f})\n"
            use_cases_text += f"**Problem:** {uc['problem_statement'][:200]}...\n"
            if uc['existing_solutions']:
                use_cases_text += "**Existing Solutions:**\n"
                for sol in uc['existing_solutions'][:3]:
                    use_cases_text += f"- {sol.get('name', 'Unknown')}: {sol.get('description', '')}\n"
            if uc['potential_approaches']:
                use_cases_text += "**Potential Approaches:**\n"
                for app in uc['potential_approaches'][:2]:
                    use_cases_text += f"- {app.get('name', 'Unknown')}: {app.get('description', '')}\n"
    else:
        use_cases_text = "No similar use cases found in the database."

    # Format case studies
    if case_studies:
        case_studies_text = "\n## Real-World Implementations\n"
        for cs in case_studies:
            chains_str = ', '.join(cs['chains']) if cs['chains'] else 'N/A'
            case_studies_text += f"\n### {cs['title']}\n"
            case_studies_text += f"**Entity:** {cs['entity']} ({cs['location']})\n"
            case_studies_text += f"**Chains:** {chains_str} | **Status:** {cs['status']}\n"
            case_studies_text += f"**Summary:** {cs['summary']}\n"
            case_studies_text += f"**Source:** {cs['url']}\n"
    else:
        case_studies_text = "\nNo real-world case studies found for this problem type."

    prompt = f"""Problem Statement:
{state.problem_statement}

## Related Use Cases & Solutions
{use_cases_text}
{case_studies_text}

Analyze the matches, identify what existing solutions could help, reference relevant case studies, and highlight gaps where new solutions are needed."""

    response = llm.generate(prompt=prompt, system_prompt=SCOUT_SYSTEM_PROMPT)

    # Add analysis to messages for context
    return {
        "existing_solutions": use_cases,
        "messages": [AIMessage(content=f"[Scout Analysis]\n{response}")],
        "status": "designing",
    }


def run_designer(state: AgentState) -> dict[str, Any]:
    """
    Designer agent: Proposes a solution concept for user confirmation.
    """
    llm = get_llm_client()

    # Check if we have strong matches
    strong_matches = [s for s in state.existing_solutions if s.get("similarity", 0) > 0.7]

    if strong_matches:
        prompt = f"""Problem Statement:
{state.problem_statement}

Strong Existing Solutions Found:
{chr(10).join(f"- {s['name']}: {s['description']}" for s in strong_matches)}

Recommend connecting with existing solutions rather than building new."""
    else:
        solutions_summary = (
            "\n".join(f"- {s['name']}: {s['description']}" for s in state.existing_solutions)
            if state.existing_solutions
            else "None found"
        )

        prompt = f"""Problem Statement:
{state.problem_statement}

Partial/Related Solutions:
{solutions_summary}

Design a new solution concept that addresses the gaps."""

    response = llm.generate(prompt=prompt, system_prompt=DESIGNER_SYSTEM_PROMPT)

    return {
        "design_proposal": response,
        "messages": [AIMessage(content=response)],
        "status": "awaiting_design_confirmation",
    }


def process_design_confirmation(state: AgentState) -> dict[str, Any]:
    """
    Process user's response to design proposal.
    """
    # Get the last human message
    last_human_msg = None
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            last_human_msg = msg.content.lower().strip()
            break

    if not last_human_msg:
        return {"status": "awaiting_design_confirmation"}

    # Check for confirmation
    confirmed = any(word in last_human_msg for word in ["yes", "si", "proceed", "confirm", "ok", "good", "looks good"])
    rejected = any(word in last_human_msg for word in ["no", "wrong", "bad", "doesn't", "don't", "human", "talk to someone"])

    if confirmed:
        return {
            "design_confirmed": True,
            "status": "architecting",
        }
    elif rejected:
        return {
            "design_confirmed": False,
            "status": "human_handoff",
        }
    else:
        # Unclear response, ask for clarification
        return {
            "messages": [AIMessage(content="I want to make sure I understand. Does this solution direction work for you? Please reply 'yes' to proceed or let me know your concerns.")],
            "status": "awaiting_design_confirmation",
        }


def run_architect(state: AgentState) -> dict[str, Any]:
    """
    Architect agent: Generates final RFS or Connection document.
    """
    llm = get_llm_client()

    # Determine output type
    strong_matches = [s for s in state.existing_solutions if s.get("similarity", 0) > 0.7]

    if strong_matches and not state.design_confirmed:
        doc_type = "connection"
        prompt = f"""Generate a Connection Document.

Problem Statement:
{state.problem_statement}

Recommended Solutions:
{chr(10).join(f"- {s['name']}: {s['description']} ({s.get('url', 'No URL')})" for s in strong_matches)}

Design Proposal:
{state.design_proposal}"""
    else:
        doc_type = "rfs"
        prompt = f"""Generate a Request for Solutions (RFS) document.

Problem Statement:
{state.problem_statement}

Confirmed Design:
{state.design_proposal}

Actor Context:
{state.actor_profile or 'See problem statement'}"""

    response = llm.generate(prompt=prompt, system_prompt=ARCHITECT_SYSTEM_PROMPT)

    return {
        "final_proposal": response,
        "messages": [AIMessage(content=f"Here's the final {'Connection Document' if doc_type == 'connection' else 'Request for Solutions'}:\n\n{response}")],
        "status": "complete",
    }


def run_human_handoff(state: AgentState) -> dict[str, Any]:
    """
    Handle transfer to human designers.
    """
    return {
        "messages": [AIMessage(content=HUMAN_HANDOFF_MESSAGE)],
        "status": "complete",
    }
