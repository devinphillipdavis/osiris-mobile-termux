"""Directive F -- read the research ladder, stage the next rung, run it in the background.

Bound by the same rule as the desktop: the criterion is committed before the run. This
package will stage a rung that has no pre-registration, but it will not launch one, and
it never writes a verdict for a criterion it had to infer.

Submodules load lazily (PEP 562) so `python -m osiris_mobile.ladder.advance` does not
re-import a module the package has already bound, which runpy warns about.
"""

__all__ = ["Program", "Rung", "load_program", "Advancer", "StagedRun"]

_LAZY = {"Program": "program", "Rung": "program", "load_program": "program",
         "Advancer": "advance", "StagedRun": "advance"}


def __getattr__(name):
    if name in _LAZY:
        import importlib
        module = importlib.import_module("." + _LAZY[name], __name__)
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    return sorted(list(globals()) + __all__)
