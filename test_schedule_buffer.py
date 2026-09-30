import os
import unittest

os.environ.setdefault("BUFFER_API_KEY", "test")
os.environ.setdefault("GITHUB_REPOSITORY", "owner/repo")
os.environ.setdefault("MEDIA_SHA", "test-sha")

from schedule_buffer import SITE_CTA_LABEL, build_post_text


class BuildPostTextTest(unittest.TestCase):
    def test_real_image_has_no_ai_note(self):
        text = build_post_text({
            "post_text": "本文",
            "image_sources": [{"type": "pexels"}],
        })
        self.assertNotIn("AI生成イメージ", text)
        self.assertTrue(text.endswith(f"{SITE_CTA_LABEL}\nhttps://venutrip.jp"))

    def test_ai_image_has_ai_note(self):
        text = build_post_text({
            "post_text": "本文",
            "image_sources": [{"type": "ai"}],
        })
        self.assertIn("※画像はAI生成イメージ", text)

    def test_existing_footer_is_replaced_once(self):
        text = build_post_text({
            "post_text": "本文\n\n▼VENUTRIPで周辺情報をチェック\nhttps://legacy.example/",
            "image_sources": [{"type": "pexels"}],
        })
        self.assertNotIn("legacy.example", text)
        self.assertEqual(text.count(SITE_CTA_LABEL), 1)
        self.assertEqual(text.count("https://venutrip.jp"), 1)


if __name__ == "__main__":
    unittest.main()
