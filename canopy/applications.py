"""Application discovery and search shared by Canopy layouts."""

def visible_apps(apps):
    """Filter hidden or unnamed launchers and sort without duplicates."""
    result = {}
    for app in apps:
        if app.should_show() and app.get_name() and app.get_id():
            result.setdefault(app.get_id(), app)
    return sorted(result.values(), key=lambda app: (app.get_name().casefold(), app.get_id()))


def matches_app(app, query: str) -> bool:
    """Match each query term against the display name or desktop entry ID."""
    fields = (app.get_name().casefold(), app.get_id().casefold())
    return all(any(term in field for field in fields) for term in query.casefold().split())
