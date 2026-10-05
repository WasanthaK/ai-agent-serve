import pathlib
import unittest


class DockerPackagingTests(unittest.TestCase):
    def test_runtime_image_copies_all_root_python_modules(self):
        dockerfile = pathlib.Path("Dockerfile").read_text(
            encoding="utf-8"
        )

        self.assertIn("COPY *.py ./", dockerfile)
        self.assertIn(
            "COPY agent_skills ./agent_skills",
            dockerfile,
        )
        self.assertIn("uvicorn runtime:app", dockerfile)


if __name__ == "__main__":
    unittest.main()
