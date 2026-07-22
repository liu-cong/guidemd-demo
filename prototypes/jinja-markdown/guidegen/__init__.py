"""guidegen — jinja-markdown guide compiler.

One Jinja2 template + one guide.yaml per guide; docs, variants, CI plans
and the job matrix are all projections of a single render. No document
parser is owned here: Jinja parses the template (including the {% step %}
tag, registered via Jinja's extension API), PyYAML parses the config.
"""

from .guide import Guide
from .matrix import Matrix

__all__ = ["Guide", "Matrix"]
