DEFAULT_CHECKER_SKIN_ID = "classic"
STORE_ALL_ACCESS_LOGIN = "j0muty"

CHECKER_SKINS = [
    {
        "id": "classic",
        "name": "Обычные шашки",
        "tier": "default",
        "tier_label": "Базовый",
        "description": "Белые и черные полированные шашки для каждой партии.",
        "currency": "free",
        "soft_price": 0,
        "rub_price": 0,
    },
    {
        "id": "nordic_wood",
        "name": "Деревянные шашки",
        "tier": "simple",
        "tier_label": "Простой",
        "description": "Теплый клен против темного ореха, с тонкой шлифовкой по краю.",
        "currency": "soft",
        "soft_price": 650,
        "rub_price": 0,
    },
    {
        "id": "blue_circuit",
        "name": "Синий кант",
        "tier": "premium",
        "tier_label": "Крутой",
        "description": "Фарфор и графит с холодным технологичным кантом.",
        "currency": "rub",
        "soft_price": 0,
        "rub_price": 149,
    },
    {
        "id": "royal_onyx",
        "name": "Золотой оникс",
        "tier": "simple",
        "tier_label": "Простой",
        "description": "Мрамор, черный оникс и золотой обод с сияющей дамкой.",
        "currency": "soft",
        "soft_price": 1200,
        "rub_price": 0,
    },
    {
        "id": "nebula_crystal",
        "name": "Космический кристалл",
        "tier": "premium",
        "tier_label": "Крутой",
        "description": "Глубокий кристалл с космическими бликами и светящимся ядром.",
        "currency": "rub",
        "soft_price": 0,
        "rub_price": 299,
    },
]

CHECKER_SKIN_IDS = {skin["id"] for skin in CHECKER_SKINS}


def checker_skin_by_id(skin_id: str) -> dict | None:
    return next((skin for skin in CHECKER_SKINS if skin["id"] == skin_id), None)
