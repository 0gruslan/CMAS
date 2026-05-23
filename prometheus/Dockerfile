FROM alpine:3.19

RUN apk add --no-cache gettext wget tar

RUN wget -qO /tmp/prometheus.tar.gz \
    https://github.com/prometheus/prometheus/releases/download/v2.51.0/prometheus-2.51.0.linux-amd64.tar.gz && \
    tar -xzf /tmp/prometheus.tar.gz -C /tmp && \
    mv /tmp/prometheus-2.51.0.linux-amd64/prometheus /usr/local/bin/ && \
    mv /tmp/prometheus-2.51.0.linux-amd64/promtool /usr/local/bin/ && \
    rm -rf /tmp/prometheus*

COPY prometheus.yml /etc/prometheus/prometheus.yml.template

EXPOSE 9090

CMD ["sh", "-c", "envsubst < /etc/prometheus/prometheus.yml.template > /etc/prometheus/prometheus.yml && prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus"]
