#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test framework configuration management
Supports YAML config files and environment variables
"""

import os
import yaml
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class APIConfig:
    """API configuration"""
    base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    model_name: str = "autoglm-phone"
    api_key: str = "d7c4df1dde40459d9e4329e6a98043ec.Mn66LyVARk0afi0B"

    def __post_init__(self):
        # Support environment variable override
        if os.getenv("AUTOGLM_API_KEY"):
            self.api_key = os.getenv("AUTOGLM_API_KEY")
        elif os.getenv("PHONE_AGENT_API_KEY"):
            self.api_key = os.getenv("PHONE_AGENT_API_KEY")


@dataclass
class AgentConfig:
    """Agent configuration"""
    max_steps: int = 100
    default_timeout: int = 180
    verbose: bool = True
    lang: str = "cn"


@dataclass
class DeviceConfig:
    """Device configuration"""
    device_id: str
    name: str = ""


@dataclass
class ExecutionConfig:
    """Execution configuration"""
    max_workers: int = 1
    continue_on_failure: bool = False
    retry_on_failure: int = 0
    retry_delay: float = 1.0


@dataclass
class ReportingConfig:
    """Reporting configuration"""
    output_dir: str = "test_reports"
    formats: List[str] = field(default_factory=lambda: ["html", "json"])
    include_screenshots: bool = True
    include_raw_output: bool = False
    raw_output_max_length: int = 1000


@dataclass
class TestFrameworkConfig:
    """Complete test framework configuration"""
    api: APIConfig = field(default_factory=APIConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    devices: List[DeviceConfig] = field(default_factory=list)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    reporting: ReportingConfig = field(default_factory=ReportingConfig)

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "TestFrameworkConfig":
        """Load configuration from YAML file"""
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestFrameworkConfig":
        """Create configuration from dictionary"""
        config = cls()

        # Parse API config
        if "api" in data:
            api_data = data["api"]
            config.api = APIConfig(
                base_url=api_data.get("base_url", config.api.base_url),
                model_name=api_data.get("model_name", config.api.model_name),
                api_key=api_data.get("api_key", config.api.api_key)
            )

        # Parse agent config
        if "agent" in data:
            agent_data = data["agent"]
            config.agent = AgentConfig(
                max_steps=agent_data.get("max_steps", config.agent.max_steps),
                default_timeout=agent_data.get("default_timeout", config.agent.default_timeout),
                verbose=agent_data.get("verbose", config.agent.verbose),
                lang=agent_data.get("lang", config.agent.lang)
            )

        # Parse devices config
        if "devices" in data:
            config.devices = [
                DeviceConfig(device_id=d["device_id"], name=d.get("name", ""))
                for d in data["devices"]
            ]

        # Parse execution config
        if "execution" in data:
            exec_data = data["execution"]
            config.execution = ExecutionConfig(
                max_workers=exec_data.get("max_workers", config.execution.max_workers),
                continue_on_failure=exec_data.get("continue_on_failure", config.execution.continue_on_failure),
                retry_on_failure=exec_data.get("retry_on_failure", config.execution.retry_on_failure),
                retry_delay=exec_data.get("retry_delay", config.execution.retry_delay)
            )

        # Parse reporting config
        if "reporting" in data:
            report_data = data["reporting"]
            config.reporting = ReportingConfig(
                output_dir=report_data.get("output_dir", config.reporting.output_dir),
                formats=report_data.get("formats", config.reporting.formats),
                include_screenshots=report_data.get("include_screenshots", config.reporting.include_screenshots),
                include_raw_output=report_data.get("include_raw_output", config.reporting.include_raw_output),
                raw_output_max_length=report_data.get("raw_output_max_length", config.reporting.raw_output_max_length)
            )

        return config

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            "api": {
                "base_url": self.api.base_url,
                "model_name": self.api.model_name,
                "api_key": "***" if self.api.api_key else self.api.api_key
            },
            "agent": {
                "max_steps": self.agent.max_steps,
                "default_timeout": self.agent.default_timeout,
                "verbose": self.agent.verbose,
                "lang": self.agent.lang
            },
            "devices": [
                {"device_id": d.device_id, "name": d.name}
                for d in self.devices
            ],
            "execution": {
                "max_workers": self.execution.max_workers,
                "continue_on_failure": self.execution.continue_on_failure,
                "retry_on_failure": self.execution.retry_on_failure,
                "retry_delay": self.execution.retry_delay
            },
            "reporting": {
                "output_dir": self.reporting.output_dir,
                "formats": self.reporting.formats,
                "include_screenshots": self.reporting.include_screenshots,
                "include_raw_output": self.reporting.include_raw_output,
                "raw_output_max_length": self.reporting.raw_output_max_length
            }
        }

    def get_device_ids(self) -> List[str]:
        """Get list of all device IDs"""
        return [d.device_id for d in self.devices] if self.devices else []


def load_config(config_path: Optional[str] = None) -> TestFrameworkConfig:
    """
    Load configuration from file or use defaults

    Args:
        config_path: Path to YAML configuration file

    Returns:
        TestFrameworkConfig instance
    """
    if config_path and os.path.exists(config_path):
        return TestFrameworkConfig.from_yaml(config_path)
    else:
        # Check for default config file
        default_config = "test_runner_config.yaml"
        if os.path.exists(default_config):
            return TestFrameworkConfig.from_yaml(default_config)

        # Return default configuration
        return TestFrameworkConfig()


# Default configuration (used when no config file is found)
DEFAULT_CONFIG = TestFrameworkConfig()
