"""Scaffolding: generated starters must be valid by the framework's own rules."""

import pytest

from aqef.cli import main
from aqef.config import load_config
from aqef.risks import load_register
from aqef.scaffold import init_project


class TestInitProject:
    def test_creates_valid_starters(self, tmp_path):
        created = init_project(tmp_path)
        names = {p.name for p in created}
        assert names == {"framework.yaml", "risk-register.yaml"}

        config = load_config(tmp_path / "framework.yaml")
        assert "pr-gate" in config.gates
        assert config.workflows["pr-quality-gate"].gate == "pr-gate"
        # adoption guidance: start agents at suggest tier
        assert config.agents["qe-test-generator"].trust_tier == 1

        register = load_register(tmp_path / "risk-register.yaml")
        assert register.risks[0].id == "R-001"

    def test_refuses_overwrite_without_force(self, tmp_path):
        init_project(tmp_path)
        with pytest.raises(FileExistsError, match="framework.yaml"):
            init_project(tmp_path)

    def test_force_overwrites(self, tmp_path):
        init_project(tmp_path)
        (tmp_path / "framework.yaml").write_text("mangled", encoding="utf-8")
        init_project(tmp_path, force=True)
        load_config(tmp_path / "framework.yaml")  # valid again

    def test_creates_missing_directory(self, tmp_path):
        target = tmp_path / "nested" / "project"
        init_project(target)
        assert (target / "framework.yaml").is_file()


class TestCli:
    def test_init_prints_next_steps(self, tmp_path, capsys):
        code = main(["init", "--dir", str(tmp_path)])
        assert code == 0
        out = capsys.readouterr().out
        assert "framework.yaml" in out
        assert "Next steps" in out

    def test_init_conflict_exits_2(self, tmp_path, capsys):
        assert main(["init", "--dir", str(tmp_path)]) == 0
        capsys.readouterr()
        code = main(["init", "--dir", str(tmp_path)])
        assert code == 2
        assert "refusing to overwrite" in capsys.readouterr().err

    def test_init_force_succeeds_over_existing(self, tmp_path, capsys):
        assert main(["init", "--dir", str(tmp_path)]) == 0
        assert main(["init", "--dir", str(tmp_path), "--force"]) == 0
