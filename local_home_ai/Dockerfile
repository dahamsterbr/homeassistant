ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /opt/local_home_ai

COPY requirements.txt /tmp/requirements.txt
RUN apk add --no-cache \
        bash \
        curl \
        jq \
        mosquitto-clients \
    && pip3 install --break-system-packages -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

COPY rootfs/app /opt/local_home_ai/app
COPY rootfs/run.sh /run.sh
COPY custom_components /opt/local_home_ai/custom_components

RUN chmod a+x /run.sh

LABEL \
    io.hass.name="Local Home AI" \
    io.hass.description="Local LM Studio presence fusion and learning for Home Assistant" \
    io.hass.type="addon" \
    io.hass.version="1.0.1"

CMD ["/run.sh"]
