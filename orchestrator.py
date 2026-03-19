#!/usr/bin/env python3
"""
SlackClaw Orchestrator - Multi-project coordinator
Handles cross-project operations and governance
"""

import os
from pathlib import Path
from typing import Dict, List
from orchestrator_config import (
    get_all_projects,
    is_orchestrator_channel,
    GLOBAL_STANDARDS,
)


class Orchestrator:
    """Manages cross-project coordination"""

    def update_all_claude_md(self, rule: str) -> Dict[str, bool]:
        """
        Update CLAUDE.md files across all projects with a new rule

        Args:
            rule: The rule to add to all CLAUDE.md files

        Returns:
            Dict of project_name -> success status
        """
        results = {}
        projects = get_all_projects()

        for project in projects:
            project_path = Path(project["path"])
            claude_md = project_path / "CLAUDE.md"

            try:
                # Read existing CLAUDE.md
                if claude_md.exists():
                    content = claude_md.read_text()
                else:
                    content = f"# {project['name']}\n\n"

                # Add rule to conventions section
                if "## Code Conventions" not in content:
                    content += "\n## Code Conventions\n\n"

                content += f"- {rule}\n"

                # Write back
                claude_md.write_text(content)
                results[project["name"]] = True

            except Exception as e:
                print(f"Error updating {project['name']}: {e}")
                results[project["name"]] = False

        return results

    def sync_standards(self, source_project: str, target_project: str) -> bool:
        """
        Sync coding standards from one project to another

        Args:
            source_project: Project to copy standards from
            target_project: Project to copy standards to

        Returns:
            Success status
        """
        projects = {p["name"].lower(): p for p in get_all_projects()}

        source = projects.get(source_project.lower())
        target = projects.get(target_project.lower())

        if not source or not target:
            return False

        try:
            source_claude_md = Path(source["path"]) / "CLAUDE.md"
            target_claude_md = Path(target["path"]) / "CLAUDE.md"

            if not source_claude_md.exists():
                return False

            # Read source conventions
            source_content = source_claude_md.read_text()

            # Extract conventions section
            if "## Code Conventions" in source_content:
                start = source_content.index("## Code Conventions")
                end = source_content.find("\n##", start + 1)
                conventions = source_content[start : end if end != -1 else None]

                # Add to target
                if target_claude_md.exists():
                    target_content = target_claude_md.read_text()
                else:
                    target_content = f"# {target['name']}\n\n"

                # Replace or append conventions
                if "## Code Conventions" in target_content:
                    # Replace existing
                    t_start = target_content.index("## Code Conventions")
                    t_end = target_content.find("\n##", t_start + 1)
                    target_content = (
                        target_content[:t_start]
                        + conventions
                        + (target_content[t_end:] if t_end != -1 else "")
                    )
                else:
                    # Append
                    target_content += "\n" + conventions

                target_claude_md.write_text(target_content)
                return True

        except Exception as e:
            print(f"Error syncing standards: {e}")
            return False

        return False

    def search_all_projects(self, query: str) -> Dict[str, List[str]]:
        """
        Search for a pattern across all projects

        Args:
            query: Search query (string or regex)

        Returns:
            Dict of project_name -> list of matching files
        """
        import subprocess

        results = {}
        projects = get_all_projects()

        for project in projects:
            project_path = Path(project["path"])
            if not project_path.exists():
                continue

            try:
                # Use ripgrep or grep
                cmd = ["rg", "-l", query, str(project_path)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

                if result.returncode == 0:
                    matches = result.stdout.strip().split("\n")
                    results[project["name"]] = matches
                else:
                    results[project["name"]] = []

            except Exception as e:
                print(f"Error searching {project['name']}: {e}")
                results[project["name"]] = []

        return results

    def apply_global_standard(
        self, language: str, standard_key: str
    ) -> Dict[str, bool]:
        """
        Apply a global standard to all projects of a given language

        Args:
            language: Programming language (swift, python, etc.)
            standard_key: Key from GLOBAL_STANDARDS

        Returns:
            Dict of project_name -> success status
        """
        results = {}
        projects = [p for p in get_all_projects() if p["language"] == language]

        standard = GLOBAL_STANDARDS.get(language, {})
        if standard_key not in standard:
            return results

        rule = f"Global {language} standard: {standard[standard_key]}"

        for project in projects:
            try:
                project_path = Path(project["path"])
                claude_md = project_path / "CLAUDE.md"

                content = (
                    claude_md.read_text()
                    if claude_md.exists()
                    else f"# {project['name']}\n\n"
                )

                if "## Global Standards" not in content:
                    content += "\n## Global Standards\n\n"

                content += f"- {rule}\n"

                claude_md.write_text(content)
                results[project["name"]] = True

            except Exception as e:
                print(f"Error applying standard to {project['name']}: {e}")
                results[project["name"]] = False

        return results


# Example usage
if __name__ == "__main__":
    orchestrator = Orchestrator()

    # Test updating all CLAUDE.md files
    print("Updating all CLAUDE.md files...")
    results = orchestrator.update_all_claude_md("Use descriptive variable names")
    for project, success in results.items():
        status = "✅" if success else "❌"
        print(f"{status} {project}")
