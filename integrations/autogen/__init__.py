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
ATP AutoGen Integration
This package provides AutoGen integration for the ATP platform.
"""

from .atp_agent import ATPAutoGenAgent
from .code_execution import ATPCodeExecutor
from .function_calling import ATPFunctionRegistry
from .group_chat import ATPGroupChat, ATPGroupChatManager

__all__ = ["ATPAutoGenAgent", "ATPGroupChat", "ATPGroupChatManager", "ATPCodeExecutor", "ATPFunctionRegistry"]

__version__ = "1.0.0"
