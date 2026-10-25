"""Create the Unreal scene and sequence from authored equations.

The package is relocatable: all source inputs and sanitized receipts are
resolved relative to this script's repository root.
"""
from pathlib import Path
import unreal as U,math,json,traceback,os
ROOT=Path(__file__).resolve().parents[1]
PROOF=ROOT/'proof';PROOF.mkdir(parents=True,exist_ok=True)
AT=U.AssetToolsHelpers.get_asset_tools(); ML=U.MaterialEditingLibrary
def asset(name,folder,cls,factory):
    return U.load_asset(folder+'/'+name) or AT.create_asset(name,folder,cls,factory)
def expression(mat,cls,**props):
    obj=ML.create_material_expression(mat,cls)
    for k,v in props.items(): obj.set_editor_property(k,v)
    return obj
def scalar(mat,value,prop):
    n=expression(mat,U.MaterialExpressionConstant,r=value);ML.connect_material_property(n,'',prop)
def vector(mat,value,prop):
    n=expression(mat,U.MaterialExpressionConstant3Vector,constant=U.LinearColor(*value,1));ML.connect_material_property(n,'',prop)
def custom(mat,code,inputs):
    node=expression(mat,U.MaterialExpressionCustom,code=code,output_type=U.CustomMaterialOutputType.CMOT_FLOAT3)
    ci=[]
    for name,source in inputs.items():
        c=U.CustomInput();c.set_editor_property('input_name',name);ci.append(c)
    node.set_editor_property('inputs',ci)
    for name,source in inputs.items(): ML.connect_material_expressions(source,'',node,name)
    return node
def basic_material(name,colour,metal,rough):
    m=asset(name,'/Game/Materials',U.Material,U.MaterialFactoryNew());ML.delete_all_material_expressions(m)
    vector(m,colour,U.MaterialProperty.MP_BASE_COLOR);scalar(m,metal,U.MaterialProperty.MP_METALLIC);scalar(m,rough,U.MaterialProperty.MP_ROUGHNESS)
    return m
def spawn(cls,name,pos,rot=None):
    obj=U.get_editor_subsystem(U.EditorActorSubsystem).spawn_actor_from_class(cls,U.Vector(*pos),rot or U.Rotator())
    obj.set_actor_label(name);return obj
