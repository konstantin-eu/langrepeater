import argparse

from src.langrepeater_app.main import langrepeater_main
from src.langrepeater_compiler_md import parse_markdown_file
from src.lib_clean.lib_common import get_app_dir


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "infile",
        help="Path to the input markdown file"
    )

    # optional flag with a default
    parser.add_argument(
        "-o", "--outfile",
        default="",
        help="Where to write the langrepeater txt file"
    )

    parser.add_argument(
        "--create_video",
        action="store_true",
        help="If set, a video will be created"
    )

    return parser.parse_args()

def main():
    args = get_args()

    if args.outfile == "":
        from pathlib import Path

        old_path = Path(args.infile)
        new_path = old_path.with_suffix(".txt")
        default_out = str(new_path)
    else:
        default_out = args.outfile

    print(f"Reading agrs: {args.infile} {default_out}")

    parse_markdown_file(
        args.infile,
        default_out
    )

    langrepeater_main(default_out, args.create_video)

if __name__ == "__main__":
    main()