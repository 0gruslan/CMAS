FROM alpine:3.19 AS envsubst
RUN apk add --no-cache gettext
COPY prometheus/prometheus.yml /tmp/prometheus.yml.template

FROM prom/prometheus:latest
COPY --from=envsubst /usr/bin/envsubst /usr/bin/envsubst
COPY --from=envsubst /tmp/prometheus.yml.template /etc/prometheus/prometheus.yml.template

EXPOSE 9090

ENTRYPOINT ["sh", "-c", "envsubst < /etc/prometheus/prometheus.yml.template > /etc/prometheus/prometheus.yml && prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus"]
