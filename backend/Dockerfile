FROM python:3.11-slim

WORKDIR /workspace/backend

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /workspace/backend/requirements.txt
RUN pip install --no-cache-dir -r /workspace/backend/requirements.txt
RUN pip install --no-cache-dir ofscraper
RUN python -c "from pathlib import Path; target = Path('/usr/local/lib/python3.11/site-packages/ofscraper/utils/of_env/of_env.py'); source = target.read_text(encoding='utf-8'); old = \"\"\"def getattr(val):\n    \\\"\\\"\\\"\n    Retrieves a configuration value.\n    Order of precedence: Environment Variable > Custom Config > Default Config.\n    \\\"\\\"\\\"\n    # Load all settings if not already loaded\n    config_dict = get_all_configs()\n    # 1. Check Environment Variable\n    env_val = os.environ.get(val)\n    if env_val is not None:\n        return env_val\n    if val in config_dict:  # Check if key exists in the aggregated settings\n        return config_dict.get(val)\n    return None  # Or raise KeyError(f\\\"Configuration key '{val}' not found.\\\")\n\"\"\"; new = \"\"\"def getattr(val, default=None):\n    \\\"\\\"\\\"\n    Retrieves a configuration value.\n    Order of precedence: Environment Variable > Custom Config > Default Config.\n    \\\"\\\"\\\"\n    # Load all settings if not already loaded\n    config_dict = get_all_configs()\n    # 1. Check Environment Variable\n    env_val = os.environ.get(val)\n    if env_val is not None:\n        return env_val\n    if val in config_dict:  # Check if key exists in the aggregated settings\n        return config_dict.get(val)\n    return default\n\"\"\"; assert old in source, 'No se encontro el bloque esperado para parchear ofscraper'; target.write_text(source.replace(old, new), encoding='utf-8')"

COPY backend /workspace/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
