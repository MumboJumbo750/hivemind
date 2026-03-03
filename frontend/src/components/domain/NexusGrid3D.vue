<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import type { Node3DItem, Edge3DItem } from '../../api/types'

// ─── Props ──────────────────────────────────────────────────────────────────

const props = defineProps<{
  nodes: Node3DItem[]
  edges: Edge3DItem[]
}>()

// ─── Three.js imports ───────────────────────────────────────────────────────

// Use type-only THREE namespace so we can do a runtime dynamic import
import type * as THREEType from 'three'
import type { OrbitControls as OrbitControlsType } from 'three/addons/controls/OrbitControls.js'

// ─── State ──────────────────────────────────────────────────────────────────

const canvasRef = ref<HTMLCanvasElement | null>(null)
const threeError = ref<string | null>(null)
const nodeCount = ref(0)

let renderer: THREEType.WebGLRenderer | null = null
let scene: THREEType.Scene | null = null
let camera: THREEType.PerspectiveCamera | null = null
let controls: OrbitControlsType | null = null
let animFrameId: number | null = null
let THREE: typeof THREEType | null = null

// ─── Node type color map ─────────────────────────────────────────────────────

const NODE_COLORS: Record<string, number> = {
  file:     0x4a9eff,
  module:   0x7c3aed,
  class:    0x10b981,
  function: 0xf59e0b,
}
const NODE_COLOR_DEFAULT = 0x7f92b3

// ─── Build scene ────────────────────────────────────────────────────────────

function buildScene() {
  if (!THREE || !scene) return

  // Clear previous objects (except lights/camera)
  const toRemove: THREEType.Object3D[] = []
  scene.traverse(obj => {
    if (obj instanceof THREE!.Mesh || obj instanceof THREE!.LineSegments || obj instanceof THREE!.InstancedMesh) {
      toRemove.push(obj)
    }
  })
  toRemove.forEach(o => scene!.remove(o))

  const nodes = props.nodes
  const edges = props.edges
  nodeCount.value = nodes.length

  if (nodes.length === 0) return

  // ── Build node-id → index map ──
  const indexMap = new Map<string, number>(nodes.map((n, i) => [n.id, i]))

  // ── Group nodes by type for instancing ──
  const typeGroups = new Map<string, Node3DItem[]>()
  for (const n of nodes) {
    const t = n.type ?? 'file'
    if (!typeGroups.has(t)) typeGroups.set(t, [])
    typeGroups.get(t)!.push(n)
  }

  const sphereGeo = new THREE.SphereGeometry(0.5, 10, 8)

  for (const [type, group] of typeGroups) {
    const color = NODE_COLORS[type] ?? NODE_COLOR_DEFAULT
    const mat = new THREE.MeshPhongMaterial({ color, transparent: true })
    const mesh = new THREE.InstancedMesh(sphereGeo, mat, group.length)
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage)

    const dummy = new THREE.Object3D()
    for (let i = 0; i < group.length; i++) {
      const n = group[i]
      dummy.position.set(n.x ?? 0, n.y ?? 0, n.z ?? 0)
      dummy.scale.setScalar(n.fog_of_war ? 0.6 : 1.0)
      dummy.updateMatrix()
      mesh.setMatrixAt(i, dummy.matrix)

      // Per-instance opacity via color alpha (fog-of-war nodes dimmed)
      const opacity = n.fog_of_war ? 0.3 : 1.0
      const c = new THREE.Color(color)
      // Store opacity via the color channel trick — we use instance color
      c.multiplyScalar(opacity < 1 ? 0.3 : 1.0)
      mesh.setColorAt(i, c)
    }
    mesh.instanceMatrix.needsUpdate = true
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true

    scene.add(mesh)
  }

  // ── Edges — single LineSegments draw call ──
  if (edges.length > 0) {
    const positions: number[] = []
    for (const edge of edges) {
      const si = indexMap.get(edge.source)
      const ti = indexMap.get(edge.target)
      if (si === undefined || ti === undefined) continue
      const src = nodes[si]
      const tgt = nodes[ti]
      positions.push(src.x ?? 0, src.y ?? 0, src.z ?? 0)
      positions.push(tgt.x ?? 0, tgt.y ?? 0, tgt.z ?? 0)
    }

    if (positions.length > 0) {
      const edgeGeo = new THREE.BufferGeometry()
      edgeGeo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
      const edgeMat = new THREE.LineBasicMaterial({ color: 0x223a63, opacity: 0.5, transparent: true })
      const lines = new THREE.LineSegments(edgeGeo, edgeMat)
      scene.add(lines)
    }
  }
}

