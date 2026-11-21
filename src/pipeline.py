import subprocess
import tempfile
import shutil
from pathlib import Path

from audio import prepare_audio
from camera import choose_camera_by_activity, export_camera_cuts, export_fcpxml
from config import ENVELOPE_RATE, MIN_CORRELATION
from media import extract_analysis_wav, extract_audio_track, probe_duration, probe_video_size
from rendering import render_video
from sync import estimate_and_check


OUTPUT_MODES = ("render", "resolve", "both")


def process_project(
    video1,
    video2,
    audio1=None,
    audio2=None,
    output=None,
    cuts_json="camera_cuts.json",
    resolve_xml=None,
    output_mode="render",
    on_progress=None,
):
    """Analyze two cameras, render an MP4, export Resolve FCPXML, or both.

    Resolve exports include persistent processed audio assets alongside the
    FCPXML. Camera-source audio is excluded from that timeline.
    """
    def report(message):
        print(message)
        if on_progress:
            on_progress(message)

    if output_mode not in OUTPUT_MODES:
        raise ValueError(f"output_mode must be one of {', '.join(OUTPUT_MODES)}")
    render_requested = output_mode in ("render", "both")
    timeline_requested = output_mode in ("resolve", "both")
    if render_requested and not output:
        raise ValueError("An MP4 output path is required for render/both mode.")
    if timeline_requested and not resolve_xml:
        raise ValueError("A Resolve XML path is required for resolve/both mode.")
    if timeline_requested:
        resolve_xml = str(resolve_xml)
        if resolve_xml.lower().endswith(".fcpxml.xml"):
            resolve_xml = resolve_xml[:-4]
            report(f"Removing duplicate XML suffix; saving as: {resolve_xml}")

    for path in (video1, video2):
        if not Path(path).is_file():
            raise FileNotFoundError(f"Input video not found: {path}")
    if (audio1 is None) != (audio2 is None):
        raise ValueError("Provide either both external audio tracks or neither.")
    video_only_mode = audio1 is None
    if not video_only_mode:
        for path in (audio1, audio2):
            if not Path(path).is_file():
                raise FileNotFoundError(f"Input audio not found: {path}")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        video1_wav = temp_dir / "video1_analysis.wav"
        video2_wav = temp_dir / "video2_analysis.wav"

        if video_only_mode:
            report("Video-only mode: extracting embedded audio for analysis...")
            try:
                extract_analysis_wav(video1, video1_wav)
                extract_analysis_wav(video2, video2_wav)
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(
                    "Could not extract embedded audio. Both videos must contain audio."
                ) from exc
            activity_audio1, activity_audio2 = video1_wav, video2_wav
            audio1_shift = 0.0
        else:
            activity_audio1 = temp_dir / "audio1_analysis.wav"
            activity_audio2 = temp_dir / "audio2_analysis.wav"

        # Resolve needs audio files that remain available after this temporary
        # workspace is deleted. Store these beside the XML in a companion folder.
        if timeline_requested:
            xml_path = Path(resolve_xml).expanduser().resolve()
            audio_assets_dir = xml_path.parent / f"{xml_path.stem}_media"
            audio_assets_dir.mkdir(parents=True, exist_ok=True)
            processed1_path = audio_assets_dir / "processed_audio1.wav"
            processed2_path = audio_assets_dir / "processed_audio2.wav"
        else:
            processed1_path = temp_dir / "audio1_processed.wav"
            processed2_path = temp_dir / "audio2_processed.wav"

        if video_only_mode:
            report("Preparing embedded audio for output...")
            embedded_audio1 = temp_dir / "video1_embedded_audio.wav"
            embedded_audio2 = temp_dir / "video2_embedded_audio.wav"
            try:
                extract_audio_track(video1, embedded_audio1)
                extract_audio_track(video2, embedded_audio2)
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(
                    "Could not extract embedded audio. Both videos must contain an audio track."
                ) from exc
            audio_source1, audio_source2 = embedded_audio1, embedded_audio2
        else:
            report("Preparing external audio tracks for output...")
            audio_source1, audio_source2 = audio1, audio2

        prepared_audio1 = Path(prepare_audio(audio_source1, processed1_path)).resolve()
        prepared_audio2 = Path(prepare_audio(audio_source2, processed2_path)).resolve()
        if timeline_requested:
            # prepare_audio may return its input unchanged when it already meets
            # targets. Copy it out of the temporary directory and use a stable
            # companion asset path in the XML either way.
            if prepared_audio1 != processed1_path.resolve():
                shutil.copy2(prepared_audio1, processed1_path)
            if prepared_audio2 != processed2_path.resolve():
                shutil.copy2(prepared_audio2, processed2_path)
            prepared_audio1 = processed1_path.resolve()
            prepared_audio2 = processed2_path.resolve()
            report(f"Resolve audio assets: {audio_assets_dir}")

        report("Inspecting videos...")
        duration1 = probe_duration(video1)
        duration2 = probe_duration(video2)
        duration = duration1
        width, height = probe_video_size(video1)
        default_camera = 2 if duration2 > duration1 else 1
        report(
            f"Default camera during silence: VIDEO{default_camera} "
            f"(longer clip; VIDEO1 {duration1:.1f}s, VIDEO2 {duration2:.1f}s)"
        )

        report("Extracting audio for sync analysis...")
        try:
            if not video_only_mode:
                extract_analysis_wav(prepared_audio1, activity_audio1)
                extract_analysis_wav(prepared_audio2, activity_audio2)
            extract_analysis_wav(video1, video1_wav)
            extract_analysis_wav(video2, video2_wav)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "Could not extract audio for analysis. Check that the selected media contains audio."
            ) from exc

        report("Estimating sync offsets...")
        video2_shift = estimate_and_check(video1_wav, video2_wav, "VIDEO2", MIN_CORRELATION)
        if video_only_mode:
            audio2_shift = video2_shift
        else:
            audio1_shift = estimate_and_check(
                video1_wav, activity_audio1, "AUDIO1", MIN_CORRELATION
            )
            audio2_shift = estimate_and_check(
                video1_wav, activity_audio2, "AUDIO2", MIN_CORRELATION
            )

        report("Selecting camera cuts...")
        camera_by_frame = choose_camera_by_activity(
            activity_audio1, activity_audio2, audio1_shift, audio2_shift, duration,
            default_camera=default_camera,
        )
        export_camera_cuts(cuts_json, camera_by_frame, duration, video1, video2)

        if timeline_requested:
            report("Creating Resolve timeline XML with processed audio...")
            export_fcpxml(
                resolve_xml,
                camera_by_frame,
                duration,
                video1,
                video2,
                video1_duration=duration1,
                video2_duration=duration2,
                video2_shift=video2_shift,
                width=width,
                height=height,
                audio1=prepared_audio1,
                audio2=prepared_audio2,
                audio1_duration=probe_duration(prepared_audio1),
                audio2_duration=probe_duration(prepared_audio2),
                audio1_shift=audio1_shift,
                audio2_shift=audio2_shift,
            )
            report(f"Resolve XML: {resolve_xml}")

        if render_requested:
            report("Rendering final MP4. This may take a while...")
            render_video(
                video1=video1,
                audio1=prepared_audio1,
                audio2=prepared_audio2,
                video2=video2,
                output=output,
                duration=duration,
                width=width,
                height=height,
                shift1=audio1_shift,
                shift2=audio2_shift,
                video2_shift=video2_shift,
                camera_by_frame=camera_by_frame,
                envelope_rate=ENVELOPE_RATE,
            )
            report(f"Finished: {output}")

    report(f"Camera cut list: {cuts_json}")
