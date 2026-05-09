# coding=utf-8
from typing import List, Dict

# === 현대적 통합 백엔드 ===
CAMERA_TYPES = {
    # Raspberry Pi
    'rpi_csi': {
        'type': 'rpi_csi',
        'display_name': 'Raspberry Pi CSI Camera Module',
        'description': 'Raspberry Pi Camera Module v2/v3 (CSI 인터페이스)',
        'category': 'modern',
        'platform': 'raspberry_pi',
        'backend': 'libcamera',
        'library': 'picamera2',
        'requirements': [
            ('pip-pypi', 'picamera2', 'picamera2'),
            ('pip-pypi', 'opencv-python', 'opencv-python>=4.8.0')
        ],
        'device_detection': 'libcamera-hello --list-cameras',
        'supported_features': ['high_fps', 'hardware_acceleration', 'hdr']
    },

    # 범용 USB 웹캠
    'usb_webcam': {
        'type': 'usb_webcam',
        'display_name': 'USB 웹캠',
        'description': 'USB 연결 웹캠 (범용)',
        'category': 'modern',
        'platform': 'all',
        'backend': 'opencv',
        'library': 'opencv-python',
        'requirements': [
            ('pip-pypi', 'opencv-python', 'opencv-python>=4.8.0')
        ],
        'device_detection': 'v4l2-ctl --list-devices',
        'supported_features': ['auto_focus', 'auto_exposure']
    },

    # PC 내장 웹캠
    'builtin_webcam': {
        'type': 'builtin_webcam',
        'display_name': '내장 웹캠',
        'description': '노트북/PC 내장 웹캠',
        'category': 'modern',
        'platform': 'debian_pc',
        'backend': 'opencv',
        'library': 'opencv-python',
        'requirements': [
            ('pip-pypi', 'opencv-python', 'opencv-python>=4.8.0')
        ],
        'device_detection': 'v4l2-ctl --list-devices',
        'supported_features': ['auto_focus', 'auto_exposure']
    },

    # 가상 카메라
    'virtual_camera': {
        'type': 'virtual_camera',
        'display_name': '가상 카메라 (v4l2loopback)',
        'description': 'v4l2loopback 가상 카메라 장치',
        'category': 'modern',
        'platform': 'debian_pc',
        'backend': 'opencv',
        'library': 'opencv-python',
        'requirements': [
            ('pip-pypi', 'opencv-python', 'opencv-python>=4.8.0'),
            ('apt', 'v4l2loopback-dkms', 'v4l2loopback-dkms')
        ],
        'device_detection': 'v4l2-ctl --list-devices | grep v4l2loopback',
        'supported_features': ['custom_resolution', 'custom_fps']
    },

    # IP 카메라
    'ip_camera': {
        'type': 'ip_camera',
        'display_name': 'IP 카메라 (ONVIF/RTSP)',
        'description': 'ONVIF 프로토콜 지원 IP 카메라',
        'category': 'modern',
        'platform': 'all',
        'backend': 'onvif',
        'library': 'python-onvif-zeep',
        'requirements': [
            ('pip-pypi', 'opencv-python', 'opencv-python>=4.8.0'),
            ('pip-pypi', 'python-onvif-zeep', 'python-onvif-zeep>=0.2.12')
        ],
        'device_detection': 'onvif_discovery',
        'supported_features': ['ptz', 'remote_access', 'high_resolution']
    },

    # 스트리밍 URL
    'stream_url': {
        'type': 'stream_url',
        'display_name': '스트리밍 URL (RTSP/HTTP)',
        'description': 'RTSP/HTTP 스트리밍 URL',
        'category': 'modern',
        'platform': 'all',
        'backend': 'opencv',
        'library': 'opencv-python',
        'requirements': [
            ('pip-pypi', 'opencv-python', 'opencv-python>=4.8.0')
        ],
        'device_detection': 'manual',
        'supported_features': ['remote_access', 'low_latency']
    },

    # Docker USB 패스스루
    'usb_passthrough': {
        'type': 'usb_passthrough',
        'display_name': '호스트 USB 카메라 (Docker)',
        'description': '도커 호스트의 USB 카메라 (device passthrough)',
        'category': 'modern',
        'platform': 'docker',
        'backend': 'opencv',
        'library': 'opencv-python',
        'requirements': [
            ('pip-pypi', 'opencv-python', 'opencv-python>=4.8.0')
        ],
        'device_detection': 'v4l2-ctl --list-devices',
        'docker_config': {
            'devices': ['/dev/video0:/dev/video0'],
            'privileged': False
        },
        'supported_features': ['auto_focus', 'auto_exposure']
    },

    # === 레거시 백엔드 (호환성 유지) ===
    'fswebcam': {
        'type': 'fswebcam',
        'display_name': 'USB 웹캠 (fswebcam) [Legacy]',
        'description': 'fswebcam CLI 기반 USB 웹캠 캡처',
        'category': 'legacy',
        'platform': 'all',
        'backend': 'fswebcam',
        'library': 'fswebcam',
        'requirements': [
            ('apt', 'fswebcam', 'fswebcam')
        ],
        'deprecated': True,
        'recommended_alternative': 'usb_webcam',
        'deprecation_message': 'fswebcam은 더 이상 권장되지 않습니다. OpenCV 기반 USB 웹캠을 사용하세요.'
    },

    'raspistill': {
        'type': 'raspistill',
        'display_name': 'Raspberry Pi Camera (raspistill) [Legacy]',
        'description': 'raspistill CLI 기반 CSI 카메라 캡처',
        'category': 'legacy',
        'platform': 'raspberry_pi',
        'backend': 'raspistill',
        'library': 'raspistill',
        'requirements': [
            ('apt', 'libraspberrypi-bin', 'libraspberrypi-bin')
        ],
        'deprecated': True,
        'recommended_alternative': 'rpi_csi',
        'deprecation_message': 'raspistill은 더 이상 권장되지 않습니다. libcamera 기반 CSI 카메라를 사용하세요.'
    },

    'picamera': {
        'type': 'picamera',
        'display_name': 'Raspberry Pi Camera (picamera v1) [Legacy]',
        'description': 'picamera v1 라이브러리 기반 CSI 카메라',
        'category': 'legacy',
        'platform': 'raspberry_pi',
        'backend': 'picamera',
        'library': 'picamera',
        'requirements': [
            ('pip-pypi', 'picamera', 'picamera')
        ],
        'deprecated': True,
        'recommended_alternative': 'rpi_csi',
        'deprecation_message': 'picamera v1은 더 이상 권장되지 않습니다. picamera2를 사용하세요.'
    },

    'url_urllib': {
        'type': 'url_urllib',
        'display_name': 'URL 스트림 (urllib) [Legacy]',
        'description': 'urllib 기반 URL 이미지/스트림 캡처',
        'category': 'legacy',
        'platform': 'all',
        'backend': 'urllib',
        'library': 'urllib',
        'requirements': [],  # 내장 라이브러리
        'deprecated': True,
        'recommended_alternative': 'stream_url',
        'deprecation_message': 'urllib 기반 스트림은 더 이상 권장되지 않습니다. OpenCV 기반 스트림을 사용하세요.'
    },

    'url_requests': {
        'type': 'url_requests',
        'display_name': 'URL 스트림 (requests) [Legacy]',
        'description': 'requests 라이브러리 기반 URL 이미지/스트림 캡처',
        'category': 'legacy',
        'platform': 'all',
        'backend': 'requests',
        'library': 'requests',
        'requirements': [
            ('pip-pypi', 'requests', 'requests')
        ],
        'deprecated': True,
        'recommended_alternative': 'stream_url',
        'deprecation_message': 'requests 기반 스트림은 더 이상 권장되지 않습니다. OpenCV 기반 스트림을 사용하세요.'
    }
}

CAPTURE_MODES = {
    'snapshot': {
        'name': 'Photo (Snapshot)',
        'description': 'Single image capture',
        'settings': ['resolution', 'quality', 'format']
    },
    'timelapse': {
        'name': 'Timelapse',
        'description': 'Interval image capture',
        'settings': ['resolution', 'interval', 'duration', 'format']
    },
    'video': {
        'name': 'Video',
        'description': 'Continuous video recording',
        'settings': ['resolution', 'fps', 'duration', 'codec']
    },
    'stream': {
        'name': 'Live Stream',
        'description': 'Real-time live streaming',
        'settings': ['resolution', 'fps', 'bitrate', 'protocol']
    }
}
