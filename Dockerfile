FROM 192.168.1.11:8085/tasks-rt:latest

# docker build -t 192.168.1.11:8085/tasks .
# docker push 192.168.1.11:8085/tasks

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG C.UTF-8

WORKDIR /opt/
COPY . .
RUN python -m compileall -b /opt/

ENV UVICORN_TIMEOUT_KEEP_ALIVE                      20
ENV TZ                                              "Asia/Shanghai"

EXPOSE 8080
ENTRYPOINT ["python","server.pyc"]