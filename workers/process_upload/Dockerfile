# process_upload worker — CSV downsampling + session analysis.
# AWS Lambda base image: the same image deploys to Lambda (container image) and
# runs locally via the bundled Runtime Interface Emulator:
#   docker run -p 9000:8080 xgsail-process-upload
#   curl -XPOST localhost:9000/2015-03-31/functions/function/invocations -d @event.json
#
# NOTE: build context is the REPO ROOT (see docker-compose.yml /
# scripts/build-images.sh), not this directory, so the shared
# libs/xgsail_windfusion package is reachable. All COPY paths below are
# therefore relative to the repo root.
FROM public.ecr.aws/lambda/python:3.12

COPY workers/process_upload/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Shared wind-fusion math (also used by the backend). Installed into
# site-packages so `import xgsail_windfusion` resolves like any dep.
COPY libs/xgsail_windfusion/ /tmp/xgsail_windfusion/
RUN pip install --no-cache-dir /tmp/xgsail_windfusion

# handler.py + analyzer.py + processing/ (the analytics library moved here from
# the backend so the API stays pure-serving).
COPY workers/process_upload/ ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]
