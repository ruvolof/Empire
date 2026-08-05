import pytest

from empire.server.utils.file_util import is_path_within, safe_filename


class TestSafeFilename:
    @pytest.mark.parametrize("filename", ["report.yaml", "avatar.png", "a.b.c.txt"])
    def test_plain_names_pass_through(self, filename):
        assert safe_filename(filename) == filename

    @pytest.mark.parametrize(
        "filename",
        [
            "",
            None,
            ".",
            "..",
            "/",
            "/etc/passwd",
            "../etc/passwd",
            "../../../../etc/shadow",
            "../../../../../../../../root/.ssh/authorized_keys",  # issue #824 PoC
            "foo/bar.txt",
            "..\\..\\windows\\evil.dll",
            "dir\\file.txt",
            "foo\x00bar.txt",
        ],
    )
    def test_unsafe_names_return_none(self, filename):
        assert safe_filename(filename) is None


class TestIsPathWithin:
    def test_contained_path_is_within(self, tmp_path):
        assert is_path_within(tmp_path / "a" / "b.txt", tmp_path) is True

    @pytest.mark.parametrize(
        "relative",
        ["../evil.txt", "a/../../evil.txt", "../../../../etc/passwd"],
    )
    def test_traversal_is_not_within(self, tmp_path, relative):
        assert is_path_within(tmp_path / relative, tmp_path) is False

    def test_sibling_prefix_is_not_within(self, tmp_path):
        base = tmp_path / "downloads"
        base.mkdir()
        assert is_path_within(tmp_path / "downloads-evil" / "x", base) is False
