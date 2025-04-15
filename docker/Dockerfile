FROM debian:stable-slim

ENV DOCKER_CONTAINER TRUE

RUN useradd -ms /bin/bash pi
RUN useradd -ms /bin/bash aot-ai

COPY ./aot-ai/scripts/upgrade_commands.sh /home/aot-ai/aot-ai/scripts/upgrade_commands.sh

RUN /home/aot-ai/aot-ai/scripts/upgrade_commands.sh docker-create-files-directories-symlinks
RUN /home/aot-ai/aot-ai/scripts/upgrade_commands.sh update-apt
RUN /home/aot-ai/aot-ai/scripts/upgrade_commands.sh update-packages
RUN /home/aot-ai/aot-ai/scripts/upgrade_commands.sh ssl-certs-generate
RUN /home/aot-ai/aot-ai/scripts/upgrade_commands.sh install-docker

COPY ./install/requirements.txt /home/aot-ai/install

RUN /home/aot-ai/aot-ai/scripts/upgrade_commands.sh docker-update-pip
RUN /home/aot-ai/aot-ai/scripts/upgrade_commands.sh docker-update-pip-packages

COPY . /home/aot-ai
WORKDIR /home/aot-ai/aot-ai

RUN /home/aot-ai/aot-ai/scripts/upgrade_commands.sh docker-compile-translations
RUN /home/aot-ai/aot-ai/scripts/upgrade_commands.sh compile-aot-ai-wrapper
