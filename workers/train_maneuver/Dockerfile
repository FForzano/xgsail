# train_maneuver worker — manual training run for the Stage 2 ML maneuver
# classifier (see workers/process_upload/processing/maneuver_classification.py).
#
# Unlike process_upload/video this is NOT a Lambda: nothing invokes it on an
# event, so it's a plain Python image, invoked by hand:
#   docker compose --profile training run --rm train_maneuver \
#       python -m workers.train_maneuver.train --data /data/maneuvers.csv --output /data/model
#
# Build context is the REPO ROOT (see docker-compose.yml), not this
# directory, so `workers.process_upload.processing.maneuver_features` (the
# single source of truth for the feature list — see dataset.py) is reachable
# as a namespace package under the same /app/workers/... layout it has in
# the repo, instead of duplicating the feature list here.
FROM python:3.12-slim

WORKDIR /app

COPY workers/train_maneuver/requirements.txt /app/workers/train_maneuver/requirements.txt
RUN pip install --no-cache-dir -r /app/workers/train_maneuver/requirements.txt

COPY workers/process_upload/processing/ /app/workers/process_upload/processing/
COPY workers/train_maneuver/ /app/workers/train_maneuver/

CMD ["python", "-m", "workers.train_maneuver.train", "--help"]
