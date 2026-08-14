import type { SceneState } from "../../types/photo-scene";
import { getHumanJointPositions3d } from "../photo-scene/human-3d-model.ts";
import type { SceneErgonomicsInput, SceneManualContext, SceneTaskSequence } from "./types.ts";
import { emptyManualContext } from "./types.ts";

export function buildSceneErgonomicsInput(sceneId:string,state:SceneState,options:{task?:SceneTaskSequence|null;manualContext?:SceneManualContext;calculatedAt?:string}={}):SceneErgonomicsInput {
  const sceneRevision=hashSceneState(state);
  return {
    schemaVersion:"scene-ergonomics-input-v1",sceneId,sceneRevision,sceneSchemaVersion:"1.4",
    calibrationQuality: state.calibration.scaleField.status==="PERSPECTIVE_GOOD"?"HIGH":state.calibration.scaleField.status==="LOCAL_ONLY"||state.calibration.scaleField.status==="PERSPECTIVE_PARTIAL"?"PARTIAL":"UNKNOWN",
    humans:state.humans.filter((h)=>h.visible).map((human)=>({id:human.id,profile:structuredClone(human.profile),rootPositionCm:{...human.human3d.rootPositionCm},rootRotationDeg:{...human.human3d.rootRotationDeg},jointPositionsCm:getHumanJointPositions3d(human.human3d),jointRotationsDeg:structuredClone(human.human3d.jointRotationsDeg),hands:{left:{preset:human.human3d.hands.left.preset},right:{preset:human.human3d.hands.right.preset}},heldObjectIds:[human.human3d.attachments.leftObjectId,human.human3d.attachments.rightObjectId].filter((id):id is string=>Boolean(id)),supportState:human.placement.positionMode==="SEATED_AT_OBJECT"?"SEATED":human.placement.floorPinned?"STANDING":"UNKNOWN",provenance:human.human3d.migrationStatus==="NATIVE_3D"?"USER_PROVIDED":"DERIVED"})),
    objects:state.objects.filter((object)=>object.visible&&object.status!=="USER_REJECTED").map((object)=>({id:object.id,name:object.name,type:object.type,geometry:object.geometry3d?structuredClone(object.geometry3d):null,interactionPoints:object.interactionPoints3d.map((point)=>({id:point.id,name:point.name,type:point.type,positionCm:{...point.positionCm},hand:point.hand})),provenance:object.geometry3d?.source==="USER_PROVIDED"?"USER_PROVIDED":object.geometry3d?.source==="DERIVED_FROM_CONFIRMED_DIMENSIONS"?"SCENE_CALIBRATED":object.geometry3d?"SCENE_ESTIMATED":"UNKNOWN"})),
    task:options.task??null,manualContext:options.manualContext??emptyManualContext(),createdAt:options.calculatedAt??new Date().toISOString(),
  };
}

export function hashSceneState(state:SceneState):string { const canonical=stableStringify(state);let hash=2166136261;for(let i=0;i<canonical.length;i++){hash^=canonical.charCodeAt(i);hash=Math.imul(hash,16777619)}return `fnv1a-${(hash>>>0).toString(16).padStart(8,"0")}`; }
function stableStringify(value:unknown):string { if(value===null||typeof value!=="object")return JSON.stringify(value);if(Array.isArray(value))return `[${value.map(stableStringify).join(",")}]`;const record=value as Record<string,unknown>;return `{${Object.keys(record).sort().map((key)=>`${JSON.stringify(key)}:${stableStringify(record[key])}`).join(",")}}`; }
