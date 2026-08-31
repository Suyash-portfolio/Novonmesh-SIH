import os
import logging
import threading

logger = logging.getLogger("navonmesh.ai")

YOLO_MODEL = None
PLATE_MODEL = None
REID_MODEL = None
OCR_ENGINE = None
OCR_ENGINE_TYPE = None
OCR_INIT_ATTEMPTED = False

TESSERACT_PATH = None


def _find_tesseract():
    global TESSERACT_PATH
    if TESSERACT_PATH is not None:
        return TESSERACT_PATH
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
    ]
    import shutil
    which = shutil.which("tesseract")
    if which:
        candidates.insert(0, which)
    for p in candidates:
        if os.path.isfile(p):
            TESSERACT_PATH = p
            return p
    TESSERACT_PATH = ""
    return ""


def load_vehicle_detector(model_path=None):
    global YOLO_MODEL
    if YOLO_MODEL is not None:
        return YOLO_MODEL
    path = model_path or os.environ.get("YOLO_VEHICLE_MODEL", "yolov8n.pt")
    try:
        from ultralytics import YOLO
        if not os.path.exists(path):
            logger.info("Downloading yolov8n.pt...")
            YOLO("yolov8n.pt")
        YOLO_MODEL = YOLO(path)
        logger.info(f"Vehicle YOLO model loaded: {path}")
        return YOLO_MODEL
    except Exception as e:
        logger.warning(f"Vehicle model not available ({e}). Using fallback detection.")
        YOLO_MODEL = None
        return None


def load_plate_detector(model_path=None):
    global PLATE_MODEL
    if PLATE_MODEL is not None:
        return PLATE_MODEL
    if PLATE_MODEL is False:
        return None
    path = model_path or os.environ.get("YOLO_PLATE_MODEL", "models/license_plate.pt")
    try:
        from ultralytics import YOLO
        if os.path.exists(path):
            PLATE_MODEL = YOLO(path)
            logger.info(f"Plate YOLO model loaded: {path}")
        else:
            alt = "license_plate.pt"
            if os.path.exists(alt):
                PLATE_MODEL = YOLO(alt)
                logger.info(f"Plate YOLO model loaded: {alt}")
            else:
                logger.warning("No dedicated plate model found — plate detection limited")
                PLATE_MODEL = False
        return PLATE_MODEL if PLATE_MODEL is not False else None
    except Exception as e:
        logger.warning(f"Plate model not available: {e}")
        PLATE_MODEL = False
        return None


def load_reid_model(model_path=None):
    global REID_MODEL
    if REID_MODEL is not None:
        return REID_MODEL
    path = model_path or os.environ.get("REID_MODEL_PATH", "osnet_x1_0.pth")
    try:
        if os.path.exists(path):
            logger.info(f"Re-ID model loaded: {path}")
            REID_MODEL = {"path": path, "ready": True}
        else:
            logger.info("Re-ID model not found — using appearance-based fallback")
            REID_MODEL = {"path": None, "ready": False}
        return REID_MODEL
    except Exception as e:
        logger.warning(f"Re-ID model not available: {e}")
        REID_MODEL = {"path": None, "ready": False}
        return REID_MODEL


def _try_init_easyocr():
    result = [None]
    error = [None]

    def _init():
        try:
            import easyocr
            reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            result[0] = reader
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=_init, daemon=True)
    t.start()
    t.join(timeout=120)

    if t.is_alive():
        logger.warning("EasyOCR init timed out after 120s")
        return None
    if error[0]:
        logger.warning(f"EasyOCR init failed: {error[0]}")
        return None
    return result[0]


def _try_init_paddleocr():
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    os.environ["PADDLE_PDX_DISABLE_MODEL_DOWNLOAD"] = "False"

    result = [None]
    error = [None]

    def _init():
        try:
            from paddleocr import PaddleOCR
            import paddleocr
            version = getattr(paddleocr, "__version__", "0.0")
            if version.startswith("2."):
                engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            else:
                engine = PaddleOCR(lang="en")
            result[0] = engine
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=_init, daemon=True)
    t.start()
    t.join(timeout=60)

    if t.is_alive():
        logger.warning("PaddleOCR init timed out after 60s")
        return None
    if error[0]:
        logger.warning(f"PaddleOCR init failed: {error[0]}")
        return None
    return result[0]


def load_ocr_engine():
    global OCR_ENGINE, OCR_ENGINE_TYPE, OCR_INIT_ATTEMPTED
    if OCR_ENGINE is not None:
        return OCR_ENGINE
    if OCR_INIT_ATTEMPTED:
        return None
    OCR_INIT_ATTEMPTED = True

    tess_path = _find_tesseract()
    if tess_path:
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = tess_path
            logger.info(f"pytesseract configured with: {tess_path}")
        except Exception:
            pass

    logger.info("Trying PaddleOCR...")
    engine = _try_init_paddleocr()
    if engine:
        OCR_ENGINE = engine
        OCR_ENGINE_TYPE = "paddleocr"
        logger.info("OCR engine: PaddleOCR")
        return OCR_ENGINE

    logger.info("Trying EasyOCR...")
    engine = _try_init_easyocr()
    if engine:
        OCR_ENGINE = engine
        OCR_ENGINE_TYPE = "easyocr"
        logger.info("OCR engine: EasyOCR")
        return OCR_ENGINE

    if tess_path:
        OCR_ENGINE_TYPE = "pytesseract"
        logger.info("OCR engine: pytesseract (fallback)")
        return "pytesseract"

    logger.info("OCR engine: contour-only (no text output)")
    OCR_ENGINE_TYPE = "contour"
    return None


