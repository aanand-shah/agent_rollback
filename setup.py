"""
Setup script for AgentRollback package.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README if it exists
readme_path = Path(__file__).parent / "README.md"
long_description = ""
if readme_path.exists():
    long_description = readme_path.read_text(encoding="utf-8")

setup(
    name="agent-rollback",
    version="0.1.0",
    author="AgentRollback Team",
    description="AI Agent State Recovery System - Git for AI Agents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/example/agent-rollback",
    packages=find_packages(exclude=["tests", "tests.*", "examples"]),
    include_package_data=True,
    package_data={
        "agent_rollback": ["migrations/*.sql"],
    },
    python_requires=">=3.10",
    install_requires=[
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "pydantic>=2.5.0",
        "click>=8.1.0",
        "rich>=13.0.0",
        "python-dateutil>=2.8.0",
        "aiosqlite>=0.19.0",
        "httpx>=0.25.0",
    ],
    extras_require={
        "redis": ["redis>=5.0.0"],
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "agentrollback=agent_rollback.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Recovery Tools",
    ],
    keywords="ai agent state recovery rollback tracking",
)
