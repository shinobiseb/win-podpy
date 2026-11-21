import argparse

from config import AUDIO1, AUDIO2, CUTS_JSON, OUTPUT, VIDEO, VIDEO2
from pipeline import OUTPUT_MODES, process_project


def main():
    parser = argparse.ArgumentParser(
        description="Analyze two camera videos and render or export a Resolve timeline."
    )
    parser.add_argument("--video1", default=VIDEO, help="Camera 1 video")
    parser.add_argument("--video2", default=VIDEO2, help="Camera 2 video")
    parser.add_argument("--audio1", default=AUDIO1, help="Separate audio track 1")
    parser.add_argument("--audio2", default=AUDIO2, help="Separate audio track 2")
    parser.add_argument(
        "--videos-only",
        action="store_true",
        help="Use audio embedded in each video instead of separate audio files",
    )
    parser.add_argument(
        "--output-mode",
        choices=OUTPUT_MODES,
        default="render",
        help="Choose MP4 rendering, timeline XML only, or both",
    )
    parser.add_argument("--output", help="Rendered MP4 path (render/both mode)")
    parser.add_argument(
        "--resolve-xml",
        help="Final Cut Pro XML output path (resolve/both mode)",
    )
    parser.add_argument("--cuts-json", default=CUTS_JSON, help="Camera cut-list JSON path")
    args = parser.parse_args()

    output = args.output or (OUTPUT if args.output_mode in ("render", "both") else None)
    timeline_xml = args.resolve_xml or (
        "podpy_timeline.fcpxml" if args.output_mode in ("resolve", "both") else None
    )

    process_project(
        video1=args.video1,
        video2=args.video2,
        audio1=None if args.videos_only else args.audio1,
        audio2=None if args.videos_only else args.audio2,
        output=output,
        cuts_json=args.cuts_json,
        resolve_xml=timeline_xml,
        output_mode=args.output_mode,
    )


if __name__ == "__main__":
    main()
