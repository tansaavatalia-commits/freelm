"""Exception hierarchy shared by every GÉNESIS module.

Messages are in Italian because they reach the owner through the CLI/UI.
"""

from __future__ import annotations


class GenesisError(Exception):
    """Base class for every error raised by GÉNESIS."""


class ConfigError(GenesisError):
    """Invalid or unreadable configuration."""


class MigrationError(GenesisError):
    """The database schema cannot be brought to the expected version."""


class PermissionDenied(GenesisError):
    """An action was refused by the permission layer."""


class ApprovalRequired(PermissionDenied):
    """The action needs an owner approval; ``approval_id`` is the pending request."""

    def __init__(self, approval_id: str, action: str, level: int) -> None:
        super().__init__(
            f"l'azione '{action}' (livello {level}) richiede l'approvazione del proprietario: "
            f"genesis approvals approve {approval_id}"
        )
        self.approval_id = approval_id
        self.action = action
        self.level = level


class TaskError(GenesisError):
    """Invalid task definition or task-queue operation."""


class TaskCancelled(GenesisError):
    """Raised inside a task handler to acknowledge a cancellation request."""


class WorkerBusy(GenesisError):
    """Another process already holds the task-worker lock of this data folder."""


class ToolError(GenesisError):
    """A tool refused or failed an operation."""
