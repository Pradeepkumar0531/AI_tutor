"""Pipeline failure taxonomy. The Celery task retries *transient* failures with
bounded backoff and marks *permanent* ones FAILED immediately — never infinite
retries, never silent success."""

from __future__ import annotations


class PermanentFailure(Exception):
    """Will not succeed on retry: corrupt PDF, no content, missing dependency,
    over-limit document. Carries a user-safe message plus a debug detail." """

    def __init__(self, user_message: str, *, detail: str = "") -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail


class TransientFailure(Exception):
    """May succeed on retry: storage/network blips, DB connectivity loss."""


class ExtractionFailed(PermanentFailure):
    pass


class NoUsableContent(PermanentFailure):
    pass


class DocumentTooLarge(PermanentFailure):
    pass


class OcrUnavailable(PermanentFailure):
    pass


class OcrFailed(PermanentFailure):
    pass
