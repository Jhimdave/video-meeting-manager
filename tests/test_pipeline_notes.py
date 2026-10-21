import unittest

from pipeline import _notes_description


class NotesDescriptionTests(unittest.TestCase):
    def test_returns_trimmed_overview_without_action_items(self):
        self.assertEqual(_notes_description("  Discussed status and agreed on next steps.  "),
                         "Discussed status and agreed on next steps.")

    def test_uses_transcript_fallback_when_overview_is_empty(self):
        self.assertEqual(_notes_description("  "), "See transcript on the page.")


if __name__ == "__main__":
    unittest.main()
