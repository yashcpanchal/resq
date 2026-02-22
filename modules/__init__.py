# ResQ-Capital — Core Logic Modules
#
# Lazy imports — avoid crashing the server when optional heavy deps
# (osmnx, Pillow, etc.) are not yet installed.

__all__ = ["find_aid_sites", "get_best_aid_site"]


def __getattr__(name: str):
    if name in ("find_aid_sites", "get_best_aid_site"):
        from modules.candidate_verification import find_aid_sites, get_best_aid_site
        return find_aid_sites if name == "find_aid_sites" else get_best_aid_site
    raise AttributeError(f"module 'modules' has no attribute {name!r}")
