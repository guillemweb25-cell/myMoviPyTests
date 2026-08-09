# Worker de ASD (TalkNet) para la RTX 4060. Se ejecuta en WSL2 con --gpus all.
FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ffmpeg wget libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN git clone --depth 1 https://github.com/TaoRuijie/TalkNet-ASD.git

WORKDIR /opt/TalkNet-ASD
# Dependencias de TalkNet (su requirement.txt) + las de nuestra mini-API.
RUN pip install --no-cache-dir \
        scenedetect==0.6.2 opencv-python-headless python_speech_features \
        numpy scipy scikit-learn pandas tqdm gdown \
        fastapi "uvicorn[standard]" python-multipart

# Modelo preentrenado de TalkNet (si el build no puede con gdown, se baja al 1er uso).
RUN gdown --id 1AbN9fCf9IexMxEKXLQY2KYBlb-IhSEea -O pretrain_TalkSet.model || \
    echo "Aviso: baja pretrain_TalkSet.model en el primer /asd si falla aqui."

# Nuestra API + conversor (se copian DENTRO del repo TalkNet para importar su código).
COPY app.py run_talknet.py /opt/TalkNet-ASD/

EXPOSE 8900
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8900"]
