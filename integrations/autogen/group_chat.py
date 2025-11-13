# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
ATP AutoGen Group Chat Integration
This module provides group chat functionality with ATP-backed agents.
"""

import logging
import random
from typing import Any

try:
    from autogen import GroupChat, GroupChatManager
except ImportError:
    raise ImportError("AutoGen is required for ATP AutoGen integration. Install it with: pip install pyautogen") from None

from .atp_agent import ATPAutoGenAgent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ATPGroupChat(GroupChat):
    """Enhanced GroupChat with ATP-specific features."""

    def __init__(
        self,
        agents: list[ATPAutoGenAgent],
        messages: list[dict] | None = None,
        max_round: int = 10,
        admin_name: str = "Admin",
        func_call_filter: bool = True,
        speaker_selection_method: str = "auto",
        allow_repeat_speaker: bool = True,
        **kwargs,
    ):
        """
        Initialize ATP Group Chat.

        Args:
            agents: List of ATP agents
            messages: Initial messages
            max_round: Maximum number of conversation rounds
            admin_name: Name of the admin/moderator
            func_call_filter: Whether to filter function calls
            speaker_selection_method: Method for selecting next speaker
            allow_repeat_speaker: Whether to allow the same speaker consecutively
            **kwargs: Additional arguments
        """
        super().__init__(
            agents=agents,
            messages=messages or [],
            max_round=max_round,
            admin_name=admin_name,
            func_call_filter=func_call_filter,
            **kwargs,
        )

        self.speaker_selection_method = speaker_selection_method
        self.allow_repeat_speaker = allow_repeat_speaker
        self._conversation_history = []
        self._speaker_stats = {agent.name: 0 for agent in agents}

        # Custom speaker selection functions
        self._selection_methods = {
            "auto": self._auto_select_speaker,
            "round_robin": self._round_robin_select_speaker,
            "random": self._random_select_speaker,
            "expertise_based": self._expertise_based_select_speaker,
            "load_balanced": self._load_balanced_select_speaker,
        }

    def _auto_select_speaker(self, last_speaker: ATPAutoGenAgent, selector: ATPAutoGenAgent) -> ATPAutoGenAgent:
        """Automatically select next speaker based on context."""
        if not self.messages:
            return self.agents[0]

        last_message = self.messages[-1].get("content", "").lower()

        # Keyword-based selection
        for agent in self.agents:
            if agent == last_speaker and not self.allow_repeat_speaker:
                continue

            agent_name_lower = agent.name.lower()

            # Check if agent is mentioned by name
            if agent_name_lower in last_message:
                return agent

            # Check for role-based keywords
            if "code" in last_message or "programming" in last_message:
                if "code" in agent_name_lower or "developer" in agent_name_lower:
                    return agent

            if "data" in last_message or "analysis" in last_message:
                if "data" in agent_name_lower or "analyst" in agent_name_lower:
                    return agent

            if "review" in last_message:
                if "review" in agent_name_lower:
                    return agent

        # Fallback to next agent in list
        current_index = self.agents.index(last_speaker)
        next_index = (current_index + 1) % len(self.agents)
        return self.agents[next_index]

    def _round_robin_select_speaker(self, last_speaker: ATPAutoGenAgent, selector: ATPAutoGenAgent) -> ATPAutoGenAgent:
        """Select next speaker in round-robin fashion."""
        current_index = self.agents.index(last_speaker)
        next_index = (current_index + 1) % len(self.agents)
        return self.agents[next_index]

    def _random_select_speaker(self, last_speaker: ATPAutoGenAgent, selector: ATPAutoGenAgent) -> ATPAutoGenAgent:
        """Randomly select next speaker."""
        available_agents = self.agents.copy()
        if not self.allow_repeat_speaker and last_speaker in available_agents:
            available_agents.remove(last_speaker)

        return random.choice(available_agents) if available_agents else last_speaker

    def _expertise_based_select_speaker(
        self, last_speaker: ATPAutoGenAgent, selector: ATPAutoGenAgent
    ) -> ATPAutoGenAgent:
        """Select speaker based on expertise matching."""
        if not self.messages:
            return self.agents[0]

        last_message = self.messages[-1].get("content", "").lower()

        # Define expertise keywords for different agent types
        expertise_map = {
            "code": ["code", "programming", "development", "bug", "function", "class"],
            "data": ["data", "analysis", "statistics", "chart", "visualization", "dataset"],
            "review": ["review", "feedback", "quality", "improvement", "suggestion"],
            "general": ["help", "question", "explain", "what", "how", "why"],
        }

        # Score agents based on expertise match
        agent_scores = {}
        for agent in self.agents:
            if agent == last_speaker and not self.allow_repeat_speaker:
                continue

            score = 0
            agent_name_lower = agent.name.lower()

            for expertise, keywords in expertise_map.items():
                if expertise in agent_name_lower:
                    for keyword in keywords:
                        if keyword in last_message:
                            score += 1

            agent_scores[agent] = score

        # Select agent with highest score
        if agent_scores:
            best_agent = max(agent_scores, key=agent_scores.get)
            if agent_scores[best_agent] > 0:
                return best_agent

        # Fallback to auto selection
        return self._auto_select_speaker(last_speaker, selector)

    def _load_balanced_select_speaker(
        self, last_speaker: ATPAutoGenAgent, selector: ATPAutoGenAgent
    ) -> ATPAutoGenAgent:
        """Select speaker to balance conversation load."""
        # Find agent with least participation
        min_count = min(self._speaker_stats.values())
        candidates = [agent for agent in self.agents if self._speaker_stats[agent.name] == min_count]

        # Remove last speaker if not allowing repeats
        if not self.allow_repeat_speaker and last_speaker in candidates:
            candidates.remove(last_speaker)

        if not candidates:
            candidates = [agent for agent in self.agents if agent != last_speaker]

        return random.choice(candidates) if candidates else last_speaker

    def select_speaker(self, last_speaker: ATPAutoGenAgent, selector: ATPAutoGenAgent) -> ATPAutoGenAgent:
        """Select the next speaker using configured method."""
        selection_func = self._selection_methods.get(self.speaker_selection_method, self._auto_select_speaker)

        next_speaker = selection_func(last_speaker, selector)

        # Update speaker statistics
        self._speaker_stats[next_speaker.name] += 1

        logger.info(f"Selected next speaker: {next_speaker.name}")
        return next_speaker

    def add_agent(self, agent: ATPAutoGenAgent):
        """Add an agent to the group chat."""
        if agent not in self.agents:
            self.agents.append(agent)
            self._speaker_stats[agent.name] = 0
            logger.info(f"Added agent {agent.name} to group chat")

    def remove_agent(self, agent: ATPAutoGenAgent):
        """Remove an agent from the group chat."""
        if agent in self.agents:
            self.agents.remove(agent)
            if agent.name in self._speaker_stats:
                del self._speaker_stats[agent.name]
            logger.info(f"Removed agent {agent.name} from group chat")

    def get_conversation_summary(self) -> dict[str, Any]:
        """Get a summary of the conversation."""
        total_messages = len(self.messages)

        # Count messages by speaker
        speaker_message_count = {}
        for message in self.messages:
            speaker = message.get("name", "Unknown")
            speaker_message_count[speaker] = speaker_message_count.get(speaker, 0) + 1

        # Calculate conversation metrics
        avg_message_length = 0
        if self.messages:
            total_length = sum(len(msg.get("content", "")) for msg in self.messages)
            avg_message_length = total_length / total_messages

        return {
            "total_messages": total_messages,
            "total_agents": len(self.agents),
            "speaker_message_count": speaker_message_count,
            "speaker_stats": self._speaker_stats.copy(),
            "avg_message_length": round(avg_message_length, 2),
            "conversation_rounds": total_messages // len(self.agents) if self.agents else 0,
        }

    def export_conversation(self, format_type: str = "json") -> str | dict:
        """Export conversation in different formats."""
        if format_type == "json":
            return {
                "agents": [agent.get_agent_info() for agent in self.agents],
                "messages": self.messages,
                "summary": self.get_conversation_summary(),
            }
        elif format_type == "markdown":
            md_content = "# Group Chat Conversation\n\n"

            # Add agent information
            md_content += "## Participants\n\n"
            for agent in self.agents:
                md_content += f"- **{agent.name}**: {agent.system_message or 'No description'}\n"

            md_content += "\n## Conversation\n\n"

            # Add messages
            for i, message in enumerate(self.messages, 1):
                speaker = message.get("name", "Unknown")
                content = message.get("content", "")
                md_content += f"### Message {i} - {speaker}\n\n{content}\n\n"

            return md_content
        elif format_type == "text":
            text_content = "Group Chat Conversation\n" + "=" * 50 + "\n\n"

            for message in self.messages:
                speaker = message.get("name", "Unknown")
                content = message.get("content", "")
                text_content += f"{speaker}: {content}\n\n"

            return text_content
        else:
            raise ValueError(f"Unsupported format: {format_type}")


class ATPGroupChatManager(GroupChatManager):
    """Enhanced GroupChatManager with ATP-specific features."""

    def __init__(
        self,
        groupchat: ATPGroupChat,
        name: str = "GroupChatManager",
        atp_base_url: str = "http://localhost:8000",
        atp_api_key: str | None = None,
        **kwargs,
    ):
        """
        Initialize ATP Group Chat Manager.

        Args:
            groupchat: ATPGroupChat instance
            name: Manager name
            atp_base_url: ATP API base URL
            atp_api_key: ATP API key
            **kwargs: Additional arguments
        """
        self.atp_base_url = atp_base_url
        self.atp_api_key = atp_api_key

        # Configure LLM for the manager
        llm_config = {
            "config_list": [
                {"model": "gpt-4", "api_key": atp_api_key or "dummy", "base_url": atp_base_url, "api_type": "atp"}
            ],
            "temperature": 0.3,  # Lower temperature for more consistent management
        }

        super().__init__(groupchat=groupchat, name=name, llm_config=llm_config, **kwargs)

        self._conversation_metrics = {
            "total_rounds": 0,
            "successful_completions": 0,
            "errors": 0,
            "average_response_time": 0.0,
        }

    def initiate_chat(self, recipient: ATPAutoGenAgent, message: dict | str | None = None, **kwargs) -> dict[str, Any]:
        """Initiate group chat with enhanced monitoring."""
        import time

        start_time = time.time()

        try:
            # Call parent initiate_chat
            result = super().initiate_chat(recipient, message, **kwargs)

            # Update metrics
            self._conversation_metrics["total_rounds"] += 1
            self._conversation_metrics["successful_completions"] += 1

            end_time = time.time()
            response_time = end_time - start_time

            # Update average response time
            total_rounds = self._conversation_metrics["total_rounds"]
            current_avg = self._conversation_metrics["average_response_time"]
            new_avg = ((current_avg * (total_rounds - 1)) + response_time) / total_rounds
            self._conversation_metrics["average_response_time"] = new_avg

            logger.info(f"Group chat completed in {response_time:.2f} seconds")

            return result

        except Exception as e:
            self._conversation_metrics["errors"] += 1
            logger.error(f"Group chat error: {e}")
            raise

    def get_manager_metrics(self) -> dict[str, Any]:
        """Get group chat manager metrics."""
        return {
            "conversation_metrics": self._conversation_metrics.copy(),
            "group_chat_summary": self.groupchat.get_conversation_summary(),
            "active_agents": len(self.groupchat.agents),
            "total_messages": len(self.groupchat.messages),
        }

    def reset_conversation(self):
        """Reset the group chat conversation."""
        self.groupchat.messages = []
        self.groupchat._speaker_stats = {agent.name: 0 for agent in self.groupchat.agents}
        logger.info("Reset group chat conversation")

    def add_moderator_message(self, message: str):
        """Add a moderator message to the conversation."""
        moderator_msg = {"role": "assistant", "content": f"[MODERATOR] {message}", "name": self.name}
        self.groupchat.messages.append(moderator_msg)
        logger.info(f"Added moderator message: {message}")

    def set_conversation_rules(self, rules: list[str]):
        """Set conversation rules for the group chat."""
        rules_message = "Conversation Rules:\n" + "\n".join(f"- {rule}" for rule in rules)
        self.add_moderator_message(rules_message)

    def enforce_turn_limit(self, agent_name: str, max_turns: int):
        """Enforce turn limits for specific agents."""
        current_turns = self.groupchat._speaker_stats.get(agent_name, 0)
        if current_turns >= max_turns:
            self.add_moderator_message(
                f"{agent_name} has reached the maximum turn limit ({max_turns}). "
                "Other agents should continue the conversation."
            )
            return False
        return True


# Factory functions
def create_atp_group_chat(
    agents: list[ATPAutoGenAgent], max_round: int = 10, speaker_selection_method: str = "auto", **kwargs
) -> ATPGroupChat:
    """
    Factory function to create ATP Group Chat.

    Args:
        agents: List of ATP agents
        max_round: Maximum conversation rounds
        speaker_selection_method: Speaker selection method
        **kwargs: Additional arguments

    Returns:
        ATPGroupChat instance
    """
    return ATPGroupChat(agents=agents, max_round=max_round, speaker_selection_method=speaker_selection_method, **kwargs)


def create_atp_group_chat_manager(
    groupchat: ATPGroupChat, atp_base_url: str = "http://localhost:8000", atp_api_key: str | None = None, **kwargs
) -> ATPGroupChatManager:
    """
    Factory function to create ATP Group Chat Manager.

    Args:
        groupchat: ATPGroupChat instance
        atp_base_url: ATP API base URL
        atp_api_key: ATP API key
        **kwargs: Additional arguments

    Returns:
        ATPGroupChatManager instance
    """
    return ATPGroupChatManager(groupchat=groupchat, atp_base_url=atp_base_url, atp_api_key=atp_api_key, **kwargs)
