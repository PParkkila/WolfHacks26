"""Which tools each role gets. Adding a tool group is one line here."""

from agents import FunctionTool

from agent.query import QueryService
from agent.tools import clinician, patient


def build_tools(svc: QueryService) -> list[FunctionTool]:
    """The tools for the service's user, bound to that user's scope."""
    if svc.principal.role == "clinician":
        return clinician.build(svc)
    return patient.build(svc)
