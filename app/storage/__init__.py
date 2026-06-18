"""Storage-pakket: opslag van geüploade media op het /app/data-volume.

FOUNDATION levert de skeleton (signatures + paden + ``UploadError``); SERVICES
vult de Pillow-bodies (validatie/EXIF-strip/resize/opslag) in ``photos.py``.
"""
