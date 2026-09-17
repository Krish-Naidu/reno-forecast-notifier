import json
import unittest
from pathlib import Path

import forecast_notifier


class StateFileTests(unittest.TestCase):
    def test_state_round_trip(self) -> None:
        path = Path(self._testMethodName + ".json")
        try:
            self.assertIsNone(forecast_notifier.load_state(path))
            forecast_notifier.save_state(path, "UXUS97 KREV 171305", "2026-09-17")
            self.assertEqual(
                json.loads(path.read_text()),
                {"publication_id": "UXUS97 KREV 171305", "sent_date": "2026-09-17"},
            )
            self.assertEqual(forecast_notifier.load_state(path)["publication_id"], "UXUS97 KREV 171305")
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
