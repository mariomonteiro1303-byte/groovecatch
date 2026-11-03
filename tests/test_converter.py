from app.services.converter_service import ALLOWED_INPUTS, ALLOWED_OUTPUTS

def test_formats():
    assert "m4a" in ALLOWED_INPUTS
    assert {"mp3", "wav", "flac"} == ALLOWED_OUTPUTS
