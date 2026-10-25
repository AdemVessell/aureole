"""Render the authored Aureole sequence through UE 5.7 Movie Render Queue.

Run with UnrealEditor-Cmd ... -ExecutePythonScript=<this file>.  Configuration
is optional and is read from $LATTICE_RENDER_REQUEST, $RENDER_REQUEST_PATH, a
``--request=/absolute/path.json`` argument, or the repository's
``proof/RENDER_REQUEST.json``.

The custom frame end is exclusive.  The default 0..2 preview therefore emits
frames 0 and 1.  The authored sequence remains untouched: MRQ temporarily
overrides its playback range for this job only.
"""
import json
import os
from pathlib import Path
import sys
import traceback
import time

import unreal

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "proof"
PROOF.mkdir(parents=True, exist_ok=True)
DEFAULT_REQUEST = PROOF / "RENDER_REQUEST.json"
RESULT_PATH = PROOF / "RENDER_RESULT.json"
MAP_PATH = "/Game/Maps/Aureole"
SEQUENCE_PATH = "/Game/Sequences/LS_Aureole"

# Module globals intentionally retain UObjects and Python callables until MRQ ends.
EXECUTOR = None
QUEUE = None
JOB = None
REQUEST = None
ERRORS = []
START = time.perf_counter()


def _request_path():
    for value in (os.environ.get("LATTICE_RENDER_REQUEST"),
                  os.environ.get("RENDER_REQUEST_PATH")):
        if value:
            return value
    for arg in sys.argv:
        if arg.startswith("--request="):
            return arg.split("=", 1)[1]
    return str(DEFAULT_REQUEST)


