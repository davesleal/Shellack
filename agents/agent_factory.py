#!/usr/bin/env python3
"""
AgentFactory — singleton that creates and caches ProjectAgent instances.
One agent per thread, keyed by thread_ts.
"""

from anthropic import Anthropic
from .project_agent import ProjectAgent


class AgentFactory:
    def __init__(self, client):
        self.client = client
        self._agents: dict[str, "ProjectAgent"] = {}

    def get_agent(self, project_key: str, project_config: dict,
                  app, channel_id: str, thread_ts: str) -> "ProjectAgent":
        """One agent per thread — keyed by thread_ts."""
        if thread_ts not in self._agents:
            self._agents[thread_ts] = ProjectAgent(
                project_key, project_config, self.client,
                app, channel_id, thread_ts
            )
            print(f"🤖 Created {project_config['name']} agent for thread {thread_ts}")
        return self._agents[thread_ts]

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())
