"""Test cancellation adapter around the canonical process-tree backends."""
from command_tree import CommandTree
from resource_ownership import defer_cancellation


class TestCommandTree(CommandTree):
    """Register creation through the test owner's cooperative handoff policy."""

    def start(self, command, **options):
        with defer_cancellation():
            return self.backend.start(command, **options)
