"""Prepare default RapidOCR models before building an offline package."""
from rapidocr import RapidOCR

if __name__ == '__main__':
    RapidOCR()
    print('RapidOCR initialized; default models are cached in this environment.')

