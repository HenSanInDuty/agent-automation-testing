"""Generation reuses qualified CLI isolation and bounded subprocess ownership."""

from agents.prompts.codex_generation import build_prompt
from auto_at.contracts.generation import GeneratedTestPlannerOutput, VisionGroundedPlannerOutput

from infrastructure.codex_bridge.catalogue import GENERATION_INSTRUCTIONS_PATH
from infrastructure.codex_bridge.process import command


class GenerationProcess:
    def __init__(self, process):
        self.process = process

    async def run(self, request, directory, payload, stop):
        output_type = (VisionGroundedPlannerOutput if request.kind == "vision"
                       else GeneratedTestPlannerOutput)
        return await self.process.run(
            request, directory, build_prompt(request.kind, payload.decode()), stop,
            argv=command(self.process.executable, directory, request,
                         instructions_path=GENERATION_INSTRUCTIONS_PATH),
            output_parser=output_type.model_validate_json,
        )