def get_vehicle_classes():
    return ["car", "motorcycle", "bus", "truck"]


def detect_vehicles(frame, conf_threshold=0.4):
    model = load_vehicle_detector()
    if model is None:
        return _fallback_detect_vehicles(frame, conf_threshold)

    results = model(frame, verbose=False, conf=conf_threshold)
    detections = []
    class_map = {
        "car": "car", "motorcycle": "motorcycle", "motorbike": "motorcycle",
        "bus": "bus", "truck": "truck", "bicycle": "bicycle",
        "auto_rickshaw": "auto-rickshaw", "auto": "auto-rickshaw",
        "person": None, "traffic light": None, "stop sign": None,
    }

    for result in results:
        for box in result.boxes:
            cls_id = int(box.cls[0])
            cls_name = result.names.get(cls_id, "unknown").lower()
            mapped = class_map.get(cls_name, cls_name)
            if mapped is None:
                continue
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            detections.append({
                "bbox": [x1, y1, x2, y2],
                "class": mapped,
                "confidence": conf,
            })
    return detections


def _fallback_detect_vehicles(frame, conf_threshold=0.3):
    import cv2
    import numpy as np

    detections = []
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        edges = cv2.Canny(blurred, 50, 150)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        dilated = cv2.dilate(edges, kernel, iterations=2)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 800:
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            aspect = bw / bh if bh > 0 else 0
            if 0.3 < aspect < 5.0 and bw > 30 and bh > 20:
                confidence = min(0.75, area / (w * h) * 10 + 0.35)
                detections.append({
                    "bbox": [float(x), float(y), float(x + bw), float(y + bh)],
                    "class": "car",
                    "confidence": round(confidence, 3),
                })

        seen = set()
        filtered = []
        for det in sorted(detections, key=lambda d: -d["confidence"]):
            bbox = det["bbox"]
            cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
            key = (round(cx / 60), round(cy / 60))
            if key not in seen:
                seen.add(key)
                filtered.append(det)
            if len(filtered) >= 15:
                break

        detections = filtered

    except Exception as e:
        logger.warning(f"Fallback detection failed: {e}")

    return detections


def detect_plate(frame, vehicle_bbox, conf_threshold=0.3):
    model = load_plate_detector()
    if model is not None and model is not False:
        return _detect_plate_with_yolo(model, frame, vehicle_bbox, conf_threshold)

    return _fallback_detect_plate(frame, vehicle_bbox)


def _detect_plate_with_yolo(model, frame, vehicle_bbox, conf_threshold=0.3):
    import cv2

    x1, y1, x2, y2 = [int(v) for v in vehicle_bbox]
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    crop = frame[y1:y2, x1:x2]

    if crop.size == 0:
        return None

    results = model(crop, verbose=False, conf=conf_threshold)
    for result in results:
        for box in result.boxes:
            bx1, by1, bx2, by2 = box.xyxy[0].tolist()
            plate_bbox = [
                x1 + bx1, y1 + by1,
                x1 + bx2, y1 + by2
            ]
            plate_crop = crop[int(by1):int(by2), int(bx1):int(bx2)]
            return {
                "bbox": plate_bbox,
                "confidence": float(box.conf[0]),
                "crop": plate_crop,
            }
    return None


def _fallback_detect_plate(frame, vehicle_bbox):
    import cv2
    import numpy as np

    x1, y1, x2, y2 = [int(v) for v in vehicle_bbox]
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    crop = frame[y1:y2, x1:x2]

    if crop.size == 0:
        return None

    try:
        gh, gw = crop.shape[:2]
        plate_region = crop[int(gh * 0.4):int(gh * 0.9), int(gw * 0.05):int(gw * 0.95)]
        if plate_region.size == 0:
            return None

        gray = cv2.cvtColor(plate_region, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 200)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best_rect = None
        best_area = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 200:
                continue
            x, y, rw, rh = cv2.boundingRect(cnt)
            aspect = rw / rh if rh > 0 else 0
            if 1.5 < aspect < 6.0 and rh > 10:
                if area > best_area:
                    best_area = area
                    best_rect = (x, y, rw, rh)

        if best_rect:
            bx, by, bw, bh = best_rect
            plate_crop = plate_region[by:by + bh, bx:bx + bw]
            plate_bbox = [
                float(x1 + int(gw * 0.05) + bx),
                float(y1 + int(gh * 0.4) + by),
                float(x1 + int(gw * 0.05) + bx + bw),
                float(y1 + int(gh * 0.4) + by + bh),
            ]
            return {
                "bbox": plate_bbox,
                "confidence": 0.4,
                "crop": plate_crop,
            }
    except Exception as e:
        logger.warning(f"Fallback plate detection failed: {e}")

    return None


