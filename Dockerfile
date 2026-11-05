# One image for all Python services (producer, processor, api, dashboard, trainer)
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    SECURELYTICS_ROOT=/app

# libgomp1 = OpenMP runtime needed by LightGBM and XGBoost
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# requirements-models.txt is optional: it is created by notebooks/train_on_colab.ipynb
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN for pkg in $(grep -v '^#' requirements-boosting.txt); do \
      pip install --no-cache-dir "$pkg" || echo "WARNING: could not install $pkg - that model will be skipped"; \
    done
# Match the exact library versions the models were trained with (e.g. on Colab)
RUN if [ -f requirements-models.txt ]; then \
      pip install --no-cache-dir -r requirements-models.txt; \
    fi

COPY src ./src
COPY services ./services
COPY storage ./storage
# models/, reports/ and data/ are mounted as volumes by docker-compose
