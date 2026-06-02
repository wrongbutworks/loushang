from __future__ import annotations

from pathlib import Path

from loushang.coding.domain.types import CodingDomainPreparedTurn, CodingDomainRequest
from loushang.method import (
    MethodCompiler,
    MethodContext,
    MethodLoader,
    MethodProjector,
    MethodSelector,
)
from loushang.method.types import MethodDescriptor, MethodProjection

DEFAULT_GUIDANCE_TEMPLATE = "{guidance}\n\nUser request:\n\n{user_input}"


class CodingDomainApp:
    def __init__(
        self,
        *,
        cwd: Path | None = None,
        method_loader: MethodLoader | None = None,
        method_compiler: MethodCompiler | None = None,
        method_projector: MethodProjector | None = None,
    ) -> None:
        self._cwd = cwd
        self._method_loader = method_loader or MethodLoader()
        self._method_compiler = method_compiler or MethodCompiler()
        self._method_projector = method_projector or MethodProjector()

    def prepare_turn(self, request: CodingDomainRequest) -> CodingDomainPreparedTurn:
        method_name = request.method.strip() if request.method is not None else None
        if not method_name:
            return CodingDomainPreparedTurn(prepared_prompt=request.user_input)

        cwd = request.cwd or self._cwd or Path.cwd()
        methods = self._method_loader.discover_methods(cwd)
        descriptor = MethodSelector(methods).select(method_name)
        if descriptor is None:
            raise ValueError(f"method not found: {method_name}")

        context = MethodContext(domain="coding", metadata=request.metadata)
        plan = self._method_compiler.compile(descriptor, context=context)
        step = plan.steps[0]
        projection = self._method_projector.project(plan, step, context=context)
        if not _has_meaningful_guidance(descriptor, projection):
            return CodingDomainPreparedTurn(
                prepared_prompt=request.user_input,
                method_id=descriptor.id,
            )

        guidance = projection.system_guidance
        return CodingDomainPreparedTurn(
            prepared_prompt=DEFAULT_GUIDANCE_TEMPLATE.format(
                guidance=guidance,
                user_input=request.user_input,
            ),
            method_id=projection.method_id,
            method_guidance=guidance,
            metadata={
                "meta_role": projection.meta_role,
                "role_variant": projection.role_variant,
                "temperature": projection.temperature,
            },
        )


def _has_meaningful_guidance(descriptor: MethodDescriptor, projection: MethodProjection) -> bool:
    return bool(descriptor.content.strip() and projection.system_guidance.strip())


__all__ = [
    "CodingDomainApp",
    "DEFAULT_GUIDANCE_TEMPLATE",
]
