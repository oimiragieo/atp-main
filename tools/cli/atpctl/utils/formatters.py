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

"""Output formatters for atpctl CLI"""

import json
from typing import Any

import yaml
from rich import print as rprint


def format_output(data: Any, output_format: str = "table") -> None:
    """Format and print output data.

    Args:
        data: Data to format and print
        output_format: Output format (json, yaml, table)
    """
    if output_format == "json":
        rprint(json.dumps(data, indent=2))
    elif output_format == "yaml":
        rprint(yaml.dump(data, default_flow_style=False))
    else:
        # Default to JSON for complex structures
        rprint(json.dumps(data, indent=2))
