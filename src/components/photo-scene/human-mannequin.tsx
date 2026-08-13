"use client";

import { estimateLocalScale } from "@/lib/photo-scene/calibration";
import { renderedHeightPixels } from "@/lib/photo-scene/anthropometry";
import { getGroundPlaneStatus } from "@/lib/photo-scene/human-projection";
import type { HumanJointName, ReachDisplayMode, SceneCalibration, SceneHuman } from "@/types/photo-scene";

export type HumanDragKind = "HUMAN_ROOT" | "STANDING" | "JOINT" | "ORIENTATION";
type Point = { x: number; y: number };

export function HumanMannequin({ human, width, height, calibration, selected, reachVisible, reachMode, debug, zoom, onStart, onSelect }: {
  human: SceneHuman; width: number; height: number; calibration: SceneCalibration; selected: boolean;
  reachVisible: boolean; reachMode: ReachDisplayMode; debug: boolean; zoom: number;
  onStart: (kind: HumanDragKind, joint: HumanJointName | undefined, event: React.PointerEvent<SVGElement>) => void;
  onSelect: () => void;
}) {
  const j = human.pose.joints;
  const localScale = estimateLocalScale(calibration, human.placement.contactPoint, width, height);
  const pxPerCm = localScale?.pixelsPerCm ?? human.placement.lastScalePxPerCm ?? Math.max(0.4, height / 260);
  const d = human.profile.physicalDimensions;
  const selectedStroke = selected ? human.color : "#64748b";
  const yaw = ((human.placement.orientationDeg % 360) + 360) % 360;
  const leftBehind = yaw > 0 && yaw < 180;
  const reachCm = reachMode === "COMFORT" ? human.profile.functionalReachCm : reachMode === "FUNCTIONAL" ? human.profile.maximumReachCm * 0.9 : human.profile.maximumReachCm;
  const handles: HumanJointName[] = ["leftElbow", "rightElbow", "leftWrist", "rightWrist", "leftKnee", "rightKnee", "leftAnkle", "rightAnkle"];
  const limb = (side: "left" | "right") => <g key={side} opacity={leftBehind === (side === "left") ? 0.82 : 1}>
    <Capsule a={j[`${side}Hip`]} b={j[`${side}Knee`]} width={width} height={height} proximal={d.thighLengthCm * pxPerCm * 0.30} distal={d.thighLengthCm * pxPerCm * 0.22} fill="#263142" stroke={selectedStroke} />
    <Joint point={j[`${side}Knee`]} width={width} height={height} radius={d.lowerLegLengthCm * pxPerCm * 0.075} fill="#303b4c" />
    <Capsule a={j[`${side}Knee`]} b={j[`${side}Ankle`]} width={width} height={height} proximal={d.lowerLegLengthCm * pxPerCm * 0.22} distal={d.lowerLegLengthCm * pxPerCm * 0.14} fill="#202a39" stroke={selectedStroke} warning={human.pose.reachState[`${side}Leg`] === "OUT_OF_REACH"} />
    <Foot ankle={j[`${side}Ankle`]} toe={j[`${side}Foot`]} width={width} height={height} length={d.footLengthCm * pxPerCm} color={human.color} mirrored={side === "left"} />
    <Capsule a={j[`${side}Shoulder`]} b={j[`${side}Elbow`]} width={width} height={height} proximal={d.upperArmLengthCm * pxPerCm * 0.28} distal={d.upperArmLengthCm * pxPerCm * 0.20} fill="#2c3748" stroke={selectedStroke} />
    <Joint point={j[`${side}Elbow`]} width={width} height={height} radius={d.forearmLengthCm * pxPerCm * 0.07} fill="#344153" />
    <Capsule a={j[`${side}Elbow`]} b={j[`${side}Wrist`]} width={width} height={height} proximal={d.forearmLengthCm * pxPerCm * 0.22} distal={d.forearmLengthCm * pxPerCm * 0.14} fill="#222d3d" stroke={selectedStroke} warning={human.pose.reachState[`${side}Arm`] === "OUT_OF_REACH"} />
    <Hand wrist={j[`${side}Wrist`]} end={j[`${side}Hand`]} width={width} height={height} length={d.handLengthCm * pxPerCm} color={human.color} />
  </g>;

  return <g data-human-id={human.id} opacity={human.locked ? 0.72 : 1} onPointerDown={(event) => { event.stopPropagation(); onSelect(); }}>
    {reachVisible && selected && [j.leftShoulder, j.rightShoulder].map((shoulder, index) => <circle key={index} cx={shoulder.x * width} cy={shoulder.y * height} r={reachCm * pxPerCm} fill={withAlpha(human.color, 0.035)} stroke={human.color} strokeOpacity=".32" strokeWidth="1.5" strokeDasharray={reachMode === "COMFORT" ? undefined : reachMode === "FUNCTIONAL" ? "9 7" : "3 8"} pointerEvents="none" />)}
    {leftBehind ? limb("left") : limb("right")}
    <Torso human={human} width={width} height={height} pxPerCm={pxPerCm} selected={selected} onStart={onStart} />
    {leftBehind ? limb("right") : limb("left")}
    <Head human={human} width={width} height={height} pxPerCm={pxPerCm} selected={selected} />
    {selected && <line x1={human.placement.contactPoint.x * width} y1={human.placement.contactPoint.y * height} x2={j.head.x * width} y2={j.head.y * height} stroke={human.color} strokeOpacity=".35" strokeDasharray="5 7" pointerEvents="none" />}
    {selected && <text x={j.head.x * width + 9} y={j.head.y * height + 13} fill={human.color} fontSize="11" fontWeight="700">{human.profile.heightCm.toFixed(0)} cm</text>}
    {selected && zoom >= 0.8 && handles.map((name) => <circle key={name} cx={j[name].x * width} cy={j[name].y * height} r={Math.max(4, 6 / Math.max(0.8, zoom))} fill="#f8fafc" stroke={human.color} strokeWidth="2.5" onPointerDown={(event) => onStart("JOINT", name, event)} />)}
    {selected && <g onPointerDown={(event) => onStart("HUMAN_ROOT", "pelvisRoot", event)}><circle cx={j.pelvisRoot.x * width} cy={j.pelvisRoot.y * height} r="8" fill={human.color} stroke="white" strokeWidth="2" /><path d={`M${j.pelvisRoot.x * width - 4} ${j.pelvisRoot.y * height}h8M${j.pelvisRoot.x * width} ${j.pelvisRoot.y * height - 4}v8`} stroke="white" /></g>}
    {selected && <g onPointerDown={(event) => onStart("STANDING", undefined, event)}><circle cx={human.placement.contactPoint.x * width} cy={human.placement.contactPoint.y * height} r="9" fill="#0f172a" stroke={human.color} strokeWidth="3" /><circle cx={human.placement.contactPoint.x * width} cy={human.placement.contactPoint.y * height} r="2.5" fill="white" /></g>}
    {selected && <g onPointerDown={(event) => onStart("ORIENTATION", undefined, event)}><line x1={human.placement.contactPoint.x * width} y1={human.placement.contactPoint.y * height} x2={human.placement.contactPoint.x * width + Math.cos(yaw * Math.PI / 180) * 46} y2={human.placement.contactPoint.y * height + Math.sin(yaw * Math.PI / 180) * 46} stroke={human.color} strokeWidth="2" markerEnd="url(#dimension-arrow)" /></g>}
    {debug && <Debug human={human} width={width} height={height} pxPerCm={pxPerCm} scaleStatus={localScale?.status ?? "NO_SCALE"} ground={getGroundPlaneStatus(calibration)} />}
  </g>;
}

