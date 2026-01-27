FROM alpine:latest

RUN apk add --no-cache curl tzdata

ENV TZ=America/Lima
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

RUN mkdir -p /var/log

COPY sync.sh /sync.sh
COPY crontab /etc/crontabs/root

RUN chmod +x /sync.sh

CMD ["crond", "-f", "-l", "2"]
