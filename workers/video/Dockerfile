# video worker — MP4 → HLS via ffmpeg.
# AWS Lambda base image (same image runs on Lambda and locally via RIE):
#   docker run -p 9000:8080 xgsail-video
#   curl -XPOST localhost:9000/2015-03-31/functions/function/invocations -d @event.json
FROM public.ecr.aws/lambda/python:3.12

# Static ffmpeg build (AL2023 has no ffmpeg package). Pinned to a static release
# so the binary is self-contained and identical on Lambda + local. curl already
# ships in the base image (curl-minimal) — installing it conflicts, so we don't.
RUN dnf install -y tar xz \
    && curl -sL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -o /tmp/ffmpeg.tar.xz \
    && tar -xf /tmp/ffmpeg.tar.xz -C /tmp \
    && cp /tmp/ffmpeg-*-amd64-static/ffmpeg /usr/local/bin/ffmpeg \
    && chmod +x /usr/local/bin/ffmpeg \
    && rm -rf /tmp/ffmpeg* \
    && dnf clean all

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY . ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]
