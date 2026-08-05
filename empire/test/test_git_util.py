import subprocess
from pathlib import Path

import pytest

from empire.server.utils import git_util
from empire.server.utils.git_util import GitOperationException, clone_git_repo


class _FakeRunAsUser:
    """Stub for ``run_as_user`` that records calls and simulates git side effects.

    Each entry in ``behaviors`` is consumed in order, one per call. Supported:
      ("clone_ok",): create the tmp_dir as if git cloned successfully.
      ("clone_partial",): create the tmp_dir, then raise CalledProcessError.
      ("clone_fail",): do not create tmp_dir, raise CalledProcessError.
      ("checkout_ok",): no-op; asserts ``cwd`` is the previously-cloned dir.
        Must follow a clone action — failing this precondition aborts the
        test with a clear message rather than a confusing path-mismatch.
      ("checkout_fail",): raise CalledProcessError.

    The signature explicitly mirrors ``run_as_user``'s real kwargs (``user``,
    ``cwd``, ``capture_output``, ``check``, ``text``) and rejects unknown kwargs
    so production-side signature drift fails tests loudly instead of silently
    being swallowed by a catch-all ``**kwargs``.
    """

    def __init__(self, behaviors: list[tuple[str, ...]]) -> None:
        self._calls = iter(behaviors)
        self.last_clone_dest: Path | None = None

    def __call__(
        self,
        command,
        user=None,
        cwd=None,
        capture_output=False,
        check=True,
        text=True,
        **extra,
    ):
        assert not extra, (
            f"fake run_as_user received unexpected kwargs: {extra}. "
            f"Either production changed signatures or the fake needs an update."
        )
        action = next(self._calls)
        kind = action[0]
        if kind == "clone_ok":
            dest = Path(command[-1])
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "file.txt").write_text("ok")
            self.last_clone_dest = dest
            return
        if kind == "clone_partial":
            Path(command[-1]).mkdir(parents=True, exist_ok=True)
            raise subprocess.CalledProcessError(1, command)
        if kind == "clone_fail":
            raise subprocess.CalledProcessError(1, command)
        if kind == "checkout_ok":
            assert self.last_clone_dest is not None, (
                "checkout_ok scripted without a prior clone action; "
                "this is a test-script bug, not a production issue."
            )
            assert cwd == self.last_clone_dest, (
                f"checkout cwd {cwd!r} != clone dest {self.last_clone_dest!r}"
            )
            return
        if kind == "checkout_fail":
            raise subprocess.CalledProcessError(1, command)
        raise AssertionError(f"unknown action: {action!r}")


@pytest.fixture
def isolated_tempdir(monkeypatch, tmp_path):
    """Point git_util's tempfile.gettempdir at a pytest-managed tmp_path.

    Eliminates coupling to the host /tmp and removes the need for a
    naming-pattern heuristic when asserting "the staging dir was cleaned up".
    """
    monkeypatch.setattr(git_util.tempfile, "gettempdir", lambda: str(tmp_path))
    return tmp_path


def _leftovers(tempdir: Path, exclude: frozenset[Path] = frozenset()) -> set[Path]:
    """Return any path (file or directory) left in ``tempdir`` outside ``exclude``.

    Includes files so a future bug that leaks a non-directory artifact next to
    the staging area (e.g. a git lockfile) trips the assertion.
    """
    return {p for p in tempdir.iterdir() if p not in exclude}


def test_clone_with_directory_removes_tmp_staging_dir(
    monkeypatch, isolated_tempdir, tmp_path
):
    """When ``directory`` is provided, the staging dir must not leak."""
    monkeypatch.setattr(git_util, "run_as_user", _FakeRunAsUser([("clone_ok",)]))

    dest = tmp_path / "dest"
    result = clone_git_repo("git://example.com/repo.git", directory=dest)

    assert result == dest
    assert (dest / "file.txt").read_text() == "ok"
    assert _leftovers(isolated_tempdir, exclude=frozenset({dest})) == set()


