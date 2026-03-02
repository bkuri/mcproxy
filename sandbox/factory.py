"""Factory function for creating sandbox executors."""

from typing import Any, TYPE_CHECKING

from sandbox.executor import SandboxExecutor

if TYPE_CHECKING:
    from sandbox.access_control import SandboxManifest


def create_sandbox_executor(
    manifest: "SandboxManifest",
    tool_executor: Any,
    **kwargs: Any,
) -> SandboxExecutor:
    """Factory function to create a SandboxExecutor.

    Args:
        manifest: Sandbox manifest
        tool_executor: Tool execution callable
        **kwargs: Additional arguments for SandboxExecutor

    Returns:
        Configured SandboxExecutor instance
    """
    return SandboxExecutor(manifest, tool_executor, **kwargs)
