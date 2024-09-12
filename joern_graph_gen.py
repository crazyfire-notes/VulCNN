# encoding=utf-8
import argparse
import logging
import os
import subprocess
import sys
from functools import partial
from multiprocessing import Pool
from pathlib import Path
from typing import Callable, List, Optional


def setup_logging(log_file: Path) -> logging.Logger:
    """設置日誌記錄"""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # 檔案處理程序
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)

    # 控制台處理程序
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # 格式化程序
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # 添加處理程序到日誌記錄器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def parse_options() -> argparse.Namespace:
    """解析命令行參數"""
    parser = argparse.ArgumentParser(description="使用 Joern 提取代碼屬性圖 (CPGs)")
    parser.add_argument("-i", "--input", help="輸入目錄路徑", type=str, required=True)
    parser.add_argument("-o", "--output", help="輸出目錄路徑", type=str, required=True)
    parser.add_argument(
        "-t",
        "--type",
        help="處理類型: parse 或 export",
        type=str,
        choices=["parse", "export"],
        required=True,
    )
    parser.add_argument(
        "-r",
        "--repr",
        help="表示類型: pdg 或 lineinfo_json",
        type=str,
        choices=["pdg", "lineinfo_json"],
        default="pdg",
    )
    parser.add_argument(
        "-j", "--joern_path", help="Joern CLI 路徑", type=str, required=True
    )
    parser.add_argument(
        "-l", "--log_file", help="日誌檔案路徑", type=str, default="joern_process.log"
    )
    return parser.parse_args()


