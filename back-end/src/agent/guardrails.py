"""Input guardrails: one request classifier per role.

A small classifier agent runs before the main agent. The prompt rules stay as the
second layer, and for patients the tools themselves are the hard boundary (they
cannot reach anyone else's data). The API layer turns a tripped guardrail into a
normal short reply (not an `error` event) using `decline_message`.
"""

import logging
from dataclasses import dataclass
from typing import Literal

from agents import (
    Agent,
    GuardrailFunctionOutput,
    InputGuardrail,
    InputGuardrailTripwireTriggered,
    RunContextWrapper,
    Runner,
    TResponseInputItem,
    input_guardrail,
)
from pydantic import BaseModel

from agent.auth import Role

log = logging.getLogger(__name__)

Category = Literal["diagnosis", "treatment", "identification", "other_people", "none"]


@dataclass(frozen=True)
class RolePolicy:
    instructions: str
    declines: dict[str, str]  # category -> reply; any category listed here blocks
    fallback: str  # the category used for an unrecognised verdict


CLINICIAN = RolePolicy(
    instructions="""\
Classify a clinician's message to a wearable-sensor screening tool.
- diagnosis: asks whether someone has / is diagnosed with a disease.
- treatment: asks what someone should take or be prescribed (drugs, dosing, diets).
- identification: asks who a participant really is (name, address, contact).
- none: anything else, including rankings, comparisons, trends, why a score changed,
  and who needs follow-up.
Answer with the single best category.""",
    declines={
        "diagnosis": (
            "I can't diagnose anyone. I can show each participant's Gluco Score, "
            "how it has changed and which wearable signals moved with it, to help "
            "decide who needs follow-up testing."
        ),
        "treatment": (
            "I can't recommend treatment or medication. I can show what the data "
            "suggests and who may need a clinical follow-up."
        ),
        "identification": (
            "I only work with de-identified participant ids and can't identify "
            "anyone. I can show their Gluco Score, trends and how they compare "
            "with the cohort."
        ),
    },
    fallback="diagnosis",
)

PATIENT = RolePolicy(
    instructions="""\
Classify a message a person sent to the assistant in their own wearable-health app.
- diagnosis: asks whether they (or anyone) have a disease or condition, e.g. "do I
  have diabetes?".
- treatment: asks which medication, supplement, dose, or specific diet or meal
  plan to take.
- other_people: asks about another person's data, or how they compare with other
  people, other participants or the average person.
- none: anything else, including their own scores, trends, why something changed,
  and general everyday wellness ideas ("how can I improve my score?", "should I
  walk more?").
Answer with the single best category.""",
    declines={
        "diagnosis": (
            "I can't tell whether you have a medical condition. Your Gluco Score is "
            "an estimate from your wearable, not a diagnosis, and your care team can "
            "arrange proper tests. I'm happy to walk you through what your data shows."
        ),
        "treatment": (
            "I can't recommend medication, supplements or specific diets; your care "
            "team is the right place for that. I can share general everyday ideas "
            "linked to your data, like movement or routine."
        ),
        "other_people": (
            "I can only see your own data, so I can't tell you about other people or "
            "compare you with them. I can compare you with your own earlier days, "
            "though."
        ),
    },
    fallback="diagnosis",
)

POLICIES: dict[Role, RolePolicy] = {"clinician": CLINICIAN, "patient": PATIENT}


class GuardrailVerdict(BaseModel):
    category: Category


def decline_message(tripwire: InputGuardrailTripwireTriggered, role: Role) -> str:
    """The reply for a tripped guardrail.

    An unrecognised verdict declines with the role's most conservative reply,
    and says so in the log rather than hiding it.
    """
    policy = POLICIES[role]
    info = tripwire.guardrail_result.output.output_info
    if isinstance(info, GuardrailVerdict) and info.category in policy.declines:
        return policy.declines[info.category]
    log.warning("guardrail tripped without a known verdict: %r", info)
    return policy.declines[policy.fallback]


def build_input_guardrails(model: str, role: Role) -> list[InputGuardrail]:
    policy = POLICIES[role]
    classifier = Agent(
        name=f"{role}_request_classifier",
        instructions=policy.instructions,
        model=model,
        output_type=GuardrailVerdict,
    )

    # Blocking (not parallel) so a blocked request never streams a partial answer.
    @input_guardrail(run_in_parallel=False)
    async def block_out_of_scope_requests(
        ctx: RunContextWrapper[None],
        agent: Agent,
        user_input: str | list[TResponseInputItem],
    ) -> GuardrailFunctionOutput:
        run = await Runner.run(classifier, user_input, context=ctx.context)
        verdict: GuardrailVerdict = run.final_output
        return GuardrailFunctionOutput(
            output_info=verdict, tripwire_triggered=verdict.category in policy.declines
        )

    return [block_out_of_scope_requests]
