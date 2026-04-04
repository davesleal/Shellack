"""
VisualUX persona — WCAG AA and UX laws auditor.

Fires on moderate/complex BUT only if architect.files_affected contains
UI file extensions (.tsx, .jsx, .vue, .svelte, .swift, .css, .html).
A "blocker" verdict is absolute — WCAG AA failures cannot ship.
"""

from __future__ import annotations

from tools.personas import Persona

_UI_EXTENSIONS = frozenset({".tsx", ".jsx", ".vue", ".svelte", ".swift", ".css", ".html"})


class VisualUX(Persona):
    name = "visual_ux"
    emoji = "\U0001f3a8"
    model = "sonnet"
    reads = ["architect"]
    max_tokens = 768
    system_prompt = """\
You are a WCAG AA accessibility and UX expert. Given an architectural proposal and list of
affected UI files, audit for accessibility violations and UX law breaches.

Rules:
- a11y_issues: WCAG AA violations (contrast, keyboard nav, ARIA, focus management, screen reader support).
- ux_issues: UX law violations (Fitts's Law, Hick's Law, cognitive load, progressive disclosure).
- Each a11y issue: element (component or element), violation (specific WCAG criterion), fix (concrete fix).
- Each UX issue: element, violation, fix.
- verdict: "accessible" if fully WCAG AA compliant, "fixable" if issues exist but are addressable,
  "blocker" if critical WCAG AA failures that cannot ship.
- A "blocker" verdict is absolute — WCAG AA failures must be resolved before release.

Respond ONLY with valid JSON in this exact shape:
{
  "a11y_issues": [
    {"element": "component name", "violation": "WCAG criterion", "fix": "concrete fix"}
  ],
  "ux_issues": [
    {"element": "component name", "violation": "UX law", "fix": "concrete fix"}
  ],
  "verdict": "accessible" | "fixable" | "blocker"
}"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        if complexity not in ("moderate", "complex"):
            return False
        architect = turn_context.get("architect", {})
        files = architect.get("files_affected", [])
        return any(
            any(f.endswith(ext) for ext in _UI_EXTENSIONS)
            for f in files
        )

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        parts = []
        architect = inputs.get("architect", {})
        if architect.get("proposal"):
            parts.append(f"## Architectural Proposal\n{architect['proposal']}")
        if architect.get("files_affected"):
            ui_files = [
                f for f in architect["files_affected"]
                if any(f.endswith(ext) for ext in _UI_EXTENSIONS)
            ]
            if ui_files:
                files_text = "\n".join(f"- {f}" for f in ui_files)
                parts.append(f"## UI Files Affected\n{files_text}")
        return "\n\n".join(parts) if parts else "No context available."