// ─── Init Three.js ──────────────────────────────────────────────────────────

async function initThree() {
  if (!canvasRef.value) return

  try {
    // Dynamic import — fails gracefully if three is not installed
    const [threeModule, { OrbitControls }] = await Promise.all([
      import('three'),
      import('three/addons/controls/OrbitControls.js'),
    ])
    THREE = threeModule

    const canvas = canvasRef.value
    const w = canvas.clientWidth || canvas.offsetWidth || 800
    const h = canvas.clientHeight || canvas.offsetHeight || 600

    // Renderer
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true })
    renderer.setSize(w, h, false)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setClearColor(0x000000, 0)

    // Scene
    scene = new THREE.Scene()
    scene.fog = new THREE.FogExp2(0x0a0e1a, 0.006)

    // Camera
    camera = new THREE.PerspectiveCamera(60, w / h, 0.1, 5000)
    camera.position.set(0, 50, 150)

    // Lights
    const ambient = new THREE.AmbientLight(0xffffff, 0.6)
    const point = new THREE.PointLight(0x4a9eff, 1.5, 800)
    point.position.set(0, 100, 0)
    scene.add(ambient, point)

    // Controls
    controls = new OrbitControls(camera, canvas)
    controls.enableDamping = true
    controls.dampingFactor = 0.06

    // Build geometry
    buildScene()

    // Render loop
    function animate() {
      animFrameId = requestAnimationFrame(animate)
      controls?.update()
      if (renderer && scene && camera) renderer.render(scene, camera)
    }
    animate()

    // Resize observer
    const ro = new ResizeObserver(() => {
      if (!canvas || !renderer || !camera) return
      const nw = canvas.clientWidth
      const nh = canvas.clientHeight
      renderer.setSize(nw, nh, false)
      camera.aspect = nw / nh
      camera.updateProjectionMatrix()
    })
    ro.observe(canvas)

  } catch (err: unknown) {
    threeError.value = err instanceof Error ? err.message : 'Three.js konnte nicht geladen werden.'
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => void initThree())

onUnmounted(() => {
  if (animFrameId !== null) cancelAnimationFrame(animFrameId)
  controls?.dispose()
  renderer?.dispose()
})

watch(() => [props.nodes, props.edges], () => {
  if (THREE && scene) buildScene()
}, { deep: true })
</script>

<template>
  <div class="nexus3d-wrapper">
    <!-- Unavailable fallback -->
    <div v-if="threeError" class="nexus3d-unavailable">
      <span class="nexus3d-unavailable__icon">!</span>
      <span>3D nicht verfügbar: {{ threeError }}</span>
    </div>

    <template v-else>
      <!-- Node count overlay -->
      <div class="nexus3d-overlay">
        <span class="nexus3d-count mono">{{ nodeCount }} Nodes</span>
      </div>

      <!-- Three.js canvas -->
      <canvas ref="canvasRef" class="nexus3d-canvas" />
    </template>
  </div>
</template>

<style scoped>
.nexus3d-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  background: var(--color-bg, #0a0e1a);
  overflow: hidden;
}

.nexus3d-canvas {
  display: block;
  width: 100%;
  height: 100%;
}

.nexus3d-overlay {
  position: absolute;
  top: var(--space-3);
  left: var(--space-3);
  z-index: 10;
  pointer-events: none;
}

.nexus3d-count {
  background: color-mix(in srgb, var(--color-surface) 80%, transparent);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 2px var(--space-2);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.nexus3d-unavailable {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  justify-content: center;
  height: 100%;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.nexus3d-unavailable__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 1px solid var(--color-text-muted);
  font-size: var(--font-size-xs);
  flex-shrink: 0;
}
</style>