def run_ocr(plate_image, conf_threshold=0.5):
    if plate_image is None or plate_image.size == 0:
        return {"raw_text": None, "plate_text": None, "confidence": 0.0}

    engine = load_ocr_engine()

    if engine is not None and OCR_ENGINE_TYPE == "paddleocr":
        return _ocr_with_paddleocr(engine, plate_image)
    elif engine is not None and OCR_ENGINE_TYPE == "easyocr":
        return _ocr_with_easyocr(engine, plate_image)
    elif engine == "pytesseract":
        return _ocr_with_pytesseract(plate_image)

    return {"raw_text": None, "plate_text": None, "confidence": 0.0}


def _ocr_with_paddleocr(engine, plate_image):
    import cv2

    if len(plate_image.shape) == 2:
        img = plate_image
    else:
        img = cv2.cvtColor(plate_image, cv2.COLOR_BGR2GRAY)

    try:
        results = engine.ocr(img, cls=True)
        texts = []
        if results and results[0]:
            for line in results[0]:
                text = line[1][0]
                conf = float(line[1][1])
                texts.append((text, conf))

        if not texts:
            return {"raw_text": None, "plate_text": None, "confidence": 0.0}

        raw_text = " ".join(t[0] for t in texts)
        avg_conf = sum(t[1] for t in texts) / len(texts)

        plate_text = raw_text.upper().replace(" ", "").replace(".", "")
        plate_text = "".join(c for c in plate_text if c.isalnum())

        return {
            "raw_text": raw_text,
            "plate_text": plate_text if len(plate_text) >= 3 else None,
            "confidence": round(avg_conf, 4),
        }
    except Exception as e:
        logger.warning(f"PaddleOCR failed: {e}")
        return {"raw_text": None, "plate_text": None, "confidence": 0.0}


def _ocr_with_easyocr(reader, plate_image):
    import cv2
    import numpy as np

    try:
        if len(plate_image.shape) == 2:
            img = plate_image
        else:
            img = cv2.cvtColor(plate_image, cv2.COLOR_BGR2GRAY)

        img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

        results = reader.readtext(img)
        texts = []
        for (bbox, text, conf) in results:
            texts.append((text, conf))

        if not texts:
            return {"raw_text": None, "plate_text": None, "confidence": 0.0}

        raw_text = " ".join(t[0] for t in texts)
        avg_conf = sum(t[1] for t in texts) / len(texts)

        plate_text = raw_text.upper().replace(" ", "").replace(".", "")
        plate_text = "".join(c for c in plate_text if c.isalnum())

        return {
            "raw_text": raw_text,
            "plate_text": plate_text if len(plate_text) >= 3 else None,
            "confidence": round(avg_conf, 4),
        }
    except Exception as e:
        logger.warning(f"EasyOCR failed: {e}")
        return {"raw_text": None, "plate_text": None, "confidence": 0.0}


def _ocr_with_pytesseract(plate_image):
    import cv2
    import numpy as np

    try:
        import pytesseract

        if len(plate_image.shape) == 3:
            gray = cv2.cvtColor(plate_image, cv2.COLOR_BGR2GRAY)
        else:
            gray = plate_image.copy()

        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        kernel = np.ones((2, 2), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        text = pytesseract.image_to_string(
            binary,
            config='--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        )
        text = text.strip().upper().replace(" ", "")
        text = "".join(c for c in text if c.isalnum())

        if len(text) >= 3:
            return {
                "raw_text": text,
                "plate_text": text,
                "confidence": 0.45,
            }

        return {"raw_text": text or None, "plate_text": None, "confidence": 0.0}
    except Exception as e:
        logger.warning(f"pytesseract OCR failed: {e}")
        return {"raw_text": None, "plate_text": None, "confidence": 0.0}


def compute_reid_embedding(vehicle_crop):
    model = load_reid_model()
    if vehicle_crop is None or vehicle_crop.size == 0:
        return None

    try:
        import cv2
        import numpy as np
        resized = cv2.resize(vehicle_crop, (128, 256))
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        cv2.normalize(hist, hist)
        embedding = hist.flatten()
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding.tobytes()
    except Exception as e:
        logger.warning(f"Re-ID embedding failed: {e}")
        return None


def cosine_similarity_bytes(a_bytes, b_bytes):
    import numpy as np
    if a_bytes is None or b_bytes is None:
        return 0.0
    try:
        a = np.frombuffer(a_bytes, dtype=np.float32)
        b = np.frombuffer(b_bytes, dtype=np.float32)
        if len(a) != len(b):
            return 0.0
        return float(np.dot(a, b))
    except Exception:
        return 0.0


VEHICLE_CLASSES = get_vehicle_classes()
