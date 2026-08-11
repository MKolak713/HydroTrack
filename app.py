import sys
import cv2
import numpy as np
import time
import mediapipe as mp


from pathlib import Path
from notifications import show_reminder_notification
from stats import stats, minutes_since_last_drink
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QVBoxLayout, QStackedWidget, QHBoxLayout, QGridLayout, QSlider, QFormLayout, QCheckBox, QScrollArea, QFrame
)
from PySide6.QtGui import QImage, QPixmap, QFontDatabase, QFont, QIcon
from PySide6.QtCore import QTimer, Qt
from color_settings import load_color_range, save_color_range
from settings import REMINDER_TIME_MINUTES, CALIBRATION_BOX_COLORS
from bottle_detector import find_bottle_by_color_range
from app_settings import load_app_settings, save_app_settings

BASE_DIR = Path(__file__).resolve().parent

DRINK_COOLDOWN = 10
DEFAULT_REMINDER_MINUTES = 30
DEFAULT_BOTTLE_DISTANCE = 90
DEFAULT_SOUND_ENABLED = True
DEFAULT_MASK_ENABLED = False
CALIBRATION_SAMPLE_SCALE = 0.2
DRINK_EDGE_DISTANCE = 0.5
MIN_LARGE_ZONE_PIXELS = 800
MIN_SMALL_ZONE_PIXELS = 80
STARTUP_DETECTION_COOLDOWN = 2.0
DEFAULT_COLOR_SENSITIVITY = 100

