"""Config loading and validation."""

from pathlib import Path

import pytest

from aqef.config import ConfigError, load_config, parse_config

FRAMEWORK_YAML = Path(__file__).parents[1] / "framework.yaml"


def minimal_config() -> dict:
    return {
        "version": "1.0",
        "name": "test",
        "trust": {"default_tier": 1, "tiers": {1: "suggest", 2: "act_with_review"}},
        "agents": {
            "agent-a": {"role": "testing", "trust_tier": 1, "spec": "a.md"},
        },
        "gates": {
            "gate-x": {
                "description": "x",
                "rules": [
                    {
                        "metric": "coverage",
                        "operator": ">=",
                        "threshold": 80,
                        "severity": "blocking",
                    }
                ],
            },
        },
        "workflows": {
            "wf": {
                "description": "w",
                "steps": [{"agent": "agent-a", "action": "do"}],
                "gate": "gate-x",
                "human_checkpoint": "on_fail",
            },
        },
    }


class TestShippedConfig:
    """The framework.yaml shipped with the framework must itself be valid."""

    def test_loads(self):
        config = load_config(FRAMEWORK_YAML)
        assert config.name == "AI Agentic Quality Engineering Framework"

    def test_fleet_size(self):
        config = load_config(FRAMEWORK_YAML)
        assert len(config.agents) == 10

    def test_gates_and_workflows(self):
        config = load_config(FRAMEWORK_YAML)
        assert set(config.gates) == {
            "pr-gate",
            "regression-gate",
            "release-gate",
            "ai-eval-gate",
        }
        assert set(config.workflows) == {
            "pr-quality-gate",
            "regression-cycle",
            "release-readiness",
            "ai-system-evaluation",
        }

    def test_release_workflows_always_checkpoint(self):
        config = load_config(FRAMEWORK_YAML)
        assert config.workflows["release-readiness"].human_checkpoint == "always"
        assert config.workflows["ai-system-evaluation"].human_checkpoint == "always"

    def test_agent_spec_files_exist(self):
        config = load_config(FRAMEWORK_YAML)
        root = FRAMEWORK_YAML.parent
        for agent in config.agents.values():
            assert (root / agent.spec).is_file(), f"missing spec: {agent.spec}"


class TestValidation:
    def test_minimal_config_is_valid(self):
        config = parse_config(minimal_config())
        assert config.workflows["wf"].gate == "gate-x"

    def test_missing_section_rejected(self):
        data = minimal_config()
        del data["gates"]
        with pytest.raises(ConfigError, match="gates"):
            parse_config(data)

    def test_bad_operator_rejected(self):
        data = minimal_config()
        data["gates"]["gate-x"]["rules"][0]["operator"] = "~="
        with pytest.raises(ConfigError, match="operator"):
            parse_config(data)

    def test_bad_severity_rejected(self):
        data = minimal_config()
        data["gates"]["gate-x"]["rules"][0]["severity"] = "fatal"
        with pytest.raises(ConfigError, match="severity"):
            parse_config(data)

    def test_non_numeric_threshold_rejected(self):
        data = minimal_config()
        data["gates"]["gate-x"]["rules"][0]["threshold"] = "eighty"
        with pytest.raises(ConfigError, match="threshold"):
            parse_config(data)

    def test_workflow_with_unknown_agent_rejected(self):
        data = minimal_config()
        data["workflows"]["wf"]["steps"][0]["agent"] = "agent-ghost"
        with pytest.raises(ConfigError, match="unknown agent"):
            parse_config(data)

    def test_workflow_with_unknown_gate_rejected(self):
        data = minimal_config()
        data["workflows"]["wf"]["gate"] = "gate-ghost"
        with pytest.raises(ConfigError, match="unknown gate"):
            parse_config(data)

    def test_bad_checkpoint_rejected(self):
        data = minimal_config()
        data["workflows"]["wf"]["human_checkpoint"] = "sometimes"
        with pytest.raises(ConfigError, match="human_checkpoint"):
            parse_config(data)

    def test_agent_with_undefined_trust_tier_rejected(self):
        data = minimal_config()
        data["agents"]["agent-a"]["trust_tier"] = 9
        with pytest.raises(ConfigError, match="trust_tier"):
            parse_config(data)

    def test_default_tier_must_be_defined(self):
        data = minimal_config()
        data["trust"]["default_tier"] = 7
        with pytest.raises(ConfigError, match="default_tier"):
            parse_config(data)
