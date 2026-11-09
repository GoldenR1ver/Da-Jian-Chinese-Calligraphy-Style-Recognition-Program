import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from calligraphy_style import db, images
from calligraphy_style.cli import main


def _page(boxes: list[tuple[int, int, int, int]], size=(360, 140)) -> np.ndarray:
    width, height = size
    image = np.full((height, width), 255, np.uint8)
    for x, y, w, h in boxes:
        image[y : y + h, x : x + w] = 0
    return image


class FlowTest(unittest.TestCase):
    def test_import_analyze_and_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = root / "calligraphy.db"
            page = root / "work.png"
            cv2.imwrite(str(page), _page([(20, 30, 70, 80), (140, 30, 70, 80), (260, 30, 70, 80)]))

            self.assertEqual(main(["--db", str(database), "init"]), 0)
            self.assertEqual(
                main(
                    [
                        "--db",
                        str(database),
                        "import",
                        "--image",
                        str(page),
                        "--author",
                        "多宝塔",
                        "--style",
                        "楷书",
                        "--text",
                        "永、和、年",
                        "--title",
                        "试笔",
                    ]
                ),
                0,
            )

            conn = db.connect(database)
            try:
                counts = db.summary(conn)
                self.assertEqual(counts["glyphs"], 3)
                self.assertEqual(counts["works"], 1)
                author = conn.execute(
                    """
                    SELECT authors.name
                    FROM works
                    JOIN author_styles ON author_styles.id = works.author_style_id
                    JOIN authors ON authors.id = author_styles.author_id
                    """
                ).fetchone()
                self.assertEqual(author["name"], "颜真卿")
                forms = [
                    row["form"]
                    for row in conn.execute(
                        """
                        SELECT character_variants.form AS form
                        FROM glyphs
                        JOIN character_variants ON character_variants.id = glyphs.variant_id
                        ORDER BY glyphs.reading_order
                        """
                    )
                ]
                self.assertEqual(forms, ["永", "和", "年"])
            finally:
                conn.close()

            single = root / "variant.png"
            cv2.imwrite(str(single), _page([(40, 30, 80, 80)], size=(180, 140)))
            self.assertEqual(
                main(
                    [
                        "--db",
                        str(database),
                        "import",
                        "--image",
                        str(single),
                        "--author",
                        "颜真卿",
                        "--style",
                        "楷书",
                        "--text",
                        "爲",
                    ]
                ),
                0,
            )
            conn = db.connect(database)
            try:
                row = conn.execute(
                    """
                    SELECT characters.canonical
                    FROM glyphs
                    JOIN characters ON characters.id = glyphs.character_id
                    JOIN character_variants ON character_variants.id = glyphs.variant_id
                    WHERE character_variants.form = '爲'
                    """
                ).fetchone()
                self.assertEqual(row["canonical"], "为")
            finally:
                conn.close()

            main(
                [
                    "--db",
                    str(database),
                    "score",
                    "--author",
                    "颜真卿",
                    "--style",
                    "楷书",
                    "--scores",
                    "60,70,65,55,80,40,50,45",
                ]
            )
            report_path = root / "report.json"
            self.assertEqual(
                main(
                    [
                        "--db",
                        str(database),
                        "analyze",
                        "--image",
                        str(page),
                        "--text",
                        "永和年",
                        "--out",
                        str(report_path),
                    ]
                ),
                0,
            )
            report = __import__("json").loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["authors"][0]["author"], "颜真卿")
            self.assertIn("中和", report["eight_dimensions"])

    def test_vertical_order_and_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = root / "calligraphy.db"
            page = root / "column.png"
            cv2.imwrite(
                str(page),
                _page([(40, 20, 60, 50), (40, 100, 60, 50), (40, 180, 60, 50)], size=(140, 260)),
            )
            main(["--db", str(database), "init"])
            main(
                [
                    "--db",
                    str(database),
                    "import",
                    "--image",
                    str(page),
                    "--author",
                    "王羲之",
                    "--style",
                    "行书",
                    "--layout",
                    "vertical",
                    "--text",
                    "一二三",
                ]
            )
            conn = db.connect(database)
            try:
                boxes = conn.execute(
                    "SELECT bbox_y FROM glyphs ORDER BY reading_order"
                ).fetchall()
                self.assertLess(boxes[0]["bbox_y"], boxes[1]["bbox_y"])
            finally:
                conn.close()

            self.assertEqual(
                main(
                    [
                        "--db",
                        str(database),
                        "import",
                        "--image",
                        str(page),
                        "--author",
                        "王羲之",
                        "--style",
                        "行书",
                        "--layout",
                        "vertical",
                        "--text",
                        "一二",
                    ]
                ),
                1,
            )

    def test_split_keeps_separate_characters(self) -> None:
        page = _page([(20, 30, 70, 80), (140, 30, 70, 80), (260, 30, 70, 80)])
        mask = images.ink_mask(page)
        boxes = images.find_boxes(mask, page.shape[:2])
        self.assertEqual(len(boxes), 3)


if __name__ == "__main__":
    unittest.main()
