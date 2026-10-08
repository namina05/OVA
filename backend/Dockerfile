FROM python:3.13-slim

# XGBoost needs the OpenMP runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Trained models are not kept in git, so the image trains its own: the cycle models on
# the FedCycleData set, the heat-therapy model on synthetic sessions (see README).
RUN python -m ml.training.train --synthetic --out models/current \
    && python -m ml.cycle.train --dataset data/fedcycledata/FedCycleData071012.csv --out models/cycle

# The host says which port to listen on.
ENV PORT=8000
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
