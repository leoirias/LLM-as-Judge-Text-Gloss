from __future__ import annotations

import re
from string import Template
from typing import Any

from models.base import PromptConfig


INLINE_PATTERN = re.compile(r"@\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class PromptRenderError(ValueError):
    pass


def build_judge_prompt(prompt_config: PromptConfig, text: str, gloss: str) -> str:
    return render_prompt_template(
        prompt_config,
        variables={
            "text": text,
            "gloss": gloss,
        },
    )


def render_prompt_template(prompt_config: PromptConfig, variables: dict[str, Any]) -> str:
    fragments = _prompt_fragments(prompt_config)
    template = _inline_fragments(prompt_config.template, fragments)
    return _render_variables(template, variables).strip()


def _prompt_fragments(prompt_config: PromptConfig) -> dict[str, str]:
    fragments = {
        "objective": prompt_config.objective,
        "instructions": prompt_config.instructions,
        "output_rules": prompt_config.output_rules,
        "template": prompt_config.template,
    }

    for key, value in prompt_config.extra.items():
        if isinstance(value, str):
            fragments[key] = value

    return fragments


def _inline_fragments(template: str, fragments: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)

        if key not in fragments:
            raise PromptRenderError(f"Unknown prompt fragment: {key!r}")

        return fragments[key].strip()

    return INLINE_PATTERN.sub(replace, template)


def _render_variables(template: str, variables: dict[str, Any]) -> str:
    normalized_template = VARIABLE_PATTERN.sub(lambda match: f"${match.group(1)}", template)
    normalized_variables = {key: "" if value is None else str(value) for key, value in variables.items()}

    try:
        return Template(normalized_template).substitute(normalized_variables)
    except KeyError as exc:
        missing_key = exc.args[0]
        raise PromptRenderError(f"Missing prompt variable: {missing_key!r}") from exc