def setup_environment(joern_path: Path, logger: logging.Logger):
    """設置環境變數並驗證 Joern"""
    joern_path = joern_path.resolve()
    if not joern_path.exists():
        logger.error(f"Joern 路徑不存在: {joern_path}")
        sys.exit(1)

    os.environ["PATH"] = f"{joern_path}{os.pathsep}{os.environ['PATH']}"
    os.environ["JOERN_HOME"] = str(joern_path)

    try:
        result = subprocess.run(
            [str(joern_path / "joern"), "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info(f"Joern 版本: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        logger.error(f"無法運行 Joern: {e}")
        sys.exit(1)


def run_subprocess(
    cmd: List[str], error_msg: str, logger: logging.Logger, shell: bool = False
) -> Optional[str]:
    """運行子進程命令並處理潛在錯誤"""
    try:
        if shell:
            cmd = " ".join(cmd)
        result = subprocess.run(
            cmd, check=True, capture_output=True, text=True, shell=shell
        )
        logger.info(f"成功運行命令: {cmd}")
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"{error_msg}:")
        logger.error(f"命令: {cmd}")
        logger.error(f"返回碼: {e.returncode}")
        logger.error(f"錯誤輸出: {e.stderr}")
        logger.error(f"標準輸出: {e.stdout}")
    except Exception as e:
        logger.error(f"{error_msg}: {str(e)}")
    return None


def process_file(
    file: Path,
    outdir: Path,
    record_file: Path,
    process_func: Callable,
    logger: logging.Logger,
):
    """處理單個文件並記錄結果"""
    with record_file.open("r+") as f:
        processed_files = set(f.read().splitlines())
        name = file.stem
        if name in processed_files:
            logger.info(f"文件已處理: {name}")
            return

        if process_func(file, outdir):
            f.write(f"{name}\n")
            logger.info(f"已將 {name} 添加到記錄文件")


def joern_parse(
    file: Path, outdir: Path, joern_path: Path, logger: logging.Logger
) -> bool:
    """使用 Joern 解析 C 文件"""
    name = file.stem
    logger.info(f"正在處理文件: {name}")
    out_file = outdir / f"{name}.bin"

    if out_file.exists():
        logger.info(f"輸出文件已存在: {out_file}")
        return True

    joern_parse_path = joern_path / "joern-parse"
    cmd = [
        str(joern_parse_path),
        str(file),
        "--language",
        "c",
        "--output",
        str(out_file),
    ]

    return run_subprocess(cmd, f"解析文件 {file} 時出錯", logger) is not None


def joern_export(
    bin_file: Path, outdir: Path, repr: str, joern_path: Path, logger: logging.Logger
) -> bool:
    """導出已解析的二進制文件為 PDG 或 JSON 格式"""
    logger.info(f"開始導出進程: {bin_file}")
    name = bin_file.stem
    out_file = outdir / name

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

        if run_subprocess(cmd, f"導出 PDG 時出錯: {bin_file}", logger):
            if out_file.is_dir():
                pdg_files = list(out_file.glob("*.dot"))
                if pdg_files:
                    merged_dot = out_file.with_suffix(".dot")
                    logger.info(f"開始合併 PDG 文件到: {merged_dot}")
                    try:
                        with merged_dot.open("w", encoding="utf-8") as outfile:
                            outfile.write("digraph G {\n")
                            for pdg in pdg_files:
                                logger.info(f"處理 PDG 文件: {pdg}")
                                with pdg.open(encoding="utf-8") as infile:
                                    content = infile.read()
                                    # 移除開頭的 "digraph G {" 和結尾的 "}"
                                    content = content.replace("digraph G {", "", 1)
                                    content = content.rsplit("}", 1)[0]
                                    outfile.write(f"subgraph cluster_{pdg.stem} {{\n")
                                    outfile.write(content)
                                    outfile.write("\n}\n")
                            outfile.write("}")
                        logger.info(f"成功合併 PDG 文件到: {merged_dot}")

                        # 刪除原始的 PDG 目錄
                        import shutil

                        shutil.rmtree(out_file)
                        logger.info(f"已刪除原始 PDG 目錄: {out_file}")

                        return True
                    except Exception as e:
                        logger.error(f"合併 PDG 文件時發生錯誤: {e}")
                        return False
                else:
                    logger.warning(f"未在 {out_file} 中找到 .dot 文件")
                    return False
            else:
                logger.info(f"PDG 輸出已經是一個文件: {out_file}")
                return True
        else:
            logger.error(f"Joern 導出命令失敗: {bin_file}")
            return False
    else:  # JSON 導出
        out_file = out_file.with_suffix(".json")
        script_path = Path("graph-for-funcs.sc").resolve()
        if not script_path.exists():
            logger.error(f"腳本文件不存在: {script_path}")
            return False
        cmd = [
            str(joern_path / "joern"),
            "--script",
            str(script_path),
            "--params",
            f"inputPath={bin_file},outputPath={out_file}",
        ]

        if run_subprocess(cmd, f"導出 JSON 時出錯: {bin_file}", logger):
            logger.info(f"成功導出 JSON: {out_file}")
            return True
        else:
            logger.error(f"JSON 導出失敗: {bin_file}")
            return False

    # return False


def main():
    args = parse_options()
    log_file = Path(args.log_file)
    logger = setup_logging(log_file)
    logger.info(f"開始 Joern 圖生成進程，參數: {args}")

    joern_path = Path(args.joern_path).resolve()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    logger.info(f"Joern 路徑: {joern_path}")
    logger.info(f"輸入路徑: {input_path}")
    logger.info(f"輸出路徑: {output_path}")

    output_path.mkdir(parents=True, exist_ok=True)

    setup_environment(joern_path, logger)

    pool_num = os.cpu_count() or 1
    logger.info(f"使用進程池，工作進程數: {pool_num}")

    with Pool(pool_num) as pool:
        if args.type == "parse":
            files = list(input_path.glob("*.c"))
            logger.info(f"找到 {len(files)} 個 C 文件待解析")
            record_file = output_path / "parse_res.txt"
            record_file.touch(exist_ok=True)
            pool.map(
                partial(
                    process_file,
                    outdir=output_path,
                    record_file=record_file,
                    process_func=partial(
                        joern_parse, joern_path=joern_path, logger=logger
                    ),
                    logger=logger,
                ),
                files,
            )
        elif args.type == "export":
            bins = list(input_path.glob("*.bin"))
            logger.info(f"找到 {len(bins)} 個二進制文件待導出")
            record_file = output_path / "export_res.txt"
            record_file.touch(exist_ok=True)
            pool.map(
                partial(
                    process_file,
                    outdir=output_path,
                    record_file=record_file,
                    process_func=partial(
                        joern_export,
                        repr=args.repr,
                        joern_path=joern_path,
                        logger=logger,
                    ),
                    logger=logger,
                ),
                bins,
            )
        else:
            logger.error(f"無效的處理類型: {args.type}")

    logger.info("Joern 圖生成進程完成")


if __name__ == "__main__":
    main()
