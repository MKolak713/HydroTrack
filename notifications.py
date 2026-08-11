from winotify import Notification
import winsound
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent
DING_PATH = BASE_DIR / "assets" / "ding.wav"

def show_reminder_notification(
    sound_enabled=True
):
    if sound_enabled and DING_PATH.exists():
        winsound.PlaySound(
            str(DING_PATH),
            winsound.SND_FILENAME
        )

    toast = Notification(
        app_id="Water Detector",
        title="Water Reminder",
        msg="Time to drink some water!"
    )

    toast.show()