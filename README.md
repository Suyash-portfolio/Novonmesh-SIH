# NAVONMESH Sightlines — SIH26127

City-Wide AI Engine for Multi-Camera ANPR & Vehicle Tracking

## Features

- Real YOLO vehicle detection
- Dedicated license plate detection
- OCR (PaddleOCR / EasyOCR / Tesseract fallback)
- ByteTrack object tracking
- Global Vehicle ID (cross-camera association)
- Custom Leaflet city road map trajectory
- Analytics dashboard
- Blacklist & alerts
- Video upload & background processing

## Local Development

```bash
python run.py
```

Opens at http://127.0.0.1:5000

## Render Deployment

1. Push this repository to GitHub
2. Create a new Web Service on Render
3. Connect your GitHub repository
4. Render will auto-detect `render.yaml`
5. Or manually configure:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`
   - **Health Check:** `/health`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | auto-generated | Flask secret key |
| `PORT` | 5000 (local) / $PORT (Render) | Server port |
| `DATABASE_URL` | SQLite | Database connection URL |
| `FRAME_SKIP` | 3 | Process every Nth frame |
| `CONFIDENCE_THRESHOLD` | 0.4 | YOLO confidence threshold |
| `OCR_INTERVAL` | 1 | OCR every N detections |
| `MAX_UPLOAD_MB` | 2048 | Max upload size in MB |
| `VEHICLE_MODEL_PATH` | yolov8n.pt | Vehicle detection model |
| `PLATE_MODEL_PATH` | models/license_plate.pt | Plate detection model |

## AI Models

Models are downloaded automatically on first run:
- `yolov8n.pt` — Vehicle detection (auto-downloaded)
- `models/license_plate.pt` — Plate detection (included)
- `osnet_x1_0.pth` — Re-ID (optional, appearance fallback used)

## Tech Stack

- Python 3.11 / Flask
- SQLAlchemy / SQLite
- Ultralytics YOLO
- PaddleOCR
- ByteTrack
- Leaflet.js (custom city map)
- Chart.js
