"""Telemetry capture and the fold-aware live monitor pane."""

from .stream import FrameStream, default_stream_path
from .tail import render, watch

__all__ = ["FrameStream", "default_stream_path", "render", "watch"]
