---
title: "Nexus Grid 3D: Three.js WebGL-Rendering"
service_scope: ["frontend"]
stack: ["typescript", "vue3", "three.js", "webgl"]
version_range: { "vue": ">=3.4", "typescript": ">=5.0", "three": ">=0.160" }
confidence: 0.5
source_epics: ["EPIC-PHASE-8"]
guards:
  - title: "Frontend Typecheck"
    command: "cd frontend && npm run typecheck"
  - title: "Frontend Build"
    command: "cd frontend && npm run build"
---

## Skill: Nexus Grid 3D (Three.js)

### Rolle
Du implementierst die 3D-Ansicht des Nexus Grid mit Three.js. Die bestehende 2D-Ansicht (Cytoscape) bleibt erhalten — ein Toggle-Button schaltet zwischen [2D] und [3D] um. Performance-Ziel: 1000 Nodes @ 30 FPS auf Mid-Range-GPU.

### Konventionen
- Composable: `src/composables/useNexusGrid3D.ts`
- Component: `src/components/HvNexusGrid3D.vue`
- Three.js Render-Loop **außerhalb** von Vue-Reaktivität — keine reaktiven Refs im Animation-Frame
- Design Tokens (CSS Variables) soweit möglich; GLSL-Shader für Fog-of-War
- Cleanup: `renderer.dispose()`, `scene.clear()`, Geometrien + Materialien disposen in `onBeforeUnmount`
- Lazy-Load: Three.js Bundle nur bei 3D-Ansicht importieren (`() => import('three')`)

### Performance-Strategie

| Technik | Zweck |
| --- | --- |
| `THREE.InstancedMesh` | Ein Draw-Call pro Node-Typ (statt 1000 einzelne) |
| Frustum Culling | Three.js Default (automatisch für Meshes) |
| Level-of-Detail (LOD) | Entfernte Nodes → 8-Polygon-Sphäre, nahe → 32-Polygon |
| `THREE.LineSegments` | Kanten als Buffer Geometry (kein individuelles Line Objekt) |
| Kein reaktiver Render-Loop | `requestAnimationFrame` statt Vue watch |
| Fog-of-War-Shader | GLSL auf Plane-Overlay (kein DOM-Element) |

### Grundstruktur

```typescript
// useNexusGrid3D.ts
import { onBeforeUnmount, ref, shallowRef } from 'vue'
import type { Scene, PerspectiveCamera, WebGLRenderer, InstancedMesh } from 'three'

export function useNexusGrid3D(container: Ref<HTMLElement | null>) {
  const scene = shallowRef<Scene | null>(null)
  const camera = shallowRef<PerspectiveCamera | null>(null)
  const renderer = shallowRef<WebGLRenderer | null>(null)
  let animationFrameId: number | null = null

  async function init() {
    const THREE = await import('three')
    const { OrbitControls } = await import('three/addons/controls/OrbitControls.js')

    scene.value = new THREE.Scene()
    scene.value.background = new THREE.Color(0x0a0e17) // --surface-base Token

    camera.value = new THREE.PerspectiveCamera(60, getAspect(), 0.1, 2000)
    camera.value.position.set(0, 100, 200)

    renderer.value = new THREE.WebGLRenderer({
      canvas: container.value!.querySelector('canvas')!,
      antialias: true,
      powerPreference: 'high-performance',
    })
    renderer.value.setPixelRatio(Math.min(window.devicePixelRatio, 2))

    const controls = new OrbitControls(camera.value, renderer.value.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.05

    animate()
  }

  function animate() {
    animationFrameId = requestAnimationFrame(animate)
    if (renderer.value && scene.value && camera.value) {
      renderer.value.render(scene.value, camera.value)
    }
  }

  onBeforeUnmount(() => {
    if (animationFrameId) cancelAnimationFrame(animationFrameId)
    renderer.value?.dispose()
    scene.value?.clear()
  })

  return { init, scene, camera, renderer }
}
```