def test_clone_with_directory_and_ref_success(monkeypatch, isolated_tempdir, tmp_path):
    """Successful clone + checkout + copy: staging cleaned, checkout ran in staging."""
    fake = _FakeRunAsUser([("clone_ok",), ("checkout_ok",)])
    monkeypatch.setattr(git_util, "run_as_user", fake)

    dest = tmp_path / "dest"
    result = clone_git_repo("git://example.com/repo.git", ref="v1.0", directory=dest)

    assert result == dest
    assert (dest / "file.txt").read_text() == "ok"
    # _FakeRunAsUser internally asserts checkout's cwd == clone dest;
    # also verify the staging dir is gone post-cleanup.
    assert _leftovers(isolated_tempdir, exclude=frozenset({dest})) == set()


def test_clone_without_directory_keeps_tmp_dir_for_caller(
    monkeypatch, isolated_tempdir
):
    """When ``directory`` is None, the returned tmp_dir belongs to the caller."""
    monkeypatch.setattr(git_util, "run_as_user", _FakeRunAsUser([("clone_ok",)]))

    result = clone_git_repo("git://example.com/repo.git")

    assert result.exists()
    assert result.parent == isolated_tempdir
    assert (result / "file.txt").read_text() == "ok"
    assert _leftovers(isolated_tempdir) == {result}


def test_clone_without_directory_with_ref_success(monkeypatch, isolated_tempdir):
    """When ``directory`` is None + ``ref`` provided, ownership still transfers post-checkout.

    Guards against a refactor that, e.g., clears ``tmp_dir = None`` before the
    checkout block — which would leak the staging dir on success.
    """
    fake = _FakeRunAsUser([("clone_ok",), ("checkout_ok",)])
    monkeypatch.setattr(git_util, "run_as_user", fake)

    result = clone_git_repo("git://example.com/repo.git", ref="v1.0")

    assert result.exists()
    assert result.parent == isolated_tempdir
    assert (result / "file.txt").read_text() == "ok"
    assert _leftovers(isolated_tempdir) == {result}


def test_clone_failure_cleans_partial_tmp_dir(monkeypatch, isolated_tempdir):
    """A partial clone (dir created, command failed) is cleaned before re-raise."""
    monkeypatch.setattr(git_util, "run_as_user", _FakeRunAsUser([("clone_partial",)]))

    with pytest.raises(GitOperationException, match="Failed to clone"):
        clone_git_repo("git://example.com/repo.git")

    assert _leftovers(isolated_tempdir) == set()


def test_checkout_failure_cleans_tmp_dir(monkeypatch, isolated_tempdir, tmp_path):
    """Successful clone followed by failed checkout must still clean the staging dir."""
    monkeypatch.setattr(
        git_util,
        "run_as_user",
        _FakeRunAsUser([("clone_ok",), ("checkout_fail",)]),
    )

    with pytest.raises(GitOperationException, match="Failed to check out"):
        clone_git_repo(
            "git://example.com/repo.git", ref="v1.0", directory=tmp_path / "dest"
        )

    # dest was never created (copytree never ran), so nothing to exclude.
    assert _leftovers(isolated_tempdir) == set()


def test_copytree_failure_cleans_tmp_dir(monkeypatch, isolated_tempdir, tmp_path):
    """If shutil.copytree raises after a successful clone, the finally still cleans.

    Triggers a real-world failure mode (destination already exists →
    FileExistsError) rather than artificially destroying the source.
    """
    monkeypatch.setattr(git_util, "run_as_user", _FakeRunAsUser([("clone_ok",)]))

    dest = tmp_path / "dest"
    dest.mkdir()  # Pre-existing destination; shutil.copytree refuses to overwrite.

    with pytest.raises(FileExistsError):
        clone_git_repo("git://example.com/repo.git", directory=dest)

    assert _leftovers(isolated_tempdir, exclude=frozenset({dest})) == set()
