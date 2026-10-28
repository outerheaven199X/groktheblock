"""Compatibility alias: `import cryptosint` still works and loads grok_the_block.

Prefer `grok_the_block`. Do not mix both names in one process (each would hold its own module state).
"""
import os as _os
__path__ = [_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "grok_the_block")]
