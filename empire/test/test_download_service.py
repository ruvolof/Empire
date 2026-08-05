import io
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from starlette import status

from empire.server.core.download_service import DownloadService


def test__increment_filename(tmp_path):
    path = tmp_path / "test.txt"

    filename, location = DownloadService._increment_filename(path)

    assert filename == "test.txt"
    assert location == path

    path.write_text("test")

    filename, location = DownloadService._increment_filename(path)

    assert filename == "test(1).txt"
    assert location == tmp_path / "test(1).txt"

    location.write_text("test")

    filename, location = DownloadService._increment_filename(path)

    assert filename == "test(2).txt"
    assert location == tmp_path / "test(2).txt"


def test_create_download_from_path(main, session_local, models):
    test_upload = Path(__file__).parent / "test-upload.yaml"
    download_service: DownloadService = main.downloadsv2
    with session_local() as db:
        user = db.query(models.User).first()
        download = download_service.create_download(db, user, test_upload)

        assert download.id > 0
        assert download.filename.startswith("test-upload")
        assert download.filename.endswith(".yaml")
        assert f"downloads/uploads/{user.username}/" in download.location
        assert download.location.endswith(".yaml")

        db.delete(download)


def test_create_download_blocks_path_traversal(main, session_local, models):
    """A traversal filename must be rejected, never written outside downloads."""
    download_service: DownloadService = main.downloadsv2
    escaped = Path("/tmp/empire_traversal_probe.txt")
    escaped.unlink(missing_ok=True)
    upload = UploadFile(
        io.BytesIO(b"pwned"),
        filename="../../../../../../../../tmp/empire_traversal_probe.txt",
    )
    with session_local() as db:
        user = db.query(models.User).first()

        with pytest.raises(HTTPException) as exc_info:
            download_service.create_download(db, user, upload)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert not escaped.exists(), "traversal file escaped the downloads directory"


def test_create_download_from_text_blocks_path_traversal(main, session_local, models):
    """The text-upload path must reject a traversal filename too."""
    download_service: DownloadService = main.downloadsv2
    escaped = Path("/tmp/empire_text_traversal_probe.txt")
    escaped.unlink(missing_ok=True)
    with session_local() as db:
        user = db.query(models.User).first()

        with pytest.raises(HTTPException) as exc_info:
            download_service.create_download_from_text(
                db,
                user,
                "pwned",
                "../../../../../../../../tmp/empire_text_traversal_probe.txt",
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert not escaped.exists()


def test_create_download_rejects_issue_824_poc(main, session_local, models):
    """Exact proof-of-concept from GitHub issue #824.

    The reported exploit uploads a file named
    ``../../../../../../../../root/.ssh/authorized_keys`` to overwrite the
    server's SSH authorized_keys. It must be rejected before any write, so the
    target path is never touched even when the server runs as root.
    """
    download_service: DownloadService = main.downloadsv2
    poc_filename = "../../../../../../../../root/.ssh/authorized_keys"
    upload = UploadFile(io.BytesIO(b"attacker-key"), filename=poc_filename)
    with session_local() as db:
        user = db.query(models.User).first()

        with pytest.raises(HTTPException) as exc_info:
            download_service.create_download(db, user, upload)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


class TestSecureUploadLocation:
    """Direct unit tests for _secure_upload_location against adversarial input."""

    def test_plain_filename_is_allowed(self, tmp_path):
        location = DownloadService._secure_upload_location(tmp_path, "report.yaml")
        assert location == tmp_path / "report.yaml"

    @pytest.mark.parametrize(
        "filename",
        [
            "../etc/passwd",
            "../../../../../../etc/shadow",
            "../../../../../../../../root/.ssh/authorized_keys",  # issue #824 PoC
            "/etc/passwd",
            "..",
            ".",
            "",
            "foo/bar.txt",
            "..\\..\\windows\\evil.dll",
        ],
    )
    def test_traversal_is_rejected(self, tmp_path, filename):
        with pytest.raises(HTTPException) as exc_info:
            DownloadService._secure_upload_location(tmp_path, filename)
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
