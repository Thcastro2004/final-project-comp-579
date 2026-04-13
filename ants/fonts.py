def make_ui_fonts() -> tuple[object, object, object]:
    import pygame._freetype as _ft

    _ft.init()

    class _UiFont:
        __slots__ = ("_f",)

        def __init__(self, size: int, *, strong: bool = False) -> None:
            self._f = _ft.Font(None, size=max(1, int(size)))
            self._f.antialiased = True
            if strong:
                self._f.strong = True

        def render(self, text, antialias, color, background=None):
            self._f.antialiased = bool(antialias)
            t = "" if text is None else str(text)
            if background is not None:
                return self._f.render(t, fgcolor=color, bgcolor=background)[0]
            return self._f.render(t, fgcolor=color)[0]

    return _UiFont(15), _UiFont(13), _UiFont(17, strong=True)
