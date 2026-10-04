"""Input guardrail: diagnosis, treatment and identification requests.

A small classifier agent runs before the main agent. The prompt rules stay as the
second layer. The API layer turns a tripped guardrail into a normal short reply
(not an `error` event) using `decline_message`.
"""

from typing import Literal

from agents import (
    Agent,
    GuardrailFunctionOutput,
    InputGuardrail,
    RunContextWrapper,
    Runner,
    TResponseInputItem,
    input_guardrail,
)
from pydantic import BaseModel

Category = Literal["diagnosis", "treatment", "identification", "none"]

CLASSIFIER_INSTRUCTIONS = """\
Classify the user's message for a wearable-sensor screening tool.
- diagnosis: asks whether someone has / is diagnosed with a disease.
- treatment: asks what someone should take, do or be prescribed (drugs, diets, dosing).
- identification: asks who a person really is (name, address, contact).
- none: anything else, including why a person is flagged, comparing, ranking, or
  data quality.
Answer with the single best category."""

DECLINE_MESSAGES: dict[str, str] = {
    "diagnosis": (
        "I can't diagnose anyone. What I can say is whether the screening model "
        "flags a person for follow-up testing, how confident it is, and how "
        "reliable their data is."
    ),
    "treatment": (
        "I can't recommend treatment or medication. A flagged person should be "
        "referred for clinical assessment. I can show what the model flags and "
        "how trustworthy the data is."
    ),
    "identification": (
        "I only work with de-identified person ids and can't identify anyone. "
        "I can show their risk label, data quality, and how they compare with "
        "the cohort."
    ),
}


class GuardrailVerdict(BaseModel):
    category: Category


def decline_message(verdict: GuardrailVerdict | object) -> str:
    category = (
        verdict.category if isinstance(verdict, GuardrailVerdict) else "diagnosis"
    )
    return DECLINE_MESSAGES.get(category, DECLINE_MESSAGES["diagnosis"])


def build_input_guardrails(model: str) -> list[InputGuardrail]:
    classifier = Agent(
        name="request_classifier",
        instructions=CLASSIFIER_INSTRUCTIONS,
        model=model,
        output_type=GuardrailVerdict,
    )

    # Blocking (not parallel) so a blocked request never streams a partial answer.
    @input_guardrail(run_in_parallel=False)
    async def block_clinical_requests(
        ctx: RunContextWrapper[None],
        agent: Agent,
        user_input: str | list[TResponseInputItem],
    ) -> GuardrailFunctionOutput:
        run = await Runner.run(classifier, user_input, context=ctx.context)
        verdict: GuardrailVerdict = run.final_output
        return GuardrailFunctionOutput(
            output_info=verdict, tripwire_triggered=verdict.category != "none"
        )

    return [block_clinical_requests]
