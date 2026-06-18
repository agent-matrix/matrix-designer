"""Matrix Designer — the Brain of the Matrix ecosystem.

Turns an idea (plus optional references: image, PDF, URL, repo) into a governed
**Design Bundle**: the full solution design — framework decision, visual/UX target,
architecture, entity/data contracts, asset manifest, acceptance criteria (including
visual), and an ordered, dependency-aware batch roadmap — BEFORE Matrix Builder turns
it into blueprint candidates.

    Matrix Designer thinks.  Matrix Builder governs.  GitPilot builds.  Matrix Definitions enforce.

Pipeline position::

    idea-request -> [ matrix-designer ] -> design-bundle -> blueprint-candidate (x3) -> matrix-bundle -> ...

The bundle is itself validated against Matrix Definitions design-packs, so the brain
never approves itself: AI may *propose* design; the Definitions *validate* it.
"""

__version__ = "0.6.1"

from .models import DesignBundle  # noqa: F401
