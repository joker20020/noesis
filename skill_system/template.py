"""SKILL.md template generator with stage-specific content."""

SKILL_MD_TEMPLATE = """---
name: {name}
description: {description}
category: {category}
stage: "{stage}"
version: {version}
---

# {title}

## Overview
{overview}

## When to Use
- {when_to_use}

## Core Pattern

### Prerequisites
- {prerequisites}

### Steps
{steps}

## Quick Reference

| Step | Tool | Key Parameters |
|------|------|---------------|
{quick_ref}

## Common Mistakes
- {mistakes}
"""


def generate_skill_md(
    name: str,
    description: str,
    category: str,
    stage: str = "NL",
    version: int = 1,
    scripts: list[str] | None = None,
) -> str:
    title = name.replace("-", " ").title()

    if stage == "NL":
        overview = f"Explore and accomplish tasks related to {title}."
        when = f"When the user needs to work with {title}"
        prereq = "(to be determined through execution)"
        steps = "1. (to be determined through execution)"
        mistakes = "(to be learned through execution)"
        quick = "| (pending) | (pending) | (pending) |"
    elif stage == "SOP":
        overview = f"Standardized workflow for {title}."
        when = f"When the user needs to work with {title}"
        prereq = "(documented from execution)"
        steps = "(documented from execution)"
        mistakes = "(documented from execution)"
        quick = "| (pending) | (pending) | (pending) |"
    else:
        overview = f"Execute {title} tasks via pre-built scripts."
        when = f"When the user needs to work with {title}"
        prereq = "Scripts are in scripts/ directory"
        script_list = "\n".join(f"- `{s}`" for s in (scripts or []))
        steps = f"Run via code_run:\n{script_list or '(none)'}"
        mistakes = "- API tokens must be configured in environment variables"
        quick = "\n".join(f"| {s} | code_run | -- |" for s in (scripts or ["(none)"]))

    return SKILL_MD_TEMPLATE.format(
        name=name, description=description, category=category,
        stage=stage, version=version, title=title,
        overview=overview, when_to_use=when,
        prerequisites=prereq, steps=steps,
        quick_ref=quick, mistakes=mistakes,
    )
