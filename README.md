# HydroTrack 

HydroTrack is a Windows desktop application that uses computer vision
to automatically detect when a user drinks water and track their
hydration throughout the day.

## Features

- Real-time webcam-based drink detection
- Bottle color calibration
- MediaPipe facial landmark tracking
- Adjustable detection range
- Adjustable color sensitivity
- Customizable hydration reminders
- Optional reminder sounds
- Session hydration statistics
- Editable drink history
- Optional detection mask for debugging

## How It Works

HydroTrack uses MediaPipe to locate the user's mouth and OpenCV to
identify a calibrated water bottle.

Rather than simply detecting the bottle anywhere in the camera frame,
HydroTrack analyzes the bottle's position relative to the user's mouth
and uses multiple detection zones to determine when a drink has
actually occurred.

## Built With

- Python
- OpenCV
- MediaPipe
- PySide6
- NumPy
- Winotify

## Screenshots
<img width="993" height="774" alt="htmain" src="https://github.com/user-attachments/assets/b14aefd6-c780-4661-a32f-1a9b21b2038d" />
<img width="993" height="770" alt="htlogs" src="https://github.com/user-attachments/assets/55b173bc-42e6-4866-ad9b-31ba97fc29a0" />
<img width="991" height="770" alt="htset" src="https://github.com/user-attachments/assets/171cf337-23ab-4ee1-be7d-000aea84e1d6" />
<img width="215" height="215" alt="htmask" src="https://github.com/user-attachments/assets/28779e68-aebd-428b-a36f-5d17b5e506ab" />



## Download

A packaged Windows version of HydroTrack is available under Releases.
