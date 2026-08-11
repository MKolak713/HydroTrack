import time

stats = {
    "session_drinks": 0,
    "notification_count": 0,
    "last_drink_time": None
}

def minutes_since_last_drink():
    if stats["last_drink_time"] is None:
        return 0
    return int((time.time() - stats["last_drink_time"]) / 60)