def _load_request():
    path = _request_path()
    if not os.path.isfile(path):
        return {}, path
    with open(path, "r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("render request must be a JSON object: " + path)
    return value, path


def _resolution(request):
    value = request.get("resolution", [1280, 720])
    if isinstance(value, dict):
        width, height = value.get("width", 1280), value.get("height", 720)
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        width, height = value
    else:
        raise ValueError("resolution must be [width, height] or {width, height}")
    width, height = int(width), int(height)
    if width < 1 or height < 1:
        raise ValueError("resolution must be positive")
    return width, height


def _frame_range(request):
    # Defaults intentionally produce the requested two-frame preview.
    start = int(request.get("frame_start", request.get("start_frame", 0)))
    end = int(request.get("frame_end", request.get("end_frame", 2)))
    if end <= start:
        raise ValueError("frame_end is exclusive and must be greater than frame_start")
    return start, end


def _output_path(request):
    value = request.get("output_path", request.get("output_directory"))
    if not value:
        value = os.path.join(ROOT, "renders", "preview")
    candidate = Path(os.path.expanduser(str(value)))
    return str((ROOT / candidate).resolve() if not candidate.is_absolute() else candidate.resolve())


def _write_result(status, **fields):
    result = {
        "status": status,
        "engine": unreal.SystemLibrary.get_engine_version(),
        "map": MAP_PATH,
        "sequence": SEQUENCE_PATH,
        "elapsed_seconds": round(time.perf_counter()-START,3),
    }
    result.update(fields)
    try:
        with open(RESULT_PATH, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
    except Exception as exc:
        unreal.log_error("Could not write render receipt: {}".format(exc))


def _text(error_text):
    # FText's Python string conversion retains the text in UE 5.7.
    return str(error_text)


def _on_error(executor, pipeline, is_fatal, error_text):
    message = _text(error_text)
    ERRORS.append({"fatal": bool(is_fatal), "message": message})
    unreal.log_error("AUREOLE_MRQ_ERROR fatal={} {}".format(is_fatal, message))


def _on_finished(executor, success):
    global EXECUTOR, QUEUE, JOB
    successful = bool(success) and not any(item["fatal"] for item in ERRORS)
    _write_result(
        "success" if successful else "error",
        success=successful,
        request=REQUEST,
        errors=ERRORS,
    )
    unreal.log("AUREOLE_MRQ_FINISHED success={}".format(successful))
    # This paired call is required after set_keep_python_script_alive(True).
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    EXECUTOR = None
    QUEUE = None
    JOB = None
    unreal.SystemLibrary.quit_editor()


def render():
    global EXECUTOR, QUEUE, JOB, REQUEST
    REQUEST, request_path = _load_request()
    width, height = _resolution(REQUEST)
    start_frame, end_frame = _frame_range(REQUEST)
    output_dir = _output_path(REQUEST)
    os.makedirs(output_dir, exist_ok=True)

    if not unreal.EditorAssetLibrary.does_asset_exist(MAP_PATH):
        raise RuntimeError("missing map asset " + MAP_PATH)
    if not unreal.EditorAssetLibrary.does_asset_exist(SEQUENCE_PATH):
        raise RuntimeError("missing sequence asset " + SEQUENCE_PATH)

    # Verify evaluated engine state, not just the authored keyframes.
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    assert levels.load_level(MAP_PATH)
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    camera=next(a for a in actors if isinstance(a,unreal.CineCameraActor))
    lattice=next(a for a in actors if a.get_actor_label()=='Equation-defined lattice')
    location=lattice.get_actor_location()
    assert max(abs(v-e) for v,e in zip([location.x,location.y,location.z],[0,0,174]))<0.01, str(location)
    editor=unreal.LevelSequenceEditorBlueprintLibrary
    sequence=unreal.load_asset(SEQUENCE_PATH)
    assert editor.open_level_sequence(sequence)
    world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    collection=unreal.load_asset('/Game/Materials/MPC_Shot')
    with open(PROOF/'BUILD.json') as handle: expected=json.load(handle)['camera_samples']
    checks=[]
    for frame in [0,30,60,90,119]:
        editor.set_current_time(frame);editor.set_current_time(frame)
        value=unreal.MaterialLibrary.get_scalar_parameter_value(world,collection,'ShotTime')
        where=camera.get_actor_location()
        error=max(abs(v-e) for v,e in zip([where.x,where.y,where.z],expected[frame]['location']))
        checks.append({'frame':frame,'ShotTime':value,'expected_time':frame/24,'camera_error_cm':error})
        assert abs(value-frame/24)<1e-5 and error<0.01, str(checks[-1])
    editor.set_current_time(0);editor.close_level_sequence()
    with open(PROOF/'SEQUENCE_CHECK.json','w') as handle:
        json.dump({'status':'PASS','evaluated_in_unreal':True,'samples':checks},handle,indent=2)

    subsystem = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    QUEUE = subsystem.get_queue()
    QUEUE.delete_all_jobs()
    JOB = QUEUE.allocate_new_job(unreal.MoviePipelineExecutorJob)
    JOB.set_editor_property("map", unreal.SoftObjectPath(MAP_PATH))
    JOB.set_editor_property("sequence", unreal.SoftObjectPath(SEQUENCE_PATH))
    JOB.set_editor_property("author", "Aureole render_shot.py")

    config = JOB.get_configuration()
    output = config.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
    output.set_editor_property("output_resolution", unreal.IntPoint(width, height))
    directory=unreal.DirectoryPath()
    directory.set_editor_property("path",output_dir)
    output.set_editor_property("output_directory",directory)
    output.set_editor_property("file_name_format", "Aureole.{frame_number}")
    output.set_editor_property("zero_pad_frame_numbers", int(REQUEST.get("zero_pad", 4)))
    output.set_editor_property("auto_version", False)
    output.set_editor_property("version_number", 1)
    output.set_editor_property("override_existing_output", bool(REQUEST.get("override_existing", True)))
    output.set_editor_property("flush_disk_writes_per_shot", True)
    output.set_editor_property("use_custom_playback_range", True)
    output.set_editor_property("custom_start_frame", start_frame)
    output.set_editor_property("custom_end_frame", end_frame)
    output.set_editor_property("output_frame_step",max(1,int(REQUEST.get("frame_step",1))))

    config.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
    config.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_PNG)
    aa = config.find_or_add_setting_by_class(unreal.MoviePipelineAntiAliasingSetting)
    if REQUEST.get("disable_temporal_reprojection",False):
        aa.set_editor_property("override_anti_aliasing",True)
        aa.set_editor_property("anti_aliasing_method",unreal.AntiAliasingMethod.AAM_NONE)
    # ``aa_samples`` is a concise alias for the usual spatial-only preview.
    aa_samples = REQUEST.get("spatial_samples", REQUEST.get("aa_samples", 1))
    aa.set_editor_property("spatial_sample_count", max(1, int(aa_samples)))
    aa.set_editor_property("temporal_sample_count", max(1, int(REQUEST.get("temporal_samples", 1))))
    aa.set_editor_property("engine_warm_up_count", max(0, int(REQUEST.get("engine_warmup", 0))))
    aa.set_editor_property(
        "render_warm_up_count",
        max(0, int(REQUEST.get("render_warmup", REQUEST.get("warmup", 0)))),
    )

    _write_result(
        "started",
        request_path=request_path,
        request=REQUEST,
        output_path=output_dir,
        resolution=[width, height],
        frame_start=start_frame,
        frame_end_exclusive=end_frame,
        expected_frames=end_frame - start_frame,
    )
    unreal.log("AUREOLE_MRQ_STARTED {} {}x{} frames=[{}, {})".format(
        output_dir, width, height, start_frame, end_frame))

    # Epic's local sample explicitly requires globals for executor/callback lifetime.
    EXECUTOR = unreal.MoviePipelinePIEExecutor(subsystem)
    EXECUTOR.on_executor_errored_delegate.add_callable_unique(_on_error)
    EXECUTOR.on_executor_finished_delegate.add_callable_unique(_on_finished)
    unreal.EditorPythonScripting.set_keep_python_script_alive(True)
    subsystem.render_queue_with_executor_instance(EXECUTOR)


try:
    render()
except Exception:
    detail = traceback.format_exc()
    unreal.log_error("AUREOLE_MRQ_SETUP_ERROR\n" + detail)
    _write_result("error", success=False, request=REQUEST, errors=[{"fatal": True, "message": detail}])
    unreal.SystemLibrary.quit_editor()