function Torso({ human, width, height, pxPerCm, selected, onStart }: { human: SceneHuman; width: number; height: number; pxPerCm: number; selected: boolean; onStart: Parameters<typeof HumanMannequin>[0]["onStart"] }) {
  const j = human.pose.joints, d = human.profile.physicalDimensions;
  const shoulder = middle(j.leftShoulder, j.rightShoulder), hip = middle(j.leftHip, j.rightHip), torsoLength = Math.max(1, Math.hypot((hip.x - shoulder.x) * width, (hip.y - shoulder.y) * height));
  const chest = d.chestWidthCm * pxPerCm, waist = d.waistWidthCm * pxPerCm, pelvis = d.pelvisWidthCm * pxPerCm;
  const path = bodyPath(shoulder, hip, width, height, chest, waist);
  return <g onPointerDown={(event) => onStart("HUMAN_ROOT", undefined, event)}>
    <path d={path} fill="#202b3a" stroke={selected ? human.color : "#64748b"} strokeWidth={selected ? 2.6 : 1.3} />
    <path d={`M${shoulder.x * width - chest * .36},${shoulder.y * height + torsoLength * .14} Q${shoulder.x * width},${shoulder.y * height + torsoLength * .30} ${shoulder.x * width + chest * .36},${shoulder.y * height + torsoLength * .14}`} fill="none" stroke="#94a3b8" strokeOpacity=".25" />
    <rect x={hip.x * width - pelvis / 2} y={hip.y * height - pelvis * .18} width={pelvis} height={pelvis * .42} rx={pelvis * .17} fill="#182231" stroke={human.color} strokeOpacity=".55" strokeWidth="1.5" />
    <Capsule a={j.neck} b={shoulder} width={width} height={height} proximal={d.neckLengthCm * pxPerCm * .55} distal={d.neckLengthCm * pxPerCm * .72} fill="#303b4b" stroke={human.color} />
  </g>;
}

