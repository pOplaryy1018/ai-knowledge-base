import hashlib
from pathlib import Path

import pytest
from PIL import Image

from app.services.connectors import image as connector
from app.services.connectors.types import ConnectorError


def picture(path: Path, fmt: str = 'PNG', color: str = 'red') -> Path:
    with Image.new('RGB', (8, 6), color) as img:
        img.save(path, format=fmt)
    return path


@pytest.mark.parametrize(('suffix', 'fmt'), [('.png', 'PNG'), ('.jpg', 'JPEG'), ('.webp', 'WEBP')])
def test_valid_images_preserve_original_bytes(tmp_path, suffix, fmt):
    path = picture(tmp_path / ('image' + suffix), fmt)
    validated = connector.validate_image(path)
    assert validated.original_bytes == path.read_bytes()
    assert validated.image_hash == hashlib.sha256(path.read_bytes()).hexdigest()
    assert (validated.width, validated.height) == (8, 6)


@pytest.mark.parametrize('case', ['extension', 'mismatch', 'corrupt', 'oversize', 'pixels', 'animated'])
def test_invalid_images_rejected(tmp_path, case):
    path = picture(tmp_path / 'image.png')
    if case == 'extension':
        path = path.rename(path.with_suffix('.gif'))
    elif case == 'mismatch':
        path = path.rename(path.with_suffix('.jpg'))
    elif case == 'corrupt':
        path.write_bytes(b'not an image')
    elif case == 'oversize':
        with path.open('ab') as stream:
            stream.write(b'0' * (10 * 1024 * 1024))
    elif case == 'pixels':
        with Image.new('1', (5001, 4000)) as img:
            img.save(path)
    else:
        with Image.new('RGB', (8, 6), 'red') as first, Image.new('RGB', (8, 6), 'blue') as second:
            first.save(path, save_all=True, append_images=[second])
    with pytest.raises(ConnectorError):
        connector.validate_image(path)


def test_ocr_failure_and_no_text_save_valid_original(tmp_path):
    path = picture(tmp_path / 'image.png')

    def unavailable(img):
        raise RuntimeError('secret executable path')

    failed = connector.collect_image(path, ocr_runner=unavailable)
    assert failed.ocr_status == 'unavailable'
    assert failed.documents == []
    assert 'secret' not in str(failed.manifest)
    empty = connector.collect_image(path, ocr_runner=lambda img: ' \n')
    assert empty.ocr_status == 'no_text'
    assert failed.image_hash == empty.image_hash


def test_correction_replaces_retrieval_ocr_but_preserves_machine_channel(tmp_path):
    path = picture(tmp_path / 'image.png')
    snapshot = connector.collect_image(path, manual_description='diagram', ocr_correction='correct', ocr_runner=lambda img: 'machine')
    assert [(doc.logical_path, doc.text) for doc in snapshot.documents] == [('ocr_correction', 'correct'), ('manual_description', 'diagram')]
    assert snapshot.manifest['ocr_text'] == 'machine'
    assert [doc.locator['origin'] for doc in snapshot.documents] == ['image_ocr_correction', 'manual_description']
    assert all(doc.locator['image_hash'] == snapshot.image_hash for doc in snapshot.documents)
    assert all('x' not in doc.locator for doc in snapshot.documents)


def test_hash_and_independent_channel_fingerprints(tmp_path):
    red = connector.collect_image(picture(tmp_path / 'red.png'), ocr_runner=lambda img: 'same')
    blue = connector.collect_image(picture(tmp_path / 'blue.png', color='blue'), ocr_runner=lambda img: 'same')
    assert red.raw_hash != blue.raw_hash
    rebuilt = connector.build_image_snapshot(red.image_hash, ocr_text=red.ocr_text, ocr_status=red.ocr_status, manual_description='manual')
    assert rebuilt.raw_hash != red.raw_hash
    assert rebuilt.manifest['channel_fingerprints']['ocr_text'] == red.manifest['channel_fingerprints']['ocr_text']
    assert rebuilt.manifest['channel_fingerprints']['manual_description'] != red.manifest['channel_fingerprints']['manual_description']
    assert red.documents[0].logical_path == 'ocr_text'
    assert red.documents[0].locator['origin'] == 'image_ocr'


def test_default_missing_tesseract_saves_original(tmp_path, monkeypatch):
    import pytesseract

    monkeypatch.setattr(pytesseract.pytesseract, 'tesseract_cmd', str(tmp_path / 'missing.exe'))
    snapshot = connector.collect_image(picture(tmp_path / 'image.png'))
    assert snapshot.ocr_status == 'unavailable'
    assert snapshot.image_hash
    assert snapshot.documents == []


def test_text_limits_whitespace_and_status_consistency(tmp_path):
    path = picture(tmp_path / 'image.png')
    snapshot = connector.collect_image(path, manual_description='  description\n', ocr_runner=lambda img: 'machine')
    assert snapshot.manual_description == '  description\n'
    whitespace = connector.collect_image(path, manual_description=' \n', ocr_runner=lambda img: 'machine')
    assert whitespace.manual_description == ''
    with pytest.raises(ConnectorError):
        connector.collect_image(path, manual_description='x' * 100001, ocr_runner=lambda img: '')
    with pytest.raises(ConnectorError):
        connector.build_image_snapshot(snapshot.image_hash, ocr_text='text', ocr_status='no_text')


def test_original_snapshot_fields_cannot_be_reassigned(tmp_path):
    from dataclasses import FrozenInstanceError

    snapshot = connector.collect_image(picture(tmp_path / 'image.png'), ocr_runner=lambda img: 'text')
    with pytest.raises(FrozenInstanceError):
        snapshot.ocr_text = 'changed'
