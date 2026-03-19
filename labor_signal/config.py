import os


def str_to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class LaborSignalSettings:
    ENABLE_LABOR_SIGNAL_ENGINE = str_to_bool(os.getenv("ENABLE_LABOR_SIGNAL_ENGINE"), True)
    ENABLE_OPPORTUNITY_SCORING = str_to_bool(os.getenv("ENABLE_OPPORTUNITY_SCORING"), True)
    ENABLE_SKILL_GAP_ENGINE = str_to_bool(os.getenv("ENABLE_SKILL_GAP_ENGINE"), True)
    ENABLE_MARKET_ROUTING_ADVISORY = str_to_bool(os.getenv("ENABLE_MARKET_ROUTING_ADVISORY"), True)
    SHOW_LABOR_WIDGETS_TO_USERS = str_to_bool(os.getenv("SHOW_LABOR_WIDGETS_TO_USERS"), False)
    SHOW_LABOR_WIDGETS_TO_ADMIN = str_to_bool(os.getenv("SHOW_LABOR_WIDGETS_TO_ADMIN"), True)
    USE_SIGNAL_ENGINE_IN_MATCHING = str_to_bool(os.getenv("USE_SIGNAL_ENGINE_IN_MATCHING"), False)

    DEFAULT_REGION_CODE = os.getenv("LABOR_SIGNAL_DEFAULT_REGION_CODE", "DC")
    DEFAULT_REGION_NAME = os.getenv("LABOR_SIGNAL_DEFAULT_REGION_NAME", "District of Columbia")
