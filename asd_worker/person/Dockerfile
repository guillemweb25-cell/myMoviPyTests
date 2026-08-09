# Worker de detección de personas (YOLOv8). Contenedor APARTE del de TalkNet para
# no chocar con su numpy pineado. Misma base cacheada -> no re-descarga del registry.
FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# numpy<2: torch 2.1.0 se compiló contra numpy 1.x (ultralytics trae numpy 2 y
# rompe torch con "Numpy is not available").
RUN pip install --no-cache-dir "numpy<2" ultralytics fastapi "uvicorn[standard]" python-multipart && \
    python -c "import numpy,torch; assert numpy.__version__[0]=='1', numpy.__version__; print('numpy',numpy.__version__,'torch',torch.__version__,'OK')"

# Baja los pesos yolov8s para que el primer /persons no espere.
RUN python -c "from ultralytics import YOLO; YOLO('yolov8s.pt')"

WORKDIR /app
COPY app.py detect_persons.py /app/

EXPOSE 8901
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8901"]
