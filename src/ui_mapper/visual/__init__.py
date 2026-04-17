"""Visual mapping primitives — screenshot, focus, debug snapshot persistence.

These modules are shared across mappers and tests. The concrete
:class:`~ui_mapper.mappers.visual.VisualMapper` composes them into a
mapping loop.
"""

from .snapshots import SnapshotWriter, snapshot_dir_for  # noqa: F401
from .focus import focus_window  # noqa: F401
from .verification import (  # noqa: F401
    MenuOpenCheck,
    DialogOpenCheck,
    verify_menu_open,
    verify_dialog_open,
)
from .coordinates import (  # noqa: F401
    Box,
    BoxesResult,
    query_menu_bar_boxes,
    scale_box_to_screen,
)
