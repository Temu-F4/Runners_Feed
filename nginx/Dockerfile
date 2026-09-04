FROM nginx:1.27-alpine

ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG BUILD_SOURCE=https://github.com/Temu-F4/Runners_Feed

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="${BUILD_SOURCE}"

COPY nginx/templates/default.conf.template /etc/nginx/templates/default.conf.template
