from modules.utils.timezone import now_in_timezone


def build_demo_data(a=None, b=None, tz=None, **kwargs):
    now = now_in_timezone(tz)
    primary = a if a is not None else "alpha"
    secondary = b if b is not None else "beta"
    combined = f"{primary} / {secondary}"
    metrics = [
        {"label": "参数A", "value": str(primary)},
        {"label": "参数B", "value": str(secondary)},
        {"label": "组合值", "value": combined},
    ]
    return {
        "meta": {
            "title": kwargs.get("title", "Demo Template"),
            "subtitle": kwargs.get("subtitle", "Generic plugin skeleton"),
            "generated_at": now.isoformat(timespec="seconds"),
            "tz": tz,
        },
        "summary": {
            "primary": primary,
            "secondary": secondary,
            "combined": combined,
        },
        "metrics": metrics,
        "detail": {
            "left": kwargs.get("left", "Left block"),
            "right": kwargs.get("right", "Right block"),
            "note": kwargs.get("note", "Keep layout logic in view files and helpers in utils.py."),
        },
    }