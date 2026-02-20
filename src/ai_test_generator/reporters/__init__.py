"""Report generators for diagnosis output."""

from .markdown_reporter import generate_markdown_report
from .github_reporter import file_github_issue

__all__ = ["generate_markdown_report", "file_github_issue"]
