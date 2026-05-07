from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT_DIR / "build"
ARTIFACTS_DIR = ROOT_DIR / "artifacts"
ARTIFACT_STEM = "backend-lambda"
LAMBDA_REQUIREMENTS = (
    "fastapi==0.115.12",
    "httpx==0.27.2",
    "opensearch-py==2.7.1",
    "pydantic==2.11.3",
    "pypdf==5.4.0",
    "python-dotenv==1.0.1",
    "python-docx==1.1.2",
    "requests-aws4auth==1.3.1",
    "uvicorn==0.34.0",
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
    run_script = (ROOT_DIR / "run.sh").read_text(encoding="utf-8").replace("\r\n", "\n")
    (package_dir / "run.sh").write_text(run_script, encoding="utf-8", newline="\n")


def _create_archive(package_dir: Path) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = ARTIFACTS_DIR / f"{ARTIFACT_STEM}.zip"
    if archive_path.exists():
        archive_path.unlink()

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source_path in sorted(package_dir.rglob("*")):
            if source_path.is_dir():
                continue
            archive_name = source_path.relative_to(package_dir).as_posix()
            zip_info = zipfile.ZipInfo.from_file(source_path, archive_name)
            zip_info.compress_type = zipfile.ZIP_DEFLATED
            if archive_name == "run.sh":
                zip_info.external_attr = 0o755 << 16
            with source_path.open("rb") as source_file:
                archive.writestr(zip_info, source_file.read())
    return archive_path


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
