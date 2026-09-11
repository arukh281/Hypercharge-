"""Bundled skill packs — shipped in package, synced on install."""

from __future__ import annotations

from hypercharge.skill_packs import BUNDLED_SKILL_NAMES, bundled_skill_src, list_bundled_skills


def test_all_bundled_skills_present_in_package():
    skills = list_bundled_skills()
    names = {n for n, _ in skills}
    assert names == set(BUNDLED_SKILL_NAMES)
    for name, path in skills:
        assert (path / "SKILL.md").is_file(), name


def test_bundled_skill_src_hypercharge_main():
    src = bundled_skill_src("hypercharge")
    assert src is not None
    assert (src / "SKILL.md").is_file()


def test_hypercharge_concise_has_frontmatter():
    from hypercharge.paths import PACKAGE_ROOT

    text = (PACKAGE_ROOT / "skill-packs" / "hypercharge-concise" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "name: hypercharge-concise" in text
    assert "Answer in the first line" in text
