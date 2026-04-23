from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT_DIR / "build"
ARTIFACTS_DIR = ROOT_DIR / "artifacts"
ARTIFACT_STEM = "backend-lambda"
LAMBDA_REQUIREMENTS = (
    "fastapi==0.115.12",
    "httpx==0.27.2",
    "mangum==0.19.0",
    "opensearch-py==2.7.1",
    "pydantic==2.11.3",
    "pypdf==5.4.0",
    "python-dotenv==1.0.1",
    "python-docx==1.1.2",
    "requests-aws4auth==1.3.1",
)


def _create_build_directory() -> Path:
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="lambda-build-", dir=BUILD_ROOT))


def _install_dependencies(build_dir: Path, package_dir: Path) -> None:
    requirements_path = build_dir / "lambda-requirements.txt"
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
            str(package_dir),
        ],
        check=True,
        cwd=ROOT_DIR,
    )


def _copy_sources(package_dir: Path) -> None:
    shutil.copytree(ROOT_DIR / "app", package_dir / "app", dirs_exist_ok=True)
    shutil.copytree(ROOT_DIR / "data" / "mock", package_dir / "data" / "mock", dirs_exist_ok=True)
    shutil.copytree(ROOT_DIR / "scripts", package_dir / "scripts", dirs_exist_ok=True)


def _create_archive(package_dir: Path) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = ARTIFACTS_DIR / ARTIFACT_STEM
    if archive_path.with_suffix(".zip").exists():
        archive_path.with_suffix(".zip").unlink()
    created_archive = shutil.make_archive(str(archive_path), "zip", root_dir=package_dir)
    return Path(created_archive)


def main() -> int:
    print("Preparing Lambda build directory...")
    build_dir = _create_build_directory()
    package_dir = build_dir / "package"
    package_dir.mkdir(parents=True, exist_ok=True)

    print("Installing Python dependencies into artifact package...")
    _install_dependencies(build_dir, package_dir)

    print("Copying application source files...")
    _copy_sources(package_dir)

    print("Creating deployment artifact zip...")
    archive = _create_archive(package_dir)
    print(f"Created Lambda artifact: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
