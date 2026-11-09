"""Pinned Starlette parser with profile-local spooling, not a second import pipeline."""

from tempfile import SpooledTemporaryFile
from starlette.formparsers import MultiPartParser


class ManagedMultipart(MultiPartParser):
    def __init__(self, *args, directory, **kwargs):
        super().__init__(*args, **kwargs)
        self.directory = directory

    def on_headers_finished(self):
        super().on_headers_finished()
        if self._current_part.file is not None:
            # Parent callback has created only an empty in-memory spool.
            self._current_part.file.file.close()
            spool = SpooledTemporaryFile(
                max_size=self.spool_max_size, dir=self.directory
            )
            self._files_to_close_on_error.append(spool)
            self._current_part.file.file = spool
