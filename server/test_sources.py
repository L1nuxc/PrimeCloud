import unittest
from public_soundcloud import full_audio, matches


class SoundCloudTest(unittest.TestCase):
    def test_full_stream_from_current_soundcloud_cdn(self):
        url = "https://playback.media-streaming.soundcloud.cloud/example"
        audio = {"url": url, "format_id": "hls_aac_160k", "protocol": "m3u8_native"}
        self.assertEqual(full_audio({"formats": [audio]}), url)
        for change in ({"format_id": "hls_aac_160k_preview"}, {"has_drm": True},
                       {"url": "https://other.example/example"}):
            self.assertIsNone(full_audio({"formats": [audio | change]}))

    def test_matching_preserves_recording_version(self):
        track = {"artist": {"name": "DEAF KEV"}, "title": "Invincible", "duration": 279}
        original = {"uploader": "DEAF KEV", "title": "Invincible", "duration": 279.646}
        self.assertTrue(matches(track, original))
        self.assertFalse(matches(track, original | {"title": "Invincible (Clean)"}))
        self.assertFalse(matches(track, original | {"duration": 30}))
        self.assertFalse(matches(track, original | {"uploader": "Other artist"}))
