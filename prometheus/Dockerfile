FROM prom/prometheus:latest

COPY prometheus.yml /etc/prometheus/prometheus.yml.template

RUN apk add --no-cache gettext

EXPOSE 9090

CMD ["sh", "-c", "envsubst < /etc/prometheus/prometheus.yml.template > /etc/prometheus/prometheus.yml && prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus"]