function Head({ human, width, height, pxPerCm, selected }: { human: SceneHuman; width: number; height: number; pxPerCm: number; selected: boolean }) {
  const top = human.pose.joints.head, neck = human.pose.joints.neck, h = human.profile.physicalDimensions.headHeightCm * pxPerCm;
  const cx = top.x * width, cy = top.y * height + h * .5;
  const front = Math.cos(human.placement.orientationDeg * Math.PI / 180) >= 0;
  return <g><ellipse cx={cx} cy={cy} rx={h * .34} ry={h * .5} fill="#2b3646" stroke={selected ? human.color : "#718096"} strokeWidth="1.8" /><path d={`M${cx - h * .23},${cy + h * .18} Q${cx},${cy + h * .42} ${cx + h * .23},${cy + h * .18}`} fill="none" stroke="#cbd5e1" strokeOpacity=".38" /><line x1={cx + (front ? h * .20 : -h * .20)} y1={cy - h * .12} x2={cx + (front ? h * .27 : -h * .27)} y2={cy + h * .08} stroke={human.color} strokeOpacity=".75" strokeWidth="2" /><line x1={cx} y1={cy + h * .48} x2={neck.x * width} y2={neck.y * height} stroke="#2b3646" strokeWidth={Math.max(4, h * .25)} strokeLinecap="round" /></g>;
}

