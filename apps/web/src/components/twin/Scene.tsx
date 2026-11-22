"use client";

import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Component, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import URDFLoader, { type URDFRobot } from "urdf-loader";
import type { Pose } from "@/lib/twin";

export type SceneStatus = { state: "loading" | "ready" | "error"; message?: string; meshes?: number };

export type SceneProps = {
  urdf: string;
  files: string[];
  fetchFile: (path: string) => Promise<ArrayBuffer>;
  pose: Pose | null;
  joints: Record<string, number>;
  selected: string | null;
  onSelect: (link: string | null) => void;
  onStatus: (s: SceneStatus) => void;
  /** Where the base goes, in ROS coordinates (x forward, y left, metres): the camera frames it. */
  frame: { cx: number; cy: number; radius: number };
  view: "perspective" | "top";
  viewNonce: number;
};

/** The colours come from the design tokens (globals.css), read at draw time: no colour is written in this file. */
function token(name: string, fallback = "#888888"): string {
  if (typeof document === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function Controls({ frame, view, viewNonce }: Pick<SceneProps, "frame" | "view" | "viewNonce">) {
  const { camera, gl } = useThree();
  const controls = useRef<OrbitControls | null>(null);
  useEffect(() => {
    const c = new OrbitControls(camera, gl.domElement);
    c.enableDamping = false;
    controls.current = c;
    return () => c.dispose();
  }, [camera, gl]);
  useEffect(() => {
    const c = controls.current;
    if (!c) return;
    const r = Math.max(frame.radius, 0.8);
    c.target.set(frame.cx, 0.1, -frame.cy); // ROS (x, y) -> scene (x, -y)
    if (view === "top") camera.position.set(frame.cx, r * 2.4, -frame.cy + 0.001);
    else camera.position.set(frame.cx + r * 0.9, r * 0.7, -frame.cy + r * 1.1);
    c.update();
  }, [camera, frame.cx, frame.cy, frame.radius, view, viewNonce]);
  useFrame(() => controls.current?.update());
  return null;
}

function linkOf(o: THREE.Object3D | null): string | null {
  for (let n: THREE.Object3D | null = o; n; n = n.parent) if ((n as { isURDFLink?: boolean }).isURDFLink) return (n as THREE.Object3D & { urdfName: string }).urdfName || n.name;
  return null;
}

function Robot({ urdf, files, fetchFile, pose, joints, selected, onSelect, onStatus }: SceneProps) {
  const [robot, setRobot] = useState<URDFRobot | null>(null);
  const fetchRef = useRef(fetchFile);
  fetchRef.current = fetchFile;
  const statusRef = useRef(onStatus);
  statusRef.current = onStatus;

  useEffect(() => {
    let dead = false;
    let pending = 0;
    let loaded = 0;
    const manager = new THREE.LoadingManager();
    const loader = new URDFLoader(manager);
    loader.packages = "model:"; // package://<pkg>/<path> becomes model:/<pkg>/<path>; matched to the version's files below
    loader.loadMeshCb = (path, _mgr, material, done) => {
      const rel = files.find((f) => path.endsWith("/" + f));
      if (!rel) {
        done(new THREE.Object3D(), new Error(`the model has no file for ${path}`));
        return;
      }
      pending++;
      fetchRef.current(rel)
        .then((buf) => {
          if (dead) return;
          const geometry = new STLLoader().parse(buf);
          done(new THREE.Mesh(geometry, material));
          loaded++;
        })
        .catch((e: unknown) => {
          if (!dead) {
            statusRef.current({ state: "error", message: e instanceof Error ? e.message : "a mesh could not be loaded" });
            done(new THREE.Object3D(), e instanceof Error ? e : new Error("mesh"));
          }
        })
        .finally(() => {
          pending--;
          if (!dead && pending === 0) statusRef.current({ state: "ready", meshes: loaded });
        });
    };
    statusRef.current({ state: "loading" });
    try {
      const r = loader.parse(urdf);
      setRobot(r);
      if (files.length === 0) statusRef.current({ state: "ready", meshes: 0 });
    } catch (e) {
      statusRef.current({ state: "error", message: e instanceof Error ? e.message : "the URDF could not be read" });
    }
    return () => {
      dead = true;
    };
  }, [urdf, files]);

  useEffect(() => {
    if (!robot) return;
    for (const [name, v] of Object.entries(joints)) if (robot.joints[name]) robot.setJointValue(name, v);
  }, [robot, joints]);

  // For tests and for anyone inspecting the page: where the model's root really is in the scene, in ROS metres.
  const where = useMemo(() => new THREE.Vector3(), []);
  useFrame(({ gl }) => {
    if (!robot) return;
    robot.getWorldPosition(where);
    gl.domElement.dataset["robotXy"] = `${where.x.toFixed(3)},${(-where.z).toFixed(3)}`;
  });

  const accent = useMemo(() => new THREE.Color(token("--color-accent")), [selected]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!robot) return;
    robot.traverse((o) => {
      const m = o as THREE.Mesh;
      if (!m.isMesh || !(m.material as THREE.MeshPhongMaterial).emissive) return;
      const on = selected !== null && linkOf(m) === selected;
      const mat = m.material as THREE.MeshPhongMaterial;
      mat.emissive.copy(on ? accent : new THREE.Color(0, 0, 0));
      mat.emissiveIntensity = on ? 0.55 : 0;
    });
  }, [robot, selected, accent]);

  if (!robot) return null;
  const click = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    onSelect(linkOf(e.object));
  };
  return (
    // URDF is Z-up; the scene is Y-up. The base pose from /tf places the model's root (base_footprint) on the ground.
    <group rotation={[-Math.PI / 2, 0, 0]}>
      <group position={[pose?.x ?? 0, pose?.y ?? 0, 0]} rotation={[0, 0, pose?.yaw ?? 0]} onClick={click}>
        <primitive object={robot} />
      </group>
    </group>
  );
}

class Boundary extends Component<{ onError: (m: string) => void; children: ReactNode }, { failed: boolean }> {
  override state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  override componentDidCatch(e: Error) {
    this.props.onError(e.message);
  }
  override render() {
    return this.state.failed ? null : this.props.children;
  }
}

export default function Scene(props: SceneProps) {
  const [grid] = useState(() => ({ major: token("--color-line"), minor: token("--color-line") }));
  return (
    <Boundary onError={(m) => props.onStatus({ state: "error", message: m })}>
      <Canvas
        camera={{ fov: 40, near: 0.05, far: 200, position: [2, 1.5, 2] }}
        gl={{ antialias: true, alpha: true }}
        onPointerMissed={() => props.onSelect(null)}
        data-testid="twin-canvas"
      >
        <ambientLight intensity={0.9} />
        <directionalLight position={[3, 6, 2]} intensity={1.6} />
        <directionalLight position={[-4, 3, -3]} intensity={0.5} />
        <gridHelper args={[20, 40, grid.major, grid.minor]} />
        <Controls frame={props.frame} view={props.view} viewNonce={props.viewNonce} />
        <Robot {...props} />
      </Canvas>
    </Boundary>
  );
}
