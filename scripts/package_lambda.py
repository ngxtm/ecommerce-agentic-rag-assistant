from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT_DIR / "build" / "lambda"
PACKAGE_DIR = BUILD_DIR / "package"
ARTIFACTS_DIR = ROOT_DIR / "artifacts"
ARTIFACT_STEM = "backend-lambda"
LAMBDA_REQUIREMENTS = (
    "fastapi==0.115.12",
    "httpx==0.27.2",
    "mangum==0.19.0",
    "opensearch-py==2.7.1",
    "pydantic==2.11.3",
    "python-dotenv==1.0.1",
    "requests-aws4auth==1.3.1",
)


def _reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _install_dependencies() -> None:
    requirements_path = BUILD_DIR / "lambda-requirements.txt"
    requirements_path.write_text("\n".join(LAMBDA_REQUIREMENTS) + "\n", encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--requirement",
            str(requirements_path),
            "--platform",
            "manylinux2014_x86_64",
            "--implementation",
            "cp",
            "--python-version",
            "3.12",
            "--only-binary=:all:",
            "--target",
            str(PACKAGE_DIR),
        ],
        check=True,
        cwd=ROOT_DIR,
    )


def _copy_sources() -> None:
    shutil.copytree(ROOT_DIR / "app", PACKAGE_DIR / "app", dirs_exist_ok=True)
    shutil.copytree(ROOT_DIR / "data" / "mock", PACKAGE_DIR / "data" / "mock", dirs_exist_ok=True)


def _create_archive() -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = ARTIFACTS_DIR / ARTIFACT_STEM
    if archive_path.with_suffix(".zip").exists():
        archive_path.with_suffix(".zip").unlink()
    created_archive = shutil.make_archive(str(archive_path), "zip", root_dir=PACKAGE_DIR)
    return Path(created_archive)


def main() -> int:
    print("Preparing Lambda build directory...")
    _reset_directory(BUILD_DIR)
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)

    print("Installing Python dependencies into artifact package...")
    _install_dependencies()

    print("Copying application source files...")
    _copy_sources()

    print("Creating deployment artifact zip...")
    archive = _create_archive()
    print(f"Created Lambda artifact: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
