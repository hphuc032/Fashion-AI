"""Small CPU provider boundary for future optional inpainting implementations."""
from typing import Protocol

import cv2
import numpy as np


class InpaintingProvider(Protocol):
    def apply(self, image: np.ndarray, mask: np.ndarray, radius: int) -> np.ndarray: ...


class OpenCVInpainting:
    def apply(self, image, mask, radius):
        return cv2.inpaint(image, mask, radius, cv2.INPAINT_TELEA)
