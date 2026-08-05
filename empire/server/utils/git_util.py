import shutil
import subprocess
import tempfile
from pathlib import Path

from empire.server.common.helpers import random_string
from empire.server.utils.file_util import run_as_user


class GitOperationException(Exception):
    pass


def clone_git_repo(
    git_url: str, ref: str | None = None, directory: Path | None = None
) -> Path:
    """
    Clones a git repository to a directory and checks out a specific ref if provided.

    The clone is staged in a directory under the system tempdir first so it can
    run as the unprivileged sudo invoker (preserving their SSH agent) before
    being copied to ``directory``, which may be owned by another user. When
    ``directory`` is provided, the staging directory is removed once the copy
    completes. When ``directory`` is None, the caller becomes responsible for
    the staging directory's lifecycle. Partial staging directories from failed
    clones are always cleaned up.

    :param git_url: The git URL to clone
    :param ref: The ref to check out
    :param directory: The directory to clone the git repository to. If None, a temporary directory is used.
    :return: The directory the git repository was cloned to
    """
    tmp_dir = Path(tempfile.gettempdir()) / random_string(5)

    try:
        try:
            run_as_user(["git", "clone", git_url, tmp_dir])
        except subprocess.CalledProcessError:
            raise GitOperationException(
                f"Failed to clone git repository: {git_url}"
            ) from None

        if ref:
            try:
                run_as_user(["git", "checkout", ref], cwd=tmp_dir)
            except subprocess.CalledProcessError:
                raise GitOperationException(f"Failed to check out ref {ref}") from None

        if directory:
            shutil.copytree(tmp_dir, directory)
            return directory

        # Caller owns tmp_dir; skip the cleanup in finally.
        result = tmp_dir
        tmp_dir = None
        return result
    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
