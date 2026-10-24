import os
import cv2
import numpy as np
import threading
from django.conf import settings

class DeepFaceEngine:
    """
    Motor de Inferencia de Deep Learning para Detección y Reconocimiento Facial.
    - Detección y Alineación 5-Puntos: OpenCV YuNet (face_detection_yunet_2023mar.onnx)
    - Extracción de Características (128-d): SFace Deep Learning (face_recognition_sface_2021dec.onnx)
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        base_dir = getattr(settings, 'BASE_DIR', os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        self.yunet_path = os.path.join(base_dir, 'modelo', 'face_detection_yunet_2023mar.onnx')
        self.sface_path = os.path.join(base_dir, 'modelo', 'face_recognition_sface_2021dec.onnx')
        os.makedirs(os.path.join(base_dir, 'modelo'), exist_ok=True)
        if not os.path.exists(self.yunet_path) or not os.path.exists(self.sface_path):
            self._download_models(base_dir)

        self.detector = cv2.FaceDetectorYN.create(
            model=self.yunet_path,
            config='',
            input_size=(320, 320),
            score_threshold=0.55,
            nms_threshold=0.3,
            top_k=5000
        )

        self.recognizer = cv2.FaceRecognizerSF.create(
            model=self.sface_path,
            config=''
        )
        
        self.infer_lock = threading.Lock()

    def _download_models(self, base_dir):
        import urllib.request
        model_dir = os.path.join(base_dir, 'modelo')
        urls = {
            'face_detection_yunet_2023mar.onnx': 'https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx',
            'face_recognition_sface_2021dec.onnx': 'https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx'
        }
        for name, url in urls.items():
            path = os.path.join(model_dir, name)
            if not os.path.exists(path) or os.path.getsize(path) < 1000:
                print(f"[DeepFaceEngine] Descargando modelo {name}...")
                urllib.request.urlretrieve(url, path)
                print(f"[DeepFaceEngine] Modelo {name} descargado.")

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def detect_faces(self, frame_bgr):
        if frame_bgr is None or frame_bgr.size == 0:
            return []

        h, w = frame_bgr.shape[:2]
        with self.infer_lock:
            self.detector.setInputSize((w, h))
            _, faces = self.detector.detect(frame_bgr)
            
        if faces is None:
            return []
        return faces

    def align_and_extract_feature(self, frame_bgr, face_yunet):
        with self.infer_lock:
            aligned_face = self.recognizer.alignCrop(frame_bgr, face_yunet)
            feature = self.recognizer.feature(aligned_face)
            feature_norm = feature / (np.linalg.norm(feature) + 1e-7)
            return aligned_face, feature_norm.flatten()

    def extract_embedding_from_image(self, image_bgr):
        faces = self.detect_faces(image_bgr)
        if len(faces) == 0:
            h, w = image_bgr.shape[:2]
            with self.infer_lock:
                self.detector.setInputSize((w, h))
                self.detector.setScoreThreshold(0.3)
                _, faces = self.detector.detect(image_bgr)
                self.detector.setScoreThreshold(0.55)

        if faces is None or len(faces) == 0:
            return None, None

        best_face = max(faces, key=lambda f: f[2] * f[3])
        return self.align_and_extract_feature(image_bgr, best_face)

    def compute_similarity(self, feat1, feat2):
        if feat1 is None or feat2 is None:
            return 0.0
        return float(np.dot(feat1, feat2))

    def similarity_to_percentage(self, score):
        if score >= 0.50:
            return round(min(100.0, 85.0 + ((score - 0.50) / 0.50) * 15.0), 1)
        elif score >= 0.36:
            return round(65.0 + ((score - 0.36) / 0.14) * 20.0, 1)
        elif score >= 0.25:
            return round(45.0 + ((score - 0.25) / 0.11) * 20.0, 1)
        else:
            return round(max(0.0, (max(0.0, score) / 0.25) * 44.0), 1)

    def match_against_matrix(self, live_feat, matrix_embeddings, persona_ids):
        if matrix_embeddings is None or len(persona_ids) == 0 or live_feat is None:
            return None, 0.0, 0.0

        scores = np.dot(matrix_embeddings, live_feat)
        best_idx = int(np.argmax(scores))
        best_score = float(scores[best_idx])
        best_persona_id = persona_ids[best_idx]
        best_percent = self.similarity_to_percentage(best_score)

        return best_persona_id, best_score, best_percent
