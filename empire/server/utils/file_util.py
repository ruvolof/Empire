import logging
import os
import shutil
import subprocess

log = logging.getLogger(__name__)


def remove_dir_contents(path: str) -> None:
    """
    Removes all files and directories in a directory.
    Keeps the .keep and .gitignore that reserve the directory.
    """
    for root, dirs, files in os.walk(path):
        for f in files:
            if f.endswith(".keep") or f.endswith(".gitignore"):
                continue
            os.unlink(os.path.join(root, f))
        for d in dirs:
            shutil.rmtree(os.path.join(root, d))


def remove_file(path: str) -> None:
    """
    Removes a file. If the file doesn't exist, nothing happens.
    """
    if os.path.exists(path):
        os.remove(path)


def clear_file_contents(path: str) -> None:
    """
    Clears the contents of a file without deleting it.
    If the file doesn't exist, it creates an empty file.
    """
    try:
        with open(path, "w"):
            pass
        log.debug(f"Cleared contents of the file: {path}")
    except Exception as e:
        log.error(f"Failed to clear file contents for {path}: {e}", exc_info=True)


def run_as_user(command, user=None, cwd=None):
    """
    Runs a command as a specified user or the user who invoked sudo.
    If no user is specified and the script is not run with sudo, it runs as the current user.

    Args:
        command (list): The command to run, specified as a list of strings.
        user (str, optional): The username to run the command as. Defaults to None.
    """
    try:
        if user is None:
            user = os.getenv("SUDO_USER")

        command_with_user = ["sudo", "-u", user, *command] if user else command

        subprocess.run(command_with_user, check=True, cwd=cwd)

        log.debug("Command executed successfully: %s", " ".join(map(str, command)))

    except subprocess.CalledProcessError as e:
        # Log the error details
        log.error("Failed to execute command: %s", e, exc_info=True)
        log.error("Try running the command manually: %s", " ".join(command))
