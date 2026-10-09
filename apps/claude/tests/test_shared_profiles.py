"""Every account profile shares the default profile's instructions, skills,
settings, plugins and projects; only the login stays its own."""

from pathlib import Path

import runner


def make_main(root: Path) -> Path:
    main = root / "main"
    (main / "skills/lean").mkdir(parents=True)
    (main / "skills/lean/SKILL.md").write_text("lean")
    (main / "projects/-home-ejb/memory").mkdir(parents=True)
    (main / "projects/-home-ejb/memory/habit.md").write_text("main memory")
    (main / "CLAUDE.md").write_text("main rules")
    (main / "settings.json").write_text("{}")
    return main


def test_a_new_profile_links_everything_but_its_login(tmp_path):
    main = make_main(tmp_path)
    profiles = runner.Profiles(tmp_path / "data", main_dir=main)
    profiles.add("second")
    config = profiles.config_dir("second")
    assert config is not None
    for item in runner.SHARED_FILES + runner.SHARED_DIRS:
        assert (config / item).is_symlink(), item
        assert (config / item).resolve() == (main / item).resolve()
    assert (config / "CLAUDE.md").read_text() == "main rules"
    assert (config / "skills/lean/SKILL.md").read_text() == "lean"
    assert (config / "projects/-home-ejb/memory/habit.md").read_text() == "main memory"
    (config / ".credentials.json").write_text("second login")
    assert not (main / ".credentials.json").exists()
    # A session on any account lists itself where Crew Room, the Board and
    # the crew notes hook look: the default profile's sessions folder.
    assert (config / "sessions").resolve() == (main / "sessions").resolve()


def test_what_a_profile_had_is_merged_and_nothing_is_lost(tmp_path):
    main = make_main(tmp_path)
    profiles = runner.Profiles(tmp_path / "data", main_dir=main)
    config = tmp_path / "data/profiles/second"
    (config / "projects/-home-ejb/memory").mkdir(parents=True)
    (config / "projects/-home-ejb/abc.jsonl").write_text("transcript")
    (config / "projects/-home-ejb/memory/habit.md").write_text("second memory")
    (config / "skills/synced").mkdir(parents=True)
    (config / "CLAUDE.md").write_text("second rules")
    profiles.link_shared("second")
    # New things moved into the shared copy.
    assert (main / "projects/-home-ejb/abc.jsonl").read_text() == "transcript"
    assert (main / "skills/synced").is_dir()
    # A clash keeps the shared copy and puts the profile's own one aside.
    assert (main / "projects/-home-ejb/memory/habit.md").read_text() == "main memory"
    aside = config / "projects.before-shared/-home-ejb/memory/habit.md"
    assert aside.read_text() == "second memory"
    assert (config / "CLAUDE.md.before-shared").read_text() == "second rules"
    assert (config / "CLAUDE.md").read_text() == "main rules"


def test_linking_is_repeatable_and_env_keeps_it_current(tmp_path):
    main = make_main(tmp_path)
    profiles = runner.Profiles(tmp_path / "data", main_dir=main)
    profiles.add("second")
    profiles.link_shared("second")
    env = profiles.env("second")
    config = Path(env["CLAUDE_CONFIG_DIR"])
    assert sorted(p.name for p in config.iterdir()) == sorted(
        runner.SHARED_FILES + runner.SHARED_DIRS
    )
    # A shared file that appears later is linked on the next start.
    (config / "settings.json").unlink()
    profiles.env("second")
    assert (config / "settings.json").is_symlink()


def test_the_default_profile_is_left_alone(tmp_path):
    main = make_main(tmp_path)
    profiles = runner.Profiles(tmp_path / "data", main_dir=main)
    profiles.link_shared("default")
    assert "CLAUDE_CONFIG_DIR" not in profiles.env("default")
    assert not (tmp_path / "data/profiles").exists()
