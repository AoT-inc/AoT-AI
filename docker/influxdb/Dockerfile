FROM influxdb:1.8.10

ENV DOCKER_CONTAINER TRUE

RUN mkdir -pv /var/influxdb/data

COPY ./docker/influxdb/run.sh /home/aot-ai/docker/influxdb/run.sh
RUN chmod +x /home/aot-ai/docker/influxdb/run.sh

ENV PRE_CREATE_DB aot-ai_db
ENV ADMIN_USER aot-ai
ENV PASS mmdu77sj3nIoiajjs

EXPOSE 8086

CMD /home/aot-ai/docker/influxdb/run.sh
