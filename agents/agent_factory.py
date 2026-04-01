#!/usr/bin/env python3
"""
AgentFactory — creates and caches ProjectAgent instances.
One agent per channel, keyed by channel_id. Agents are pre-warmed at startup
so the first message to a channel incurs no creation overhead.
"""

import logging
from .project_agent import ProjectAgent

logger = logging.getLogger(__name__)


class AgentFactory:
    def __init__(self, client):
        self.client = client
        self._agents: dict[str, "ProjectAgent"] = {}

    def warmup_all(self, projects: dict, channel_routing: dict, app) -> None:
        """Pre-create one agent per dedicated channel at startup."""
        for channel_name, routing in channel_routing.items():
            if routing.get("mode") != "dedicated":
                continue
            channel_id = routing.get("channel_id", "")
            if not channel_id:
                continue
            project_key = routing.get("project")
            project = projects.get(project_key)
            if not project or not project_key:
                continue
            if channel_id not in self._agents:
                self._agents[channel_id] = ProjectAgent(
                    project_key, project, self.client, app, channel_id, ""
                )
                logger.info(f"Warmed up agent for {project['name']} ({channel_name})")

    def get_agent(self, project_key: str, project_config: dict,
                  app, channel_id: str, thread_ts: str) -> "ProjectAgent":
        """Return the channel's agent, creating it if not yet warmed up."""
        if channel_id not in self._agents:
            self._agents[channel_id] = ProjectAgent(
                project_key, project_config, self.client,
                app, channel_id, thread_ts
            )
        # Update thread context for this request
        self._agents[channel_id].channel_id = channel_id
        self._agents[channel_id].thread_ts = thread_ts
        return self._agents[channel_id]

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())
