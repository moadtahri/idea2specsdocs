"""Enforce clarification before planning or writing a new bundle."""

from langchain.agents.middleware import AgentMiddleware
from langchain.messages import ToolMessage

from .. import quality_store as qs
from .tools import PROJECT_DIRECTORY


class RequirementsGate(AgentMiddleware):
    async def awrap_model_call(self, request, handler):
        directory = PROJECT_DIRECTORY.get()
        if directory and qs.brief_state(directory.name)["status"] != "approved":
            allowed = {
                "ls",
                "read_file",
                "glob",
                "grep",
                "list_docs",
                "get_project_context",
                "propose_project_brief",
                "propose_work_item",
                "load_review_skill",
                "review_bundle",
                "check_bundle_contracts",
                "compact_conversation",
                "settle_decision",
                # Only for repo-reader (awrap_tool_call): discovery must not ask what the code shows.
                "task",
            }
            tools = [
                tool
                for tool in request.tools
                if (tool.get("name") if isinstance(tool, dict) else tool.name)
                in allowed
            ]
            request = request.override(tools=tools)
        return await handler(request)

    async def awrap_tool_call(self, request, handler):
        directory = PROJECT_DIRECTORY.get()
        call = request.tool_call
        if directory and qs.brief_state(directory.name)["status"] != "approved":
            name = call["name"]
            reading_source = (
                name == "task"
                and call.get("args", {}).get("subagent_type") == "repo-reader"
            )
            if (
                name in ("write_file", "edit_file", "write_todos", "execute", "task")
                and not reading_source
            ):
                return ToolMessage(
                    content="First clarify the app's vertical and service using supplied context, then propose the project brief. Ask at most three relevant questions at a time. The user must approve the brief using the Review project brief button before research, bundle planning or document writes.",
                    tool_call_id=call["id"],
                )
        return await handler(request)


class SecurityCoverageFeedback(AgentMiddleware):
    """Make cross-document gaps visible after an approved security/QA write."""

    async def awrap_tool_call(self, request, handler):
        result = await handler(request)
        directory = PROJECT_DIRECTORY.get()
        call = request.tool_call
        path = str(call.get("args", {}).get("file_path", "")).replace("\\", "/")
        if (
            directory
            and call["name"] in ("write_file", "edit_file")
            and path
            in (
                "/docs/security-blueprint.md",
                "/docs/qa-test-plan.md",
                "docs/security-blueprint.md",
                "docs/qa-test-plan.md",
            )
            and isinstance(result, ToolMessage)
            and result.status != "error"
        ):
            from ..quality import documents, security_coverage

            coverage = security_coverage(documents(directory.name))
            missing = [row["control_id"] for row in coverage if not row["mapped"]]
            feedback = "\n\nCurrent saved security-to-QA preflight: "
            if missing:
                feedback += (
                    "Unmapped controls: "
                    + ", ".join(missing)
                    + ". Keep bundle work incomplete; read the current security blueprint and QA plan, then propose missing TC cases or explicit links through normal document approval."
                )
            elif coverage:
                feedback += "All security controls link to defined QA cases. This establishes ID traceability only, not test adequacy or execution. Independent review is still required."
            else:
                feedback += "No security control definitions found. Add stable SEC- IDs before claiming complete coverage."
            content = (
                result.content + feedback
                if isinstance(result.content, str)
                else [*result.content, {"type": "text", "text": feedback}]
            )
            result = result.model_copy(update={"content": content})
        return result
