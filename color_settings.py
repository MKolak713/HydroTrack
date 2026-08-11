import json

COLOR_FILE = "bottle_color.json"


def save_color_range(lower, upper, preview_hsv):
    data = {
        "lower": [int(x) for x in lower],
        "upper": [int(x) for x in upper],
        "preview_hsv": [int(x) for x in preview_hsv]
    }

    with open(COLOR_FILE, "w") as file:
        json.dump(data, file)


def load_color_range():
    try:
        with open(COLOR_FILE, "r") as file:
            data = json.load(file)

            color_range = (
                tuple(data["lower"]),
                tuple(data["upper"])
            )

            preview_hsv = tuple(
                data.get("preview_hsv", [0, 0, 80])
            )

            return color_range, preview_hsv

    except (
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError
    ):
        return None, None