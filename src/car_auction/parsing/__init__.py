"""PDF parsing strategies for auction result documents."""

from .pvrm import parse_pvrm_pdf
from .tvrm import parse_tvrm_pdf

__all__ = ["parse_pvrm_pdf", "parse_tvrm_pdf"]
