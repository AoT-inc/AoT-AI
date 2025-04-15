# -*- coding: utf-8 -*-
# From https://github.com/miguelgrinberg/flask-video-streaming
import logging
import time

import cv2

from aot-ai.aot-ai_flask.camera.base_camera import BaseCamera

logger = logging.getLogger(__name__)


class Camera(BaseCamera):
    camera_options = None

    @staticmethod
    def set_camera_options(camera_options):
        logger.info("Setting camera options")
        Camera.camera_options = camera_options

    @staticmethod
    def frames():
        settings = Camera.camera_options
 
        camera = cv2.VideoCapture(settings.url_stream)
        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        camera.set(cv2.CAP_PROP_FPS, settings.stream_fps)
 
        if not camera.isOpened():
            raise RuntimeError('Could not start camera.')
 
        wait_period = float(1 / settings.stream_fps)
 
        while True:
            ret, img = camera.read()
            if not ret or img is None:
                logger.warning("Camera read failed. Retrying...")
                time.sleep(0.5)
                continue
            yield cv2.imencode('.jpg', img)[1].tobytes()
            time.sleep(wait_period)
