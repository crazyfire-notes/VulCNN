# encoding=utf-8
import argparse
import logging
import os
import subprocess
from functools import partial
from multiprocessing import Pool
from pathlib import Path
from typing import List, Optional

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_all_files(path: Path) -> List[Path]:
    """
    Recursively get all files in the given directory.

    Args:
        path (Path): The directory path to search.

    Returns:
        List[Path]: A list of all file paths found.
    """
    logger.info(f"Getting all files from: {path}")
    files = list(path.rglob("*"))
    logger.info(f"Found {len(files)} files")
    return files


def parse_options() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Extract Code Property Graphs (CPGs) using Joern"
    )
    parser.add_argument(
        "-i", "--input", help="Input directory path", type=str, required=True
    )
    parser.add_argument(
        "-o", "--output", help="Output directory path", type=str, required=True
    )
    parser.add_argument(
        "-t",
        "--type",
        help="Process type: parse or export",
        type=str,
        choices=["parse", "export"],
        required=True,
    )
    parser.add_argument(
        "-r",
        "--repr",
        help="Representation type: pdg or lineinfo_json",
        type=str,
        choices=["pdg", "lineinfo_json"],
        default="pdg",
    )
    parser.add_argument(
        "-j", "--joern_path", help="Joern CLI path", type=str, required=True
    )
    return parser.parse_args()


def run_subprocess(cmd: List[str], error_msg: str) -> Optional[str]:
    """
    Run a subprocess command and handle potential errors.

    Args:
        cmd (List[str]): Command to run.
        error_msg (str): Error message prefix.

    Returns:
        Optional[str]: Command output if successful, None otherwise.
    """
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info(f"Successfully ran command: {' '.join(cmd)}")
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"{error_msg}:")
        logger.error(f"Command: {' '.join(cmd)}")
        logger.error(f"Return code: {e.returncode}")
        logger.error(f"Error output: {e.stderr}")
        logger.error(f"Standard output: {e.stdout}")
    except Exception as e:
        logger.error(f"{error_msg}: {str(e)}")
    return None


def joern_parse(file: Path, outdir: Path, joern_path: Path) -> None:
    """
    Parse a C file using Joern.

    Args:
        file (Path): Path to the C file.
        outdir (Path): Output directory.
        joern_path (Path): Path to Joern CLI.
    """
    record_file = outdir / "parse_res.txt"
    record_file.touch(exist_ok=True)

    with record_file.open("r") as f:
        processed_files = set(f.read().splitlines())

    name = file.stem
    if name in processed_files:
        logger.info(f"File already processed: {name}")
        return

    logger.info(f"Processing file: {name}")
    out_file = outdir / f"{name}.bin"

    if out_file.exists():
        logger.info(f"Output file already exists: {out_file}")
        return

    joern_parse_path = joern_path / "joern-parse"
    cmd = [
        str(joern_parse_path),
        str(file),
        "--language",
        "c",
        "--output",
        str(out_file),
    ]

    if run_subprocess(cmd, f"Error parsing file {file}"):
        with record_file.open("a") as f:
            f.write(f"{name}\n")


def joern_export(bin_file: Path, outdir: Path, repr: str, joern_path: Path) -> None:
    """
    Export a parsed binary file to PDG or JSON format.

    Args:
        bin_file (Path): Path to the binary file.
        outdir (Path): Output directory.
        repr (str): Representation type (pdg or lineinfo_json).
        joern_path (Path): Path to Joern CLI.
    """
    record_file = outdir / "export_res.txt"
    record_file.touch(exist_ok=True)

    with record_file.open("r") as f:
        processed_files = set(f.read().splitlines())

    name = bin_file.stem
    out_file = outdir / name

    if name in processed_files:
        logger.info(f"File already processed: {name}")
        return

    logger.info(f"Processing file: {name}")

    if repr == "pdg":
        joern_export_path = joern_path / "joern-export"
        cmd = [
            str(joern_export_path),
            str(bin_file),
            "--repr",
            "pdg",
            "--out",
            str(out_file),
        ]

        if run_subprocess(cmd, f"Error exporting PDG for {bin_file}"):
            pdg_files = list(out_file.glob("0-pdg*"))
            if pdg_files:
                pdg_files[0].rename(out_file.with_suffix(".dot"))
                out_file.rmdir()
                logger.info(f"Renamed PDG file: {bin_file}")
    else:
        out_file = out_file.with_suffix(".json")
        script_path = Path("graph-for-funcs.sc").resolve()
        cmd = f'importCpg("{bin_file}")\rcpg.runScript("{script_path}").toString() |> "{out_file}"\r'

        logger.info(f"Running Joern command: {cmd}")
        joern_process = subprocess.Popen(
            [str(joern_path / "joern")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=joern_path,
        )
        stdout, stderr = joern_process.communicate(cmd)

        if stderr:
            logger.error(f"Error exporting JSON for {bin_file}: {stderr}")
        else:
            logger.info(f"Successfully exported JSON: {bin_file}")

    with record_file.open("a") as f:
        f.write(f"{name}\n")


def main() -> None:
    """Main function to orchestrate the Joern graph generation process."""
    args = parse_options()
    logger.info(f"Starting Joern graph generation process with parameters: {args}")

    # Convert all paths to absolute paths
    joern_path = Path(args.joern_path).resolve()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    logger.info(f"Joern path: {joern_path}")
    logger.info(f"Input path: {input_path}")
    logger.info(f"Output path: {output_path}")

    output_path.mkdir(parents=True, exist_ok=True)

    # Set environment variables
    os.environ["PATH"] = f"{joern_path}{os.pathsep}{os.environ['PATH']}"
    os.environ["JOERN_HOME"] = str(joern_path)

    pool_num = os.cpu_count() or 1
    logger.info(f"Using process pool with {pool_num} workers")

    with Pool(pool_num) as pool:
        if args.type == "parse":
            files = list(input_path.glob("*.c"))
            logger.info(f"Found {len(files)} C files to parse")
            pool.map(
                partial(joern_parse, outdir=output_path, joern_path=joern_path), files
            )
        elif args.type == "export":
            bins = list(input_path.glob("*.bin"))
            logger.info(f"Found {len(bins)} binary files to export")
            pool.map(
                partial(
                    joern_export,
                    outdir=output_path,
                    repr=args.repr,
                    joern_path=joern_path,
                ),
                bins,
            )
        else:
            logger.error(f"Invalid process type: {args.type}")

    logger.info("Joern graph generation process completed")


if __name__ == "__main__":
    main()
