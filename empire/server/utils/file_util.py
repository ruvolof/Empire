import logging
import os
import subprocess
from pathlib import Path, PureWindowsPath

log = logging.getLogger(__name__)


def is_path_within(path: Path, base_dir: Path) -> bool:
    """Return True if ``path`` stays inside ``base_dir`` once resolved.

    Blocks directory traversal: a path containing ``..`` that escapes
    ``base_dir`` resolves outside it and returns False.
    """
    return path.resolve().is_relative_to(base_dir.resolve())


def safe_filename(filename: str | None) -> str | None:
    """Return ``filename`` when it is already a safe basename, else None.

    Multipart upload filenames are untrusted. Return None (so callers can
    reject the upload) when the name is empty, carries a null byte, is ``.`` or
    ``..``, or contains POSIX/Windows path components -- rather than silently
    rewriting the client's name to its basename.
    """
    if not filename or "\x00" in filename:
        return None
    # PureWindowsPath splits on both / and \, so .name is the bare final
    # component on either OS. Keep the ".." set check below -- ".." survives the
    # stripped != filename guard and must be rejected explicitly.
    stripped = PureWindowsPath(filename).name
    if stripped in {"", ".", ".."} or stripped != filename:
        return None
    return stripped


def run_as_user(  # noqa: PLR0913
    command, user=None, cwd=None, capture_output=False, check=True, text=True
):
    """
    Runs a command as a specified user or the user who invoked sudo.
    If no user is specified and the script is not run with sudo, it runs as the current user.

    Args:
        command (list): The command to run, specified as a list of strings.
        user (str, optional): The username to run the command as. Defaults to None.
        cwd (str, optional): The working directory for the command. Defaults to None.
        capture_output (bool, optional): Whether to capture and return the command's output. Defaults to False.

    Returns:
        str or None: The output of the command if capture_output is True, otherwise None.
    """
    try:
        if user is None:
            user = os.getenv("SUDO_USER")

        # Avoid sudo if target user is root or empty (typical in containers)
        if user in (None, "", "root"):
            command_with_user = command
        else:
            # Preserve env (-E) so SSH_AUTH_SOCK / GIT_SSH_COMMAND are available
            command_with_user = ["sudo", "-E", "-u", user, *command]

        result = subprocess.run(
            command_with_user,
            check=check,
            cwd=cwd,
            text=text,
            capture_output=capture_output,
        )
    except subprocess.CalledProcessError as e:
        log.exception("Failed to execute command")
        log.info(
            "Try running the command manually: %s", " ".join([str(c) for c in command])
        )
        if e.stdout:
            log.warning("Command output: %s", e.stdout)
        if e.stderr:
            log.warning("Command error output: %s", e.stderr)
        raise
    else:
        log.debug("Command executed successfully: %s", " ".join(map(str, command)))

        if capture_output:
            return result.stdout.strip()
        return None
