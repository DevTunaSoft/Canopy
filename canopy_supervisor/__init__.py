"""Canopy multi-agent supervisor: bounded, worktree-isolated task coordination.

This package coordinates OpenCode coding workers. It never merges to main and
never executes untrusted Shell Pack code. State lives outside worker worktrees
so a failed task cannot corrupt the queue.
"""

__version__ = "0.1.0"
