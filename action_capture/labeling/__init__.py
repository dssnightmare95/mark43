"""Pure functions: gesture classification and human-readable Spanish labels."""

from .classify import (  # noqa: F401
    CONTROL_LABELS, BUTTON_LABELS, KIND_LABELS, TEXT_CTRLS,
    classify_drag, stroke_metrics,
    describe_click, describe_scroll, describe_drag, describe_key,
    describe_text_input,
)