### InstancedMesh für Nodes

```typescript
function createNodeInstances(nodes: NexusNode[], THREE: typeof import('three')) {
  // Gruppiere nach Node-Typ
  const groups = groupBy(nodes, n => n.type) // file, class, function, module

  const meshes: InstancedMesh[] = []

  for (const [type, typeNodes] of Object.entries(groups)) {
    const geometry = type === 'module'
      ? new THREE.BoxGeometry(2, 2, 2)
      : new THREE.SphereGeometry(1, getLODSegments(type), getLODSegments(type))

    const material = new THREE.MeshPhongMaterial({
      color: getNodeColor(type),  // Design Token Mapping
      transparent: true,
    })

    const mesh = new THREE.InstancedMesh(geometry, material, typeNodes.length)

    const matrix = new THREE.Matrix4()
    const color = new THREE.Color()

    typeNodes.forEach((node, i) => {
      matrix.setPosition(node.x, node.y, node.z)
      mesh.setMatrixAt(i, matrix)

      // Fog-of-War: unerkundete Nodes → transparent
      if (!node.explored) {
        color.set(0x333344)
        mesh.setColorAt(i, color)
        // Opacity via custom shader attribute
      }
    })

    mesh.instanceMatrix.needsUpdate = true
    meshes.push(mesh)
  }

  return meshes
}
```

### Kanten als LineSegments

```typescript
function createEdges(edges: NexusEdge[], nodePositions: Map<string, Vector3>, THREE: typeof import('three')) {
  const positions: number[] = []

  for (const edge of edges) {
    const from = nodePositions.get(edge.source)
    const to = nodePositions.get(edge.target)
    if (from && to) {
      positions.push(from.x, from.y, from.z, to.x, to.y, to.z)
    }
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))

  const material = new THREE.LineBasicMaterial({
    color: 0x334455, // --border-subtle Token
    transparent: true,
    opacity: 0.4,
  })

  return new THREE.LineSegments(geometry, material)
}
```

### Fog-of-War-Shader

```glsl
// fog_of_war.frag
uniform sampler2D exploredMap;  // Textur mit explored/unexplored Bereichen
varying vec2 vUv;

void main() {
  float explored = texture2D(exploredMap, vUv).r;
  float fogAlpha = mix(0.85, 0.0, explored);  // 85% fog für unerkundete Bereiche
  gl_FragColor = vec4(0.04, 0.06, 0.09, fogAlpha);  // --surface-base Farbton
}
```

### Datenquelle
- `GET /api/nexus/graph` → Nodes und Edges (selbe API wie 2D)
- `GET /api/nexus/graph?format=3d` → mit vorberechneten 3D-Koordinaten (force-directed Layout Backend-seitig)
- SSE: `nexus_updated`, `bug_aggregated` → Inkrementelle Updates

### Toggle 2D ↔ 3D

```vue
<template>
  <div class="hv-nexus-grid">
    <div class="hv-nexus-grid__toolbar">
      <button
        :class="{ active: mode === '2d' }"
        @click="mode = '2d'"
      >2D</button>
      <button
        :class="{ active: mode === '3d' }"
        @click="mode = '3d'"
      >3D</button>
    </div>

    <HvNexusGridCytoscape v-if="mode === '2d'" />
    <HvNexusGrid3D v-else />
  </div>
</template>
```

### Wichtige Regeln
- Vue-Reaktivität **nie** im `requestAnimationFrame`-Loop verwenden
- `shallowRef` für Three.js-Objekte (kein deep reactive proxy auf GPU-Objekten)
- Three.js als Dynamic Import (Code-Splitting — ~600KB Bundle)
- Alle Geometrien, Materialien und Texturen in `onBeforeUnmount` disposen
- pixelRatio auf max 2 begrenzen (Retina-Displays → sonst 4x Fillrate)
- Fog-of-War als Shader-Material auf Plane — kein DOM-Overlay