function Capsule({ a, b, width, height, proximal, distal, fill, stroke, warning = false }: { a: Point; b: Point; width: number; height: number; proximal: number; distal: number; fill: string; stroke: string; warning?: boolean }) {
  const points = segmentPolygon(a, b, width, height, proximal, distal);
  return <polygon points={points} fill={fill} stroke={warning ? "#f59e0b" : stroke} strokeOpacity={warning ? 1 : .55} strokeWidth={warning ? 2.4 : 1.2} strokeLinejoin="round" />;
}
function Joint({ point, width, height, radius, fill }: { point: Point; width: number; height: number; radius: number; fill: string }) { return <circle cx={point.x * width} cy={point.y * height} r={Math.max(2.5, radius)} fill={fill} stroke="#94a3b8" strokeOpacity=".28" />; }
function Hand({ wrist, end, width, height, length, color }: { wrist: Point; end: Point; width: number; height: number; length: number; color: string }) { const angle = angleDeg(wrist, end, width, height), cx = (wrist.x + end.x) / 2 * width, cy = (wrist.y + end.y) / 2 * height; return <g transform={`rotate(${angle} ${cx} ${cy})`}><rect x={cx - length * .38} y={cy - length * .22} width={length * .76} height={length * .44} rx={length * .18} fill="#1f2937" stroke={color} strokeWidth="1.3" /><path d={`M${cx + length * .19} ${cy - length * .17}l${length * .25} ${-length * .17}`} stroke={color} strokeWidth={Math.max(1.5, length * .07)} strokeLinecap="round" /></g>; }
function Foot({ ankle, toe, width, height, length, color, mirrored }: { ankle: Point; toe: Point; width: number; height: number; length: number; color: string; mirrored: boolean }) { const cx = (ankle.x + toe.x) / 2 * width + (mirrored ? -1 : 1) * length * .12, cy = Math.max(ankle.y, toe.y) * height - length * .08; return <path d={`M${cx - length * .42},${cy - length * .12} Q${cx - length * .20},${cy - length * .28} ${cx + length * .28},${cy - length * .18} Q${cx + length * .52},${cy - length * .08} ${cx + length * .46},${cy + length * .10} L${cx - length * .38},${cy + length * .10}Z`} fill="#151e2b" stroke={color} strokeWidth="1.4" />; }
function Debug({ human, width, height, pxPerCm, scaleStatus, ground }: { human: SceneHuman; width: number; height: number; pxPerCm: number; scaleStatus: string; ground: string }) { const p = human.placement.contactPoint; return <g pointerEvents="none"><rect x={p.x * width + 16} y={p.y * height - 86} width="190" height="75" rx="7" fill="rgba(2,6,23,.88)" stroke="#fb923c" /><text x={p.x * width + 24} y={p.y * height - 68} fill="#fed7aa" fontSize="10"><tspan x={p.x * width + 24}>Digital Human v1 · cm → pose → projection</tspan><tspan x={p.x * width + 24} dy="14">height: {human.profile.heightCm.toFixed(1)} cm / {renderedHeightPixels(human.pose, height).toFixed(1)} px</tspan><tspan x={p.x * width + 24} dy="14">scale: {pxPerCm.toFixed(3)} px/cm · {scaleStatus}</tspan><tspan x={p.x * width + 24} dy="14">root: {p.x.toFixed(3)}, {p.y.toFixed(3)} · yaw {human.placement.orientationDeg.toFixed(0)}°</tspan><tspan x={p.x * width + 24} dy="14">{ground} · IK {human.pose.reachState.leftArm}/{human.pose.reachState.rightArm}</tspan></text></g>; }

function segmentPolygon(a: Point, b: Point, width: number, height: number, proximal: number, distal: number) { const ax = a.x * width, ay = a.y * height, bx = b.x * width, by = b.y * height, length = Math.max(.001, Math.hypot(bx - ax, by - ay)), nx = -(by - ay) / length, ny = (bx - ax) / length; return `${ax + nx * proximal / 2},${ay + ny * proximal / 2} ${bx + nx * distal / 2},${by + ny * distal / 2} ${bx - nx * distal / 2},${by - ny * distal / 2} ${ax - nx * proximal / 2},${ay - ny * proximal / 2}`; }
function bodyPath(shoulder: Point, hip: Point, width: number, height: number, chest: number, waist: number) { const sx = shoulder.x * width, sy = shoulder.y * height, hx = hip.x * width, hy = hip.y * height, midY = sy + (hy - sy) * .62; return `M${sx - chest / 2},${sy} Q${sx - chest * .48},${midY * .65 + sy * .35} ${hx - waist / 2},${midY} Q${hx - waist * .56},${hy} ${hx},${hy} Q${hx + waist * .56},${hy} ${hx + waist / 2},${midY} Q${sx + chest * .48},${midY * .65 + sy * .35} ${sx + chest / 2},${sy}Z`; }
function middle(a: Point, b: Point) { return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; }
function angleDeg(a: Point, b: Point, width: number, height: number) { return Math.atan2((b.y - a.y) * height, (b.x - a.x) * width) * 180 / Math.PI; }
function withAlpha(hex: string, opacity: number) { return hex.startsWith("#") && hex.length === 7 ? `${hex}${Math.round(opacity * 255).toString(16).padStart(2, "0")}` : hex; }
