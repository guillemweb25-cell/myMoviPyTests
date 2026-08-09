# Worker de detección de personas (YOLOv8). Contenedor APARTE del de TalkNet para
# no chocar con su numpy pineado. Misma base cacheada -> no re-descarga del registry.
FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir ultralytics fastapi "uvicorn[standard]" python-multipart

# Baja los pesos yolov8s para que el primer /persons no espere.
RUN python -c "from ultralytics import YOLO; YOLO('yolov8s.pt')"

WORKDIR /app
COPY app.py detect_persons.py /app/

EXPOSE 8901
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8901"]
