#!/usr/bin/env python3
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
ATP Python SDK Setup
"""

import os

from setuptools import find_packages, setup

# Read the README file
with open("README.md", encoding="utf-8") as fh:
    long_description = fh.read()

# Read requirements
with open("requirements.txt", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

# Read version
version = "1.0.0"
if os.path.exists("atp_sdk/__init__.py"):
    with open("atp_sdk/__init__.py") as f:
        for line in f:
            if line.startswith("__version__"):
                version = line.split("=")[1].strip().strip('"').strip("'")
                break

setup(
    name="atp-sdk",
    version=version,
    author="ATP Project Contributors",
    author_email="support@atp.company.com",
    description="Official Python SDK for the ATP (AI Traffic Platform)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/atp-project/atp-main/tree/main/sdks/python",
    project_urls={
        "Bug Tracker": "https://github.com/atp-project/atp-main/issues",
        "Documentation": "https://docs.atp.company.com/sdk/python",
        "Source Code": "https://github.com/atp-project/atp-main/tree/main/sdks/python",
    },
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "isort>=5.12.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
            "pre-commit>=3.0.0",
        ],
        "docs": [
            "sphinx>=6.0.0",
            "sphinx-rtd-theme>=1.2.0",
            "sphinx-autodoc-typehints>=1.22.0",
        ],
        "examples": [
            "jupyter>=1.0.0",
            "matplotlib>=3.6.0",
            "pandas>=1.5.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "atp=atp_sdk.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "atp_sdk": ["py.typed"],
    },
    zip_safe=False,
    keywords="ai, artificial intelligence, machine learning, api, sdk, atp, routing, llm",
)
