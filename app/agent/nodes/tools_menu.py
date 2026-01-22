from __future__ import annotations

from app.agent.models import ToolResult
from app.agent.state import CallState
from app.rag.menu_retriever import retrieve_menu_context


def handle_menu_tools(state: CallState) -> CallState:
    query = state.last_user_message() or ""
    language = state.language or "en"
    context = retrieve_menu_context(query, language)
    state.tool_results.append(
        ToolResult(tool="menu_context", payload={"items": context})
    )
    return state