class WaterApp(QWidget):
    def __init__(self):
        super().__init__()

        font_path = Path(__file__).parent / "assets" / "CherryBombOne-Regular.ttf"
        font_id = QFontDatabase.addApplicationFont(str(font_path))

        if font_id == -1:
            self.logo_font = QFont("Arial", 75)
        else:
            font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
            self.logo_font = QFont(font_family, 80)

        icon_path = BASE_DIR / "assets" / "Logo.ico"
        self.setWindowIcon(QIcon(str(icon_path)))
        self.cooldown_until = 0
        self.last_reminder_time = time.time()
        self.last_drink_time = time.time()
        self.drink_log = []
        self.session_start_time = time.time()
        self.saved_color_range, self.saved_preview_hsv = load_color_range()
        self.tracking = False
        self.cap = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_calibration_frame)
        self.current_frame = None
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(max_num_faces=1)
        self.tracking_timer_started = False
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.refresh_stats_page)
        self.detection_ready_time = 0


        saved_settings = load_app_settings()

        self.reminder_time_minutes = saved_settings["reminder_minutes"]
        self.bottle_near_mouth_distance = saved_settings["bottle_distance"]

        self.sound_enabled = saved_settings.get(
            "sound_enabled",
            DEFAULT_SOUND_ENABLED
        )
        self.mask_enabled = saved_settings.get(
            "mask_enabled",
            DEFAULT_MASK_ENABLED
        )

        self.color_sensitivity = saved_settings.get(
            "color_sensitivity",
            DEFAULT_COLOR_SENSITIVITY
        )

        self.setWindowTitle("HydroTrack")
        self.setMinimumSize(1000, 750)
        self.setStyleSheet("""
        QLabel {
            color: #123A72;
        }

        QPushButton {
            background-color: #4A90E2;
            color: white;
            border: 3px solid #2F5F9E;
            border-radius: 15px;
            font-size: 22px;
            font-weight: bold;
            min-height: 55px;
        }
        """)

        self.pages = QStackedWidget()

        self.home_page = self.create_home_page()
        self.stats_page = self.create_stats_page()
        self.drink_log_page = self.create_drink_log_page()
        self.settings_page = self.create_settings_page()
        self.how_it_works_page = self.create_how_it_works_page()
        self.calibration_page = self.create_calibration_page()

        self.pages.addWidget(self.home_page)
        self.pages.addWidget(self.stats_page)
        self.pages.addWidget(self.drink_log_page)
        self.pages.addWidget(self.settings_page)
        self.pages.addWidget(self.how_it_works_page)
        self.pages.addWidget(self.calibration_page)


        layout = QVBoxLayout()
        layout.addWidget(self.pages)
        self.setLayout(layout)



    def create_home_page(self):
        page = QWidget()
        layout = QGridLayout()

        title = QLabel("HydroTrack")
        title.setFont(self.logo_font)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            color: #0B77D8;
            margin-top: 20px;
            margin-bottom: 40px;
        """)

        self.home_status = QLabel("● Tracking is OFF")
        self.home_status.setAlignment(Qt.AlignCenter)
        self.home_status.setStyleSheet("""
                    font-size: 20px;
                    font-weight: bold;
                    color: #B3261E;
                """)

        button_style = """
            QPushButton {
                font-size: 20px;
                min-height: 90px;
                border-radius: 12px;
            }
        """

        self.home_track_button = QPushButton("Start Tracking \n (This may take a few seconds)")
        self.home_track_button.setStyleSheet(button_style)
        self.home_track_button.clicked.connect(self.toggle_tracking)

        stats_button = QPushButton("Statistics")
        stats_button.setStyleSheet(button_style)
        stats_button.clicked.connect(self.open_stats_page)

        drink_log_button = QPushButton("Drink Log")
        drink_log_button.setStyleSheet(button_style)
        drink_log_button.clicked.connect(self.open_drink_log_page)

        settings_button = QPushButton("Settings")
        settings_button.setStyleSheet(button_style)
        settings_button.clicked.connect(self.open_settings_page)

        how_button = QPushButton("How It Works")
        how_button.setStyleSheet(button_style)
        how_button.clicked.connect(self.open_how_it_works_page)

        # Add some spacing
        layout.setVerticalSpacing(25)
        layout.setHorizontalSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setColumnStretch(2, 1)

        # Layout
        layout.addWidget(title, 0, 0, 1, 4)
        layout.addWidget(self.home_status, 1, 0, 1, 4)
        layout.addWidget(self.home_track_button, 2, 0, 1, 4)
        layout.addWidget(stats_button, 3, 0)
        layout.addWidget(drink_log_button, 3, 1)
        layout.addWidget(settings_button, 3, 2)
        layout.addWidget(how_button, 3, 3)

        # Make everything expand nicely
        layout.setRowStretch(0, 1)
        layout.setRowStretch(1, 1)
        layout.setRowStretch(2, 2)
        layout.setRowStretch(3, 2)

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        layout.setColumnStretch(3, 1)

        page.setLayout(layout)
        return page

    def create_stats_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 30)
        layout.setSpacing(25)

        title = QLabel("Statistics")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 42px;
            font-weight: bold;
            color: #0B77D8;
        """)

        self.stats_text = QLabel()
        self.stats_text.setAlignment(Qt.AlignCenter)
        self.stats_text.setStyleSheet("""
            background-color: white;
            border: 4px solid #2F5F9E;
            border-radius: 25px;
            padding: 40px;
            font-size: 26px;
            color: #123A72;
        """)

        back_button = QPushButton("Back")
        back_button.clicked.connect(self.close_stats_page)

        layout.addWidget(title)
        layout.addWidget(self.stats_text, stretch=1)
        layout.addWidget(back_button)

        page.setLayout(layout)
        return page

    def create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 30)
        layout.setSpacing(25)

        title = QLabel("Settings")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 42px;
            font-weight: bold;
            color: #0B77D8;
        """)


        form = QFormLayout()
        form.setVerticalSpacing(25)

        # Reminder slider
        self.reminder_slider = QSlider(Qt.Horizontal)
        self.reminder_slider.setRange(1, 60)
        self.reminder_slider.setValue(DEFAULT_REMINDER_MINUTES)

        self.reminder_value = QLabel(f"{DEFAULT_REMINDER_MINUTES} minutes")
        self.reminder_value.setAlignment(Qt.AlignCenter)

        reminder_limits = QHBoxLayout()
        reminder_limits.addWidget(QLabel("1 min"))
        reminder_limits.addStretch()
        reminder_limits.addWidget(QLabel("60 min"))

        reminder_layout = QVBoxLayout()
        reminder_layout.setSpacing(2)  # Less space between items

        reminder_layout.addWidget(self.reminder_slider)
        reminder_layout.addLayout(reminder_limits)
        reminder_layout.addWidget(self.reminder_value, alignment=Qt.AlignCenter)

        self.reminder_slider.valueChanged.connect(
            lambda value: self.reminder_value.setText(f"{value} minutes")
        )

        # Bottle distance slider
        self.distance_slider = QSlider(Qt.Horizontal)
        self.distance_slider.setRange(60, 120)
        self.distance_slider.setValue(DEFAULT_BOTTLE_DISTANCE)

        self.distance_value = QLabel(f"{DEFAULT_BOTTLE_DISTANCE} pixels")
        self.distance_value.setAlignment(Qt.AlignCenter)

        distance_limits = QHBoxLayout()
        distance_limits.addWidget(QLabel("Near"))
        distance_limits.addStretch()
        distance_limits.addWidget(QLabel("Far"))

        distance_layout = QVBoxLayout()
        distance_layout.setSpacing(2)

        distance_layout.addWidget(self.distance_slider)
        distance_layout.addLayout(distance_limits)
        distance_layout.addWidget(self.distance_value, alignment=Qt.AlignCenter)

        self.distance_slider.valueChanged.connect(
            lambda value: self.distance_value.setText(f"{value} pixels")
        )

        # Color sensitivity slider
        self.color_slider = QSlider(Qt.Horizontal)
        self.color_slider.setRange(50, 250)
        self.color_slider.setValue(DEFAULT_COLOR_SENSITIVITY)

        self.color_value = QLabel(
            f"{DEFAULT_COLOR_SENSITIVITY}%"
        )
        self.color_value.setAlignment(Qt.AlignCenter)

        color_limits = QHBoxLayout()
        color_limits.addWidget(QLabel("Strict"))
        color_limits.addStretch()
        color_limits.addWidget(QLabel("Sensitive"))

        color_layout = QVBoxLayout()
        color_layout.setSpacing(2)

        color_layout.addWidget(self.color_slider)
        color_layout.addLayout(color_limits)
        color_layout.addWidget(
            self.color_value,
            alignment=Qt.AlignCenter
        )

        self.color_slider.valueChanged.connect(
            lambda value:
            self.color_value.setText(f"{value}%")
        )

        self.color_slider.valueChanged.connect(
            self.mark_settings_unsaved
        )

        self.sound_checkbox = QCheckBox("Play Reminder Sound")
        self.sound_checkbox.setChecked(self.sound_enabled)

        self.mask_checkbox = QCheckBox("Show Detection Mask While Tracking")
        self.mask_checkbox.setChecked(self.mask_enabled)

        checkbox_style = """
            QCheckBox {
                font-size: 18px;
                color: #123A72;
                spacing: 10px;
            }

            QCheckBox::indicator {
                width: 22px;
                height: 22px;
            }
        """

        self.sound_checkbox.setStyleSheet(checkbox_style)
        self.mask_checkbox.setStyleSheet(checkbox_style)

        self.sound_checkbox.stateChanged.connect(
            self.mark_settings_unsaved
        )

        self.mask_checkbox.stateChanged.connect(
            self.mark_settings_unsaved
        )

        checkbox_row = QHBoxLayout()
        checkbox_row.addWidget(self.sound_checkbox)
        checkbox_row.addSpacing(40)
        checkbox_row.addWidget(self.mask_checkbox)
        checkbox_row.addStretch()

        form.addRow("Reminder interval:", reminder_layout)
        form.addRow("Detection Range:", distance_layout)
        form.addRow("Color Sensitivity:\n(recalibrate)", color_layout)
        form.addRow("Options:", checkbox_row)

        calibration_button = QPushButton("Calibration \n (This may take a few seconds)")
        calibration_button.clicked.connect(self.open_calibration_page)

        back_button = QPushButton("Back")
        back_button.clicked.connect(lambda: self.pages.setCurrentWidget(self.home_page))

        reset_button = QPushButton("Reset to Defaults")
        reset_button.clicked.connect(self.reset_settings_to_defaults)

        self.save_settings_button = QPushButton("Save Settings")
        self.save_settings_button.clicked.connect(self.save_settings)

        self.reminder_slider.valueChanged.connect(self.mark_settings_unsaved)
        self.distance_slider.valueChanged.connect(self.mark_settings_unsaved)

        layout.addWidget(title)
        layout.addLayout(form)
        layout.addStretch()
        layout.addWidget(reset_button)
        layout.addWidget(calibration_button)
        layout.addWidget(self.save_settings_button)
        layout.addWidget(back_button)

        page.setLayout(layout)
        return page

    def create_how_it_works_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(41, 41, 41, 31)
        layout.setSpacing(25)

        title = QLabel("How HydroTrack Works")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 42px;
            font-weight: bold;
            color: #0B77D8;
        """)

        info = QLabel(
            "HydroTrack uses your webcam and computer vision to detect when you take a sip of water.\n\n"

            "1. Calibrate your bottle by saving its color in the Calibration page\n\n"

            "2. When tracking starts, your mouth's position is located in real time.\n\n"

            "3. HydroTrack searches each frame for objects matching your bottle's color and dimensions.\n\n"

            "4. When a detected bottle comes within a chosen distance to your mouth,a drink is counted. \n\n"

            "5. If no drink is detected within a chosen time interval, HydroTrack sends a desktop notification reminding you to hydrate."
        )

        info.setWordWrap(True)
        info.setAlignment(Qt.AlignTop)

        info.setStyleSheet("""
            background:white;
            border:4px solid #2F5F9E;
            border-radius:25px;
            padding:28px;
            font-size:21px;
            color:#123A72;
        """)

        back_button = QPushButton("Back")
        back_button.clicked.connect(
            lambda: self.pages.setCurrentWidget(self.home_page)
        )

        layout.addWidget(title)
        layout.addWidget(info, 1)
        layout.addWidget(back_button)

        page.setLayout(layout)
        return page

    def create_calibration_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)

        self.calibration_status = QLabel("")
        self.calibration_status.setAlignment(Qt.AlignCenter)
        self.calibration_status.setStyleSheet("""
            color: #0B77D8;
            font-size: 18px;
            font-weight: bold;
        """)


        title = QLabel("Calibration")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 42px;
            font-weight: bold;
            color: #0B77D8;
        """)

        instructions = QLabel(
            "● Angle your camera/bottle to reduce glare as much as possible\n"
            "● Use an opaque bottle for better accuracy"
        )
        instructions.setMinimumHeight(85)
        instructions.setAlignment(Qt.AlignCenter)
        instructions.setStyleSheet("""
            background:white;
            border:3px solid #2F5F9E;
            border-radius:18px;
            padding:18px;
            font-size:22px;
        """)

        color_title = QLabel("Saved Bottle Color")
        color_title.setAlignment(Qt.AlignCenter)
        color_title.setStyleSheet("""
            font-size: 26px;
            font-weight: bold;
            color: #0B77D8;
        """)

        self.color_preview = QLabel("Detected\nColor")
        self.color_preview.setFixedSize(220, 220)
        self.color_preview.setAlignment(Qt.AlignCenter)
        self.color_preview.setStyleSheet("""
            background: gray;
            color: white;
            border:4px solid #2F5F9E;
            border-radius:22px;
            font-size: 18px;
        """)

        color_layout = QVBoxLayout()
        color_layout.setSpacing(8)  # instead of the default larger spacing
        color_layout.setAlignment(Qt.AlignTop)
        color_layout.addWidget(color_title)
        color_layout.addWidget(self.color_preview)

        self.camera_label = QLabel("Camera feed will appear here")
        self.camera_label.setFixedSize(620, 350)
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setStyleSheet("""
            QLabel {
                background-color: black;
                color: white;
                border: 4px solid #2F5F9E;
                border-radius: 16px;
            }
        """)


        camera_row = QHBoxLayout()
        camera_row.setSpacing(40)
        camera_row.addWidget(self.camera_label)
        camera_row.addLayout(color_layout)

        back_button = QPushButton("← Back")
        back_button.clicked.connect(self.close_calibration_page)

        layout.addWidget(title)
        layout.addWidget(instructions)

        layout.addSpacing(25)

        layout.addLayout(camera_row, 1)  # Let the camera row take the available space

        layout.addSpacing(15)  # Small gap
        layout.addWidget(back_button)


        page.setLayout(layout)
        self.update_color_preview_from_saved_range()
        return page

    def open_stats_page(self):
        self.refresh_stats_page()
        self.pages.setCurrentWidget(self.stats_page)
        self.stats_timer.start(1000)

    def refresh_stats_page(self):
        self.stats_text.setText(
            f"⏰ Minutes since last drink:\n"
            f"{minutes_since_last_drink()}\n\n"
            f"🥤 Drinks this session:\n"
            f"{len(self.drink_log)}\n\n"
            f"🔔 Notifications shown:\n"
            f"{stats['notification_count']}"
        )

    def close_stats_page(self):
        self.stats_timer.stop()
        self.pages.setCurrentWidget(self.home_page)

    def open_settings_page(self):
        self.reminder_slider.setValue(
            self.reminder_time_minutes
        )

        self.distance_slider.setValue(
            self.bottle_near_mouth_distance
        )

        self.color_slider.setValue(
            self.color_sensitivity
        )

        self.sound_checkbox.setChecked(
            self.sound_enabled
        )

        self.mask_checkbox.setChecked(
            self.mask_enabled
        )

        self.save_settings_button.setText(
            "Save Settings"
        )

        self.pages.setCurrentWidget(
            self.settings_page
        )

    def toggle_tracking(self):
        if not self.tracking:
            self.start_tracking()
        else:
            self.stop_tracking()

    def start_tracking(self):
        self.stop_camera()

        self.tracking = True
        self.home_track_button.setText("Stop Tracking")
        self.home_status.setText("● Tracking is ON")
        self.home_status.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: #16803A;
        """)


        self.tracking_timer_started = False
        self.cooldown_until = 0
        self.session_start_time = time.time()
        self.detection_ready_time = time.time() + STARTUP_DETECTION_COOLDOWN
        self.cap = cv2.VideoCapture(0)

        if not self.cap.isOpened():
            self.cap = None
            self.tracking = False
            self.home_track_button.setText("Start Tracking")
            self.home_status.setText("● Camera unavailable")
            self.home_status.setStyleSheet("""
                font-size: 20px;
                font-weight: bold;
                color: #B3261E;
            """)
            return

        try:
            self.timer.timeout.disconnect()
        except TypeError:
            pass

        self.timer.timeout.connect(self.update_tracking_frame)
        self.timer.start(30)

    def update_tracking_frame(self):
        ret, frame = self.cap.read()

        if not ret:
            return

        if not self.tracking_timer_started:
            now = time.time()

            self.session_start_time = now
            self.last_drink_time = now
            self.last_reminder_time = now

            stats["last_drink_time"] = now

            self.tracking_timer_started = True

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape

        current_time = time.time()
        mouth_pos = None
        forehead_pos = None

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_results = self.face_mesh.process(rgb)

        if face_results.multi_face_landmarks:
            face = face_results.multi_face_landmarks[0]
            mouth = face.landmark[13]
            mouth_pos = (int(mouth.x * w), int(mouth.y * h))
            forehead = face.landmark[10]
            forehead_pos = (
                int(forehead.x * w),
                int(forehead.y * h)
            )

        current_bottle_detection = find_bottle_by_color_range(
            frame,
            self.saved_color_range,
            mouth_pos,
            forehead_pos,
            self.bottle_near_mouth_distance,
            self.mask_enabled
        )

        # Count immediately when a bottle is genuinely detected
        # in the current frame near the mouth.
        if (
                current_bottle_detection is not None
                and mouth_pos is not None
                and current_time >= self.cooldown_until
                and current_time >= self.detection_ready_time
        ):
            (
                bottle_pos,
                bottle_box,
                closest_mouth_distance,
                large_zone_pixels,
                small_zone_pixels
            ) = current_bottle_detection

            if (
                    closest_mouth_distance is not None
                    and closest_mouth_distance <= DRINK_EDGE_DISTANCE
                    and large_zone_pixels >= MIN_LARGE_ZONE_PIXELS
                    and small_zone_pixels >= MIN_SMALL_ZONE_PIXELS
            ):
                self.drink_log.append(current_time)

                stats["session_drinks"] = len(self.drink_log)
                stats["last_drink_time"] = current_time

                self.last_drink_time = current_time
                self.last_reminder_time = current_time

                self.last_drink_time = current_time
                self.last_reminder_time = current_time
                self.cooldown_until = current_time + DRINK_COOLDOWN

                print(
                    "Drink detected! "
                    f"Closest bottle point: "
                    f"{closest_mouth_distance:.1f}px"
                )

        reminder_seconds = self.reminder_time_minutes * 60

        if ( current_time - self.last_drink_time >= reminder_seconds and current_time - self.last_reminder_time >= reminder_seconds):
            show_reminder_notification(
                self.sound_enabled
            )
            stats["notification_count"] += 1
            self.last_reminder_time = current_time

    def stop_tracking(self):
        self.tracking = False
        self.tracking_timer_started = False

        self.home_track_button.setText("Start Tracking")
        self.home_status.setText("● Tracking is OFF")
        self.home_status.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: #B3261E;
        """)

        self.stop_camera()

    def update_calibration_frame(self):
        ret, frame = self.cap.read()

        if not ret:
            return

        frame = cv2.flip(frame, 1)

        self.current_frame = frame.copy()

        cx, cy, cw, ch = CALIBRATION_BOX_COLORS

        # Red calibration box (BGR: Blue, Green, Red)
        cv2.rectangle(frame, (cx, cy), (cx + cw, cy + ch), (0, 0, 255), 4)

        text = "Hold bottle here"
        text2 = "and press C"

        (font_width, font_height), _ = cv2.getTextSize(
            text,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            2
        )

        (font_width, font_height), _ = cv2.getTextSize(
            text2,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            2
        )

        text_x = (cx + (cw - font_width) // 2) -15
        text_y = cy - 30

        text2_x = cx + (cw - font_width) // 2
        text2_y = cy - 10

        cv2.putText(
            frame,
            text,
            (text_x, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),  # Red text
            2
        )

        cv2.putText(
            frame,
            text2,
            (text2_x, text2_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),  # Red text
            2
        )

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape

        image = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(image)

        self.camera_label.setPixmap(
            pixmap.scaled(
                self.camera_label.width() - 8,
                self.camera_label.height() - 8,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        )

    def open_calibration_page(self):
        if self.tracking:
            self.stop_tracking()

        self.stop_camera()
        self.pages.setCurrentWidget(self.calibration_page)
        self.calibration_status.setText("")

        self.cap = cv2.VideoCapture(0)

        if not self.cap.isOpened():
            self.cap = None
            return

        try:
            self.timer.timeout.disconnect()
        except TypeError:
            pass

        self.timer.timeout.connect(self.update_calibration_frame)
        self.timer.start(30)

    def close_calibration_page(self):
        self.stop_camera()
        self.camera_label.clear()
        self.pages.setCurrentWidget(self.settings_page)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_C:
            if self.pages.currentWidget() == self.calibration_page:
                self.calibrate_from_box()

    def calibrate_from_box(self):
        if self.current_frame is None:
            return

        cx, cy, cw, ch = CALIBRATION_BOX_COLORS

        sample_w = int(cw * CALIBRATION_SAMPLE_SCALE)
        sample_h = int(ch * CALIBRATION_SAMPLE_SCALE)

        sample_x = cx + (cw - sample_w) // 2
        sample_y = cy + (ch - sample_h) // 2

        roi = self.current_frame[
            sample_y:sample_y + sample_h,
            sample_x:sample_x + sample_w
        ]
        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        pixels = hsv_roi.reshape(-1, 3)

        # Remove white glare and extremely bright pixels.
        # White/glare normally has low saturation and high brightness.
        non_glare_pixels = pixels[
            ~(
                    (pixels[:, 1] < 55) &
                    (pixels[:, 2] > 170)
            )
        ]

        if len(non_glare_pixels) < 50:
            self.calibration_status.setText(
                "Too much glare or background. Try again."
            )
            return

        # Median is less affected by unusual bright or colored pixels.
        median_hsv = np.median(non_glare_pixels, axis=0)

        h, s, v = [int(value) for value in median_hsv]

        # Black, gray, and very dark bottles should be detected by brightness.
        is_dark_bottle = v < 130

        sensitivity = self.color_sensitivity / 100.0

        if is_dark_bottle:
            bottle_saturation = non_glare_pixels[:, 1]
            bottle_values = non_glare_pixels[:, 2]

            low_s = int(np.percentile(
                bottle_saturation, 25
            ))
            high_s = int(np.percentile(
                bottle_saturation, 75
            ))

            low_v = int(np.percentile(
                bottle_values, 20
            ))
            high_v = int(np.percentile(
                bottle_values, 80
            ))

            s_margin = int(10 * sensitivity)
            v_margin = int(13 * sensitivity)

            lower = (
                0,
                max(low_s - s_margin, 0),
                max(low_v - v_margin, 0)
            )

            upper = (
                179,
                min(high_s + s_margin, 255),
                min(high_v + v_margin, 150)
            )

        else:
            h_margin = int(35 * sensitivity)
            s_margin = int(40 * sensitivity)
            v_margin = int(45 * sensitivity)

            lower = (
                max(h - h_margin, 0),
                max(s - s_margin, 0),
                max(v - v_margin, 0)
            )

            upper = (
                min(h + h_margin, 179),
                min(s + s_margin, 255),
                min(v + v_margin, 255)
            )
        self.saved_color_range = (lower, upper)
        self.saved_preview_hsv = (h, s, v)
        save_color_range(
            lower,
            upper,
            self.saved_preview_hsv
        )

        # Convert HSV average color to RGB for preview
        hsv_color = np.uint8([[[h, s, v]]])
        rgb_color = cv2.cvtColor(hsv_color, cv2.COLOR_HSV2RGB)[0][0]

        r, g, b = [int(x) for x in rgb_color]

        self.color_preview.setStyleSheet(f"""
            QLabel {{
                background-color: rgb({r}, {g}, {b});
                color: white;
                border: 4px solid #2F5F9E;
                border-radius: 22px;
                font-size: 18px;
            }}
        """)

        self.calibration_status.setText("Calibration saved")

    def stop_camera(self):
        self.timer.stop()

        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def save_settings(self):
        self.reminder_time_minutes = self.reminder_slider.value()
        self.bottle_near_mouth_distance = self.distance_slider.value()
        self.color_sensitivity = (
            self.color_slider.value()
        )
        self.sound_enabled = self.sound_checkbox.isChecked()
        self.mask_enabled = self.mask_checkbox.isChecked()

        save_app_settings(
            self.reminder_time_minutes,
            self.bottle_near_mouth_distance,
            self.color_sensitivity,
            self.sound_enabled,
            self.mask_enabled
        )

        self.save_settings_button.setText("Settings Saved")

    def reset_settings_to_defaults(self):
        self.reminder_time_minutes = (
            DEFAULT_REMINDER_MINUTES
        )

        self.bottle_near_mouth_distance = (
            DEFAULT_BOTTLE_DISTANCE
        )

        self.sound_enabled = (
            DEFAULT_SOUND_ENABLED
        )

        self.reminder_slider.setValue(
            DEFAULT_REMINDER_MINUTES
        )

        self.distance_slider.setValue(
            DEFAULT_BOTTLE_DISTANCE
        )

        self.color_slider.setValue(
            DEFAULT_COLOR_SENSITIVITY
        )

        self.sound_checkbox.setChecked(
            DEFAULT_SOUND_ENABLED
        )
        self.mask_enabled = DEFAULT_MASK_ENABLED

        self.mask_checkbox.setChecked(
            DEFAULT_MASK_ENABLED
        )

        save_app_settings(
            DEFAULT_REMINDER_MINUTES,
            DEFAULT_BOTTLE_DISTANCE,
            DEFAULT_COLOR_SENSITIVITY,
            DEFAULT_SOUND_ENABLED,
            DEFAULT_MASK_ENABLED
        )

        self.save_settings_button.setText(
            "Defaults Restored"
        )

    def closeEvent(self, event):
        self.stop_camera()

        if self.face_mesh is not None:
            self.face_mesh.close()

        event.accept()

    def mark_settings_unsaved(self, _value=None):
        self.save_settings_button.setText("Save Settings")

    def open_how_it_works_page(self):
        self.pages.setCurrentWidget(self.how_it_works_page)

    def update_color_preview_from_saved_range(self):
        if self.saved_preview_hsv is None:
            self.color_preview.setStyleSheet("""
                background: gray;
                color: white;
                border: 4px solid #2F5F9E;
                border-radius: 22px;
                font-size: 18px;
            """)
            return

        h, s, v = self.saved_preview_hsv

        hsv_color = np.uint8([[[h, s, v]]])

        rgb_color = cv2.cvtColor(
            hsv_color,
            cv2.COLOR_HSV2RGB
        )[0][0]

        r, g, b = [int(value) for value in rgb_color]

        self.color_preview.setStyleSheet(f"""
            background-color: rgb({r}, {g}, {b});
            color: white;
            border: 4px solid #2F5F9E;
            border-radius: 22px;
            font-size: 18px;
        """)

    def create_drink_log_page(self):
        page = QWidget()

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(40, 40, 40, 30)
        main_layout.setSpacing(20)

        title = QLabel("Drink Log")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 42px;
            font-weight: bold;
            color: #0B77D8;
        """)

        # Scrollable area
        self.drink_log_frame = QFrame()
        self.drink_log_frame.setStyleSheet("""
            QFrame {
                background: white;
                border: 4px solid #2F5F9E;
                border-radius: 22px;
            }
        """)

        frame_layout = QVBoxLayout(self.drink_log_frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.setSpacing(0)

        # Actual scroll area
        self.drink_log_scroll = QScrollArea()
        self.drink_log_scroll.setWidgetResizable(True)
        self.drink_log_scroll.setFrameShape(QFrame.NoFrame)

        self.drink_log_scroll.setStyleSheet("""
            QScrollArea {
                background: white;
                border: none;
            }

            QScrollArea QWidget {
                background: white;
                border: none;
            }
            QScrollBar:vertical {
        background: #E0E0E0;
        width: 14px;
        margin: 0px;
        border-radius: 7px;
    }

    QScrollBar::handle:vertical {
        background: #888888;
        min-height: 30px;
        border-radius: 7px;
    }

    QScrollBar::handle:vertical:hover {
        background: #707070;
    }

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {
        height: 0px;
    }

    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {
        background: transparent;
    }
        """)

        self.drink_log_container = QWidget()

        self.drink_log_layout = QVBoxLayout(
            self.drink_log_container
        )

        self.drink_log_layout.setContentsMargins(
            20, 20, 20, 20
        )

        self.drink_log_layout.setSpacing(15)

        self.drink_log_scroll.setWidget(
            self.drink_log_container
        )

        frame_layout.addWidget(
            self.drink_log_scroll
        )

        back_button = QPushButton("Back")
        back_button.clicked.connect(
            lambda: self.pages.setCurrentWidget(
                self.home_page
            )
        )

        main_layout.addWidget(title)
        main_layout.addWidget(
            self.drink_log_frame,
            stretch=1
        )
        main_layout.addWidget(back_button)

        page.setLayout(main_layout)

        return page

    def open_drink_log_page(self):
        self.refresh_drink_log()
        self.pages.setCurrentWidget(
            self.drink_log_page
        )

    def refresh_drink_log(self):
        # Remove the old displayed entries.
        while self.drink_log_layout.count():
            item = self.drink_log_layout.takeAt(0)

            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        if not self.drink_log:
            empty_label = QLabel(
                "No drinks detected yet."
            )

            empty_label.setAlignment(Qt.AlignCenter)

            empty_label.setStyleSheet("""
                font-size: 22px;
                color: #123A72;
                padding: 30px;
            """)

            self.drink_log_layout.addWidget(
                empty_label
            )

            self.drink_log_layout.addStretch()
            return

        # Newest drinks appear first.
        for timestamp in reversed(
                self.drink_log
        ):
            row = QWidget()
            row_layout = QHBoxLayout(row)

            time_text = time.strftime(
                "%I:%M:%S %p",
                time.localtime(timestamp)
            )

            drink_label = QLabel(
                f"Drink detected!\nTime: {time_text}"
            )

            drink_label.setStyleSheet("""
                font-size: 21px;
                color: #123A72;
            """)

            remove_button = QPushButton(
                "Remove"
            )

            remove_button.setFixedWidth(150)

            remove_button.setStyleSheet("""
                QPushButton {
                    background-color: #D20A0A;
                    color: white;
                    border-radius: 12px;
                    font-size: 18px;
                    font-weight: bold;
                    min-height: 50px;
                }
            """)

            remove_button.clicked.connect(
                lambda checked=False,
                       t=timestamp:
                self.remove_drink(t)
            )

            row_layout.addWidget(drink_label)
            row_layout.addStretch()
            row_layout.addWidget(remove_button)

            self.drink_log_layout.addWidget(row)

        self.drink_log_layout.addStretch()

    def remove_drink(self, timestamp):
        if timestamp not in self.drink_log:
            return

        self.drink_log.remove(timestamp)

        # Always derive the count from the log.
        stats["session_drinks"] = len(self.drink_log)

        if self.drink_log:
            newest_drink = max(self.drink_log)

            stats["last_drink_time"] = newest_drink
            self.last_drink_time = newest_drink

        else:
            stats["last_drink_time"] = self.session_start_time
            self.last_drink_time = self.session_start_time

        self.refresh_drink_log()
        self.refresh_stats_page()


app = QApplication(sys.argv)
window = WaterApp()
window.show()
sys.exit(app.exec())