def look(pos,target): return U.MathLibrary.find_look_at_rotation(U.Vector(*pos),U.Vector(*target))
def save(obj): U.EditorAssetLibrary.save_loaded_asset(obj)
def import_file(file,name):
    path='/Game/Geometry/'+name
    if U.EditorAssetLibrary.does_asset_exist(path): return U.load_asset(path)
    task=U.AssetImportTask();task.filename=file;task.destination_path='/Game/Geometry';task.destination_name=name;task.automated=True;task.replace_existing=True;task.save=True
    if file.endswith('.fbx'):
        opt=U.FbxImportUI();opt.import_mesh=True;opt.import_materials=False;opt.import_textures=False;opt.import_as_skeletal=False
        opt.static_mesh_import_data.set_editor_property('combine_meshes',True)
        opt.static_mesh_import_data.set_editor_property('normal_import_method',U.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
        opt.static_mesh_import_data.set_editor_property('generate_lightmap_u_vs',False)
        task.options=opt
    AT.import_asset_tasks([task]);obj=U.load_asset(path)
    if obj is None:
        paths=task.imported_object_paths
        if paths: obj=U.load_asset(paths[0])
    if obj is None: raise RuntimeError('Import failed '+file)
    return obj
def build():
    levels=U.get_editor_subsystem(U.LevelEditorSubsystem)
    if U.EditorAssetLibrary.does_asset_exist('/Game/Maps/Aureole'):
        if not levels.load_level('/Game/Maps/Aureole'): raise RuntimeError('Cannot load owned Aureole map')
        actors=U.get_editor_subsystem(U.EditorActorSubsystem)
        for old in actors.get_all_level_actors():
            if isinstance(old,(U.StaticMeshActor,U.SkyLight,U.RectLight,U.PostProcessVolume,U.CineCameraActor)): actors.destroy_actor(old)
    elif not levels.new_level('/Game/Maps/Aureole'): raise RuntimeError('Cannot create Aureole map')
    mesh=import_file(str(ROOT/'geometry/gyroid_lattice_fine.fbx'),'GyroidFine')
    mesh_tools=U.get_editor_subsystem(U.StaticMeshEditorSubsystem)
    mesh_settings=mesh_tools.get_lod_build_settings(mesh,0)
    mesh_settings.set_editor_property('recompute_normals',False)
    mesh_settings.set_editor_property('use_high_precision_tangent_basis',True)
    mesh_settings.set_editor_property('distance_field_resolution_scale',2.0)
    mesh_tools.set_lod_build_settings(mesh,0,mesh_settings);save(mesh)
    cube=import_file(str(ROOT/'geometry/studio.hdr'),'StudioEnvironment')
    mpc=asset('MPC_Shot','/Game/Materials',U.MaterialParameterCollection,U.MaterialParameterCollectionFactoryNew())
    p=U.CollectionScalarParameter();p.set_editor_property('parameter_name','ShotTime');p.set_editor_property('default_value',0)
    mpc.set_editor_property('scalar_parameters',[p]);save(mpc)
    metal=basic_material('M_ChampagneSilver',[.82,.80,.74],1.0,.28)
    metal.set_editor_property('tangent_space_normal',False)
    pos=expression(metal,U.MaterialExpressionWorldPosition)
    centre=expression(metal,U.MaterialExpressionConstant3Vector,constant=U.LinearColor(0,0,174,1))
    local=expression(metal,U.MaterialExpressionSubtract)
    ML.connect_material_expressions(pos,'',local,'A');ML.connect_material_expressions(centre,'',local,'B')
    time=expression(metal,U.MaterialExpressionCollectionParameter,collection=mpc,parameter_name='ShotTime')
    deformation='''float phase=6.28318530718*T/5.0;
float k=0.62*sin(phase-1.57079632679);
float a=1.0+0.055*sin(phase);
float theta=k*P.z/150.0; float c=cos(theta),s=sin(theta);
float3 q=a*float3(c*P.x-s*P.y,s*P.x+c*P.y,P.z);
return q-P;'''
    wpo=custom(metal,deformation,{'P':local,'T':time});ML.connect_material_property(wpo,'',U.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    normal=expression(metal,U.MaterialExpressionVertexNormalWS)
    normalcode='''float k=0.62*sin(6.28318530718*T/5.0-1.57079632679)/150.0;
float theta=k*P.z; float c=cos(theta),s=sin(theta);
float3 n=float3(c*N.x-s*N.y,s*N.x+c*N.y,N.z+k*(P.y*N.x-P.x*N.y));
return normalize(n);'''
    nc=custom(metal,normalcode,{'P':local,'T':time,'N':normal})
    interp=expression(metal,U.MaterialExpressionVertexInterpolator)
    assert ML.connect_material_expressions(nc,'',interp,'VS');assert ML.connect_material_property(interp,'',U.MaterialProperty.MP_NORMAL)
    ML.recompile_material(metal);save(metal)
    obj=spawn(U.StaticMeshActor,'Equation-defined lattice',(0,0,174));comp=obj.static_mesh_component
    comp.set_static_mesh(mesh);comp.set_material(0,metal);comp.set_mobility(U.ComponentMobility.MOVABLE);comp.set_editor_property('bounds_scale',1.35)
    floor_mat=basic_material('M_Obsidian',[.035,.045,.060],.35,.24);ML.recompile_material(floor_mat);save(floor_mat)
    floor=spawn(U.StaticMeshActor,'Obsidian stage',(0,0,0));floor.static_mesh_component.set_static_mesh(U.load_asset('/Engine/BasicShapes/Plane'));floor.set_actor_scale3d(U.Vector(80,80,1));floor.static_mesh_component.set_material(0,floor_mat);floor.set_actor_hidden_in_game(True)
    sky=spawn(U.SkyLight,'Procedural studio environment',(0,0,500));sc=sky.light_component
    sc.set_editor_property('source_type',U.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP);sc.set_editor_property('cubemap',cube);sc.set_intensity(1.5);sc.set_mobility(U.ComponentMobility.MOVABLE)
    for name,where,power,colour,width,height in [('Silver softbox',(-350,-300,430),110000,[.70,.84,1],350,500),('Champagne rim',(300,190,350),150000,[1,.65,.30],220,420),('Top silk',(20,50,620),100000,[.80,.9,1],350,240),('Quiet front',(100,-460,180),90000,[.65,.8,1],180,260)]:
        light=spawn(U.RectLight,name,where,look(where,(0,0,174)));lc=light.light_component
        lc.set_mobility(U.ComponentMobility.MOVABLE);lc.set_editor_property('intensity_units',U.LightUnits.LUMENS);lc.set_intensity(power);lc.set_light_color(U.LinearColor(*colour,1));lc.set_editor_property('source_width',width);lc.set_editor_property('source_height',height);lc.set_editor_property('attenuation_radius',2400)
    pp=spawn(U.PostProcessVolume,'Cinematic exposure',(0,0,0));pp.set_editor_property('unbound',True)
    settings=pp.get_editor_property('settings')
    for k,v in {'override_auto_exposure_method':True,'auto_exposure_method':U.AutoExposureMethod.AEM_MANUAL,'override_auto_exposure_bias':True,'auto_exposure_bias':0.0,'override_bloom_intensity':True,'bloom_intensity':.12,'override_vignette_intensity':True,'vignette_intensity':.22,'override_motion_blur_amount':True,'motion_blur_amount':.25}.items(): settings.set_editor_property(k,v)
    pp.set_editor_property('settings',settings)
    camera=spawn(U.CineCameraActor,'Camera — arc and approach',(450,-630,245),look((450,-630,245),(0,0,174)))
    cc=camera.get_cine_camera_component();cc.set_editor_property('current_focal_length',40.0);cc.set_editor_property('current_aperture',5.6)
    film=cc.get_editor_property('filmback');film.sensor_width=36.0;film.sensor_height=20.25;cc.set_editor_property('filmback',film)
    fs=cc.get_editor_property('focus_settings');fs.focus_method=U.CameraFocusMethod.MANUAL;fs.manual_focus_distance=710;cc.set_editor_property('focus_settings',fs)
    seq=asset('LS_Aureole','/Game/Sequences',U.LevelSequence,U.LevelSequenceFactoryNew())
    for tr in seq.get_tracks(): seq.remove_track(tr)
    for binding in seq.get_bindings(): binding.remove()
    seq.set_display_rate(U.FrameRate(24,1));seq.set_playback_start(0);seq.set_playback_end(120)
    binding=seq.add_possessable(camera)
    track=binding.add_track(U.MovieScene3DTransformTrack);section=track.add_section();section.set_range(0,120)
    channels=section.get_all_channels()
    camera_samples=[]
    for frame in range(121):
        t=frame/24;s=t/5;ease=s*s*(3-2*s)
        angle=math.radians(-57+24*ease);radius=770-100*ease
        location=(radius*math.cos(angle),radius*math.sin(angle),245-25*ease)
        rotation=look(location,(0,0,172));values=[*location,rotation.roll,rotation.pitch,rotation.yaw,1.,1.,1.]
        for ch,val in zip(channels,values): ch.add_key(U.FrameNumber(frame),val,interpolation=U.MovieSceneKeyInterpolation.LINEAR)
        camera_samples.append({'frame':frame,'time':t,'location':location,'rotation_rpy':[rotation.roll,rotation.pitch,rotation.yaw]})
    cuts=seq.add_track(U.MovieSceneCameraCutTrack);cut=cuts.add_section();cut.set_range(0,120)
    bid=U.MovieSceneObjectBindingID();bid.set_editor_property('guid',binding.get_id());cut.set_camera_binding_id(bid)
    mt=seq.add_track(U.MovieSceneMaterialParameterCollectionTrack);mt.set_editor_property('mpc',mpc);ms=mt.add_section();ms.set_range(0,120)
    # ParameterSection keys use sequence tick units, unlike scripting channel add_key.
    tick=seq.get_tick_resolution();end_tick=round(5.0*tick.numerator/tick.denominator)
    ms.add_scalar_parameter_key('ShotTime',U.FrameNumber(0),0.0,U.MovieSceneKeyInterpolation.LINEAR);ms.add_scalar_parameter_key('ShotTime',U.FrameNumber(end_tick),5.0,U.MovieSceneKeyInterpolation.LINEAR)
    save(seq);U.get_editor_subsystem(U.LevelEditorSubsystem).save_current_level()
    U.EditorAssetLibrary.save_directory('/Game',only_if_is_dirty=False,recursive=True)
    seq_editor=U.LevelSequenceEditorBlueprintLibrary
    assert seq_editor.open_level_sequence(seq)
    world=U.get_editor_subsystem(U.UnrealEditorSubsystem).get_editor_world()
    readback=[]
    for frame in [0,30,60,90,119]:
        seq_editor.set_current_time(frame);seq_editor.set_current_time(frame)
        actual=U.MaterialLibrary.get_scalar_parameter_value(world,mpc,'ShotTime')
        where=camera.get_actor_location();expected=camera_samples[frame]['location']
        camera_error=max(abs(v-e) for v,e in zip([where.x,where.y,where.z],expected))
        readback.append({'frame':frame,'ShotTime':actual,'expected_time':frame/24,'camera_max_error_cm':camera_error})
        assert abs(actual-frame/24)<1e-5 and camera_error<0.01, str(readback[-1])
    seq_editor.set_current_time(0);seq_editor.close_level_sequence()
    receipt={'engine':U.SystemLibrary.get_engine_version(),'mesh':mesh.get_path_name(),'bounds':str(mesh.get_bounds()),'sequence':seq.get_path_name(),'duration':5,'fps':24,'frames':120,'deformation_hlsl':deformation,'normal_hlsl':normalcode,'camera_samples':camera_samples,'sequence_readback':readback,'environment':'Authored procedural HDR studio, scripts/make_studio.py','render_pending':True}
    (PROOF/'BUILD.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    U.log('AUREOLE_BUILD_COMPLETE');U.SystemLibrary.quit_editor()
try: build()
except Exception:
    error=traceback.format_exc();(PROOF/'BUILD_ERROR.txt').write_text(error,encoding='utf-8');U.log_error(error);U.SystemLibrary.quit_editor()
