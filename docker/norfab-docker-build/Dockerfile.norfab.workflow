FROM python:3.9-slim-trixie

RUN apt-get update && \
    apt-get clean && \
    pip install --no-cache-dir pip setuptools wheel poetry --upgrade

RUN pip install --no-cache-dir norfab --upgrade

ENV LOG_LEVEL=INFO
ENV WORKERS_LIST=

ENTRYPOINT cd /etc/norfab/ && nfcli --workers-list $WORKERS_LIST -l $LOG_LEVEL