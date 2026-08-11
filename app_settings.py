import json

SETTINGS_FILE = "app_settings.json"

DEFAULT_SETTINGS = {
    "reminder_minutes": 30,
    "bottle_distance": 90,
    "sound_enabled": True,
    "mask_enabled": False
}


def save_app_settings(
    reminder_minutes,
    bottle_distance,
    color_sensitivity,
    sound_enabled,
    mask_enabled
):
    data = {
        "reminder_minutes": reminder_minutes,
        "bottle_distance": bottle_distance,
        "color_sensitivity": color_sensitivity,
        "sound_enabled": sound_enabled,
        "mask_enabled": mask_enabled
    }

    with open(SETTINGS_FILE, "w") as file:
        json.dump(data, file, indent=4)


def load_app_settings():
    try:
        with open(SETTINGS_FILE, "r") as file:
            data = json.load(file)

        return {
            "reminder_minutes": data.get(
                "reminder_minutes",
                DEFAULT_SETTINGS["reminder_minutes"]
            ),

            "bottle_distance": data.get(
                "bottle_distance",
                DEFAULT_SETTINGS["bottle_distance"]
            ),

            "sound_enabled": data.get(
                "sound_enabled",
                DEFAULT_SETTINGS["sound_enabled"]
            ),

            "color_sensitivity": data.get(
                "color_sensitivity",
                100
            ),

            "mask_enabled": data.get(
                "mask_enabled",
                DEFAULT_SETTINGS["mask_enabled"]
            )
        }

    except (
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError
    ):
        return DEFAULT_SETTINGS.copy()