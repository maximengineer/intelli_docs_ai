class IntelliDocsError(Exception):
    """Base exception for IntelliDocs AI domain errors."""


class UnsupportedFileTypeError(IntelliDocsError):
    """Raised when a document parser does not support the uploaded file type."""


class ParserTimeoutError(IntelliDocsError):
    """Raised when document parsing exceeds the configured timeout."""
