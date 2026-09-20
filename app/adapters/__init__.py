"""Thin adapters around external HTTP APIs."""

from app.adapters.devin_client import DevinClient, DevinSession
from app.adapters.github_client import GitHubClient, GitHubIssue

__all__ = ["DevinClient", "DevinSession", "GitHubClient", "GitHubIssue"]
