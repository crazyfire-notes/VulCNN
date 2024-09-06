import argparse
import re
from pathlib import Path

from clean_gadget import clean_gadget  # 添加這行來導入 clean_gadget 函數


def parse_options() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Normalization of code files.")
    parser.add_argument(
        "-i",
        "--input",
        help="The directory path of input dataset",
        type=str,
        required=True,
    )
    return parser.parse_args()


def remove_comments(code: str) -> str:
    """Remove single-line and multi-line comments from the code."""
    # Remove single-line comments
    code = re.sub(r"(?<!:)//.*", "", code)
    # Remove multi-line comments
    code = re.sub(r"/\*[\s\S]*?\*/", "", code)
    return code.strip()


# 移除這個函數定義，因為我們現在直接使用導入的 clean_gadget 函數
# def clean_gadget(code_lines: List[str]) -> List[str]:
#     """
#     Clean and normalize the code.
#     This is a placeholder function. Replace with actual implementation.
#     """
#     # TODO: Implement actual code cleaning logic
#     return code_lines


def process_file(file_path: Path) -> None:
    """Process a single file: remove comments and apply cleaning."""
    try:
        with file_path.open("r", encoding="utf-8") as file:
            code = file.read()

        # Remove comments
        code = remove_comments(code)

        # Apply cleaning
        cleaned_code = clean_gadget(code.splitlines())

        with file_path.open("w", encoding="utf-8") as file:
            file.write("\n".join(cleaned_code))

        print(f"Processed: {file_path}")
    except Exception as e:
        print(f"Error processing {file_path}: {str(e)}")


def normalize(directory: Path) -> None:
    """Normalize all files in the given directory and its subdirectories."""
    for file_path in directory.rglob("*"):
        if file_path.is_file():
            process_file(file_path)


def main() -> None:
    """Main function to run the normalization process."""
    args = parse_options()
    input_dir = Path(args.input)

    if not input_dir.exists() or not input_dir.is_dir():
        print(
            f"Error: The specified input directory does not exist or is not a directory: {input_dir}"
        )
        return

    normalize(input_dir)
    print("Normalization process completed.")


if __name__ == "__main__":
    main()
