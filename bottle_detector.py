import cv2
import numpy as np


# Detection settings
MIN_BOTTLE_AREA = 1000
MIN_LONG_SIDE = 8
MIN_SHORT_SIDE = 7
MIN_FILL_RATIO = 0.08
MAX_BOTTLE_AREA = 18000
MAX_LONG_SIDE = 260
MAX_SHORT_SIDE = 130
MIN_LARGE_ZONE_PIXELS = 1200
MIN_SMALL_ZONE_PIXELS = 500

MOUTH_DISTANCE_WEIGHT = 8


def find_bottle_by_color_range(
    frame,
    color_range,
    mouth_pos=None,
    forehead_pos=None,
    detection_distance=110,
    show_mask=False
):
    if frame is None or color_range is None:
        return None

    lower, upper = color_range

    lower_array = np.array(lower, dtype=np.uint8)
    upper_array = np.array(upper, dtype=np.uint8)

    frame_height, frame_width = frame.shape[:2]

    # Default to searching the whole frame.
    roi_x1 = 0
    roi_y1 = 0
    roi_x2 = frame_width
    roi_y2 = frame_height

    # Restrict detection to an area around the mouth.
    if mouth_pos is not None:
        mouth_x, mouth_y = mouth_pos

        # Very small detection region around the mouth
        search_width = detection_distance * 2 + 40
        search_height = detection_distance * 2 + 40

        roi_x1 = max(
            0,
            mouth_x - search_width // 2
        )

        roi_x2 = min(
            frame_width,
            mouth_x + search_width // 2
        )

        roi_y1 = max(
            0,
            mouth_y - search_height // 2
        )

        roi_y2 = min(
            frame_height,
            mouth_y + search_height // 2
        )

    roi = frame[
        roi_y1:roi_y2,
        roi_x1:roi_x2
    ]

    if roi.size == 0:
        return None

    # Convert the search region to HSV.
    hsv = cv2.cvtColor(
        roi,
        cv2.COLOR_BGR2HSV
    )

    # Keep only pixels inside the calibrated HSV range.
    mask = cv2.inRange(
        hsv,
        lower_array,
        upper_array
    )

    # Bright, low-saturation pixels are likely white glare.
    glare_lower = np.array([0, 0, 180], dtype=np.uint8)
    glare_upper = np.array([179, 65, 255], dtype=np.uint8)

    glare_mask = cv2.inRange(
        hsv,
        glare_lower,
        glare_upper
    )

    # Only accept glare close to the calibrated bottle color.
    glare_search_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (11, 11)
    )

    near_bottle_mask = cv2.dilate(
        mask,
        glare_search_kernel,
        iterations=1
    )

    nearby_glare = cv2.bitwise_and(
        glare_mask,
        near_bottle_mask
    )

    mask = cv2.bitwise_or(
        mask,
        nearby_glare
    )

    # Smooth small rough edges in the mask.
    mask = cv2.GaussianBlur(
        mask,
        (5, 5),
        0
    )

    _, mask = cv2.threshold(
        mask,
        127,
        255,
        cv2.THRESH_BINARY
    )

    close_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (7, 7)
    )

    # Fill small gaps inside detected objects.
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        close_kernel,
        iterations=1
    )

    if mouth_pos is not None and forehead_pos is not None:
        # Convert full-frame positions into ROI coordinates.
        mouth_roi_x = mouth_pos[0] - roi_x1
        mouth_roi_y = mouth_pos[1] - roi_y1

        forehead_roi_x = forehead_pos[0] - roi_x1
        forehead_roi_y = forehead_pos[1] - roi_y1

        face_height = abs(mouth_roi_y - forehead_roi_y)

        head_center_x = mouth_roi_x

        # Move the exclusion area upward toward the hair.
        head_center_y = forehead_roi_y + int(face_height * 0.15)

        head_width = max(int(face_height * 2.7), 150)
        head_height = max(int(face_height * 1.25), 80)

        cv2.ellipse(
            mask,
            (head_center_x, head_center_y),
            (head_width // 2, head_height // 2),
            0,
            0,
            360,
            0,
            -1
        )

    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    valid_contours = []

    for contour in contours:
        area = cv2.contourArea(contour)

        if area < MIN_BOTTLE_AREA:
            continue

        rotated_rect = cv2.minAreaRect(contour)
        rect_width, rect_height = rotated_rect[1]

        if rect_width <= 0 or rect_height <= 0:
            continue

        center_x = int(rotated_rect[0][0]) + roi_x1
        center_y = int(rotated_rect[0][1]) + roi_y1

        if mouth_pos is not None:
            distance_to_mouth = (
                                        (center_x - mouth_pos[0]) ** 2
                                        + (center_y - mouth_pos[1]) ** 2
                                ) ** 0.5

            if distance_to_mouth > detection_distance:
                continue

        long_side = max(rect_width, rect_height)
        short_side = min(rect_width, rect_height)

        if long_side < MIN_LONG_SIDE:
            continue

        if short_side < MIN_SHORT_SIDE:
            continue

        if area > MAX_BOTTLE_AREA:
            continue

        if long_side > MAX_LONG_SIDE:
            continue

        if short_side > MAX_SHORT_SIDE:
            continue

        rotated_area = rect_width * rect_height
        fill_ratio = area / max(rotated_area, 1)

        if fill_ratio < MIN_FILL_RATIO:
            continue

        valid_contours.append(contour)

    debug_mask = cv2.cvtColor(
        mask,
        cv2.COLOR_GRAY2BGR
    )

    if not valid_contours:
        if show_mask:
            cv2.imshow("Bottle Mask", debug_mask)
            cv2.waitKey(1)
        else:
            try:
                cv2.destroyWindow("Bottle Mask")
            except cv2.error:
                pass

        return None

    if mouth_pos is not None:

        def contour_score(contour):
            area = cv2.contourArea(contour)
            x, y, width, height = cv2.boundingRect(contour)

            center_x = (
                x
                + width // 2
                + roi_x1
            )

            center_y = (
                y
                + height // 2
                + roi_y1
            )

            distance_to_mouth = (
                (center_x - mouth_pos[0]) ** 2
                + (center_y - mouth_pos[1]) ** 2
            ) ** 0.5

            return (
                area
                - distance_to_mouth * MOUTH_DISTANCE_WEIGHT
            )

        selected_contour = max(
            valid_contours,
            key=contour_score
        )

    else:
        selected_contour = max(
            valid_contours,
            key=cv2.contourArea
        )

    selected_mask = np.zeros_like(mask)

    cv2.drawContours(
        selected_mask,
        [selected_contour],
        -1,
        255,
        thickness=-1
    )

    large_zone_pixels = 0
    small_zone_pixels = 0

    # Create a mask containing only the selected bottle contour.
    selected_mask = np.zeros_like(mask)

    cv2.drawContours(
        selected_mask,
        [selected_contour],
        -1,
        255,
        thickness=-1
    )

    # Total detected bottle pixels.
    large_zone_pixels = cv2.countNonZero(
        selected_mask
    )

    if mouth_pos is not None:
        mouth_roi_x = mouth_pos[0] - roi_x1
        mouth_roi_y = mouth_pos[1] - roi_y1

        SMALL_ZONE_WIDTH = 70
        SMALL_ZONE_HEIGHT = 45

        small_x1 = max(
            0,
            mouth_roi_x - SMALL_ZONE_WIDTH // 2
        )

        small_x2 = min(
            selected_mask.shape[1],
            mouth_roi_x + SMALL_ZONE_WIDTH // 2
        )

        small_y1 = max(
            0,
            mouth_roi_y - SMALL_ZONE_HEIGHT // 2
        )

        small_y2 = min(
            selected_mask.shape[0],
            mouth_roi_y + SMALL_ZONE_HEIGHT // 2
        )

        if (
                small_x2 > small_x1
                and small_y2 > small_y1
        ):
            small_zone = selected_mask[
                small_y1:small_y2,
                small_x1:small_x2
            ]

            small_zone_pixels = cv2.countNonZero(
                small_zone
            )

    else:
        large_zone_pixels = 0
        small_zone_pixels = 0



    # Draw the contour selected as the bottle.
    # Draw every contour that qualifies as a possible bottle.
    for contour in valid_contours:
        rotated_rect = cv2.minAreaRect(contour)

        box = cv2.boxPoints(rotated_rect)
        box = np.int32(box)

        cv2.drawContours(
            debug_mask,
            [box],
            0,
            (128, 128, 128),
            3
        )

    if show_mask:
        cv2.imshow(
            "Bottle Mask",
            debug_mask
        )
        cv2.waitKey(1)

    else:
        try:
            cv2.destroyWindow("Bottle Mask")
        except cv2.error:
            pass

    x, y, width, height = cv2.boundingRect(
        selected_contour
    )

    full_x = x + roi_x1
    full_y = y + roi_y1

    selected_rotated_rect = cv2.minAreaRect(
        selected_contour
    )

    rotated_center_x, rotated_center_y = (
        selected_rotated_rect[0]
    )

    bottle_pos = (
        int(rotated_center_x) + roi_x1,
        int(rotated_center_y) + roi_y1
    )

    bottle_box = (
        full_x,
        full_y,
        width,
        height
    )

    closest_mouth_distance = None

    if mouth_pos is not None:
        # Convert the full-frame mouth position into ROI coordinates.
        mouth_in_roi = (
            float(mouth_pos[0] - roi_x1),
            float(mouth_pos[1] - roi_y1)
        )

        # Positive when inside the contour, negative when outside.
        signed_distance = cv2.pointPolygonTest(
            selected_contour,
            mouth_in_roi,
            True
        )

        # Distance to the closest edge of the detected bottle.
        # If the mouth is inside the contour, the distance is zero.
        closest_mouth_distance = max(
            0.0,
            -signed_distance
        )

    return (
        bottle_pos,
        bottle_box,
        closest_mouth_distance,
        large_zone_pixels,
        small_zone_pixels
    )