import os
import unittest
from instagram_graphic_card_generator import InstagramGraphicCardGenerator

class TestGraphicCardGenerator(unittest.TestCase):
    def setUp(self):
        self.generator = InstagramGraphicCardGenerator()

    def test_create_news_card_without_bg(self):
        file_path = self.generator.create_news_card(
            title="India Wins Test Series with Dominant Performance",
            summary="Sensational bowling spell wraps up series victory against Sri Lanka.",
            category="cricket",
            source_name="ESPNcricinfo",
            content_id="test_card_nobg",
        )
        self.assertTrue(os.path.exists(file_path))
        self.assertTrue(file_path.endswith(".jpg"))

    def test_create_news_card_with_bg_overlay(self):
        sample_img = "https://images.unsplash.com/photo-1540747913346-19e32dc3e97e?q=80&w=1080&auto=format&fit=crop"
        file_path = self.generator.create_news_card(
            title="Next-Gen AI Chip Released with 10x Performance",
            summary="Tech giants reveal revolutionary silicon architecture for deep learning.",
            category="technology",
            source_name="TechCrunch",
            content_id="test_card_bg",
            bg_image_path=sample_img,
        )
        self.assertTrue(os.path.exists(file_path))
        self.assertTrue(file_path.endswith(".jpg"))

if __name__ == "__main__":
    unittest.main()
