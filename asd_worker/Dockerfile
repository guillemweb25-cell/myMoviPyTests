# Worker de ASD (TalkNet) para la RTX 4060 Ti. Base = la misma que ya está cacheada
# en la máquina (local_tts_api), para no re-descargar del registry.
FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

# Sin prompts interactivos (tzdata al instalar ffmpeg bloqueaba el build).
ENV DEBIAN_FRONTEND=noninteractive TZ=Europe/Madrid

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ffmpeg wget libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN git clone --depth 1 https://github.com/TaoRuijie/TalkNet-ASD.git

WORKDIR /opt/TalkNet-ASD
# TODO en un solo pip install con versiones fijadas JUNTAS, para que numpy no lo
# suba una dependencia. numpy 1.23.5 = última con los alias np.int/np.float que usa
# el TalkNet antiguo (quitados en 1.24) y compatible con torch 2.1.0.
RUN pip install --no-cache-dir \
        "numpy==1.23.5" \
        "opencv-python==4.8.1.78" \
        "scipy==1.10.1" \
        "scikit-learn==1.2.2" \
        "pandas==1.5.3" \
        "scenedetect==0.6.0.3" \
        python_speech_features tqdm "gdown<5" \
        fastapi "uvicorn[standard]" python-multipart && \
    python -c "import numpy; assert numpy.__version__=='1.23.5', numpy.__version__; print('numpy', numpy.__version__, 'OK')"

# Modelo preentrenado de TalkNet (si el build no puede con gdown, se baja al 1er uso).
RUN gdown --id 1AbN9fCf9IexMxEKXLQY2KYBlb-IhSEea -O pretrain_TalkSet.model || \
    echo "Aviso: baja pretrain_TalkSet.model en el primer /asd si falla aqui."

# Nuestra API + conversor (se copian DENTRO del repo TalkNet para importar su código).
COPY app.py run_talknet.py /opt/TalkNet-ASD/

EXPOSE 8900
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8900"]
