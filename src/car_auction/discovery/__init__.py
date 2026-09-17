"""Discovery strategies for locating auction result PDFs."""

from .pvrm_index import discover_pvrm_pdfs
from .tvrm_index import discover_tvrm_pdfs
from .date_templates import discover_tvrm_pdfs_from_templates

__all__ = [
    "discover_pvrm_pdfs",
    "discover_tvrm_pdfs",
    "discover_tvrm_pdfs_from_templates",
]
