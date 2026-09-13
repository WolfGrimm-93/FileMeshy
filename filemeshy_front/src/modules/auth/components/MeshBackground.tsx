/**
 * Fondo decorativo de /login: la "mesh" (red) que le da nombre a FileMeshy,
 * dibujada como un grafo de nodos conectados -- no una grilla ni blobs
 * genéricos. Un puñado de nodos se marcan como "documento" (mini rectángulos
 * redondeados) y otro puñado pulsa suavemente, sugiriendo una red viva de
 * archivos en movimiento. Colores y gradiente: paleta de marca en
 * docs/brand-guidelines.md (navy -> azul -> violeta -> cian).
 *
 * 100% decorativo: aria-hidden y pointer-events-none, no compite con el
 * formulario ni con lectores de pantalla.
 */

// Nodos del grafo (posiciones no alineadas a grilla, a propósito)
const NODES: Array<{ x: number; y: number }> = [
  { x: 80, y: 120 },
  { x: 220, y: 60 },
  { x: 340, y: 180 },
  { x: 140, y: 280 },
  { x: 400, y: 90 },
  { x: 520, y: 220 },
  { x: 300, y: 340 },
  { x: 600, y: 120 },
  { x: 700, y: 300 },
  { x: 480, y: 380 },
  { x: 820, y: 180 },
  { x: 900, y: 340 },
  { x: 760, y: 60 },
  { x: 150, y: 420 },
  { x: 60, y: 500 },
  { x: 380, y: 520 },
  { x: 900, y: 520 },
  { x: 950, y: 80 },
]

// Conexiones entre nodos (índices en NODES) -- un tejido orgánico, no una malla regular
const EDGES: Array<[number, number]> = [
  [0, 1],
  [1, 2],
  [2, 3],
  [3, 0],
  [2, 4],
  [4, 5],
  [5, 6],
  [6, 3],
  [5, 7],
  [7, 8],
  [8, 9],
  [9, 6],
  [8, 10],
  [10, 11],
  [11, 12],
  [12, 7],
  [13, 3],
  [13, 6],
  [13, 14],
  [14, 15],
  [15, 9],
  [15, 16],
  [16, 11],
  [10, 17],
  [17, 12],
]

// Nodos que representan un "documento" tejido en la red (índices en NODES)
const DOCUMENT_NODES = [2, 7, 9]

// Nodos que pulsan suavemente (índices en NODES), con delays distintos
const PULSING_NODES: Array<{ index: number; delay: string }> = [
  { index: 5, delay: '0s' },
  { index: 8, delay: '2s' },
  { index: 13, delay: '4s' },
]

export function MeshBackground() {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
      {/* Base: en claro, un tinte azulado muy suave; en oscuro, el navy de marca (Ink) */}
      <div className="absolute inset-0 bg-linear-to-br from-slate-50 via-blue-50/50 to-slate-100 dark:from-[#0B1638] dark:via-[#0E1D48] dark:to-[#0B1638]" />

      {/* Resplandor ambiental -- una sola fuente por esquina, no "blobs" repetidos */}
      <div
        className="absolute -top-1/3 -right-1/4 w-[60vw] h-[60vw] max-w-[720px] max-h-[720px] rounded-full blur-3xl opacity-[0.18] dark:opacity-[0.35]"
        style={{ background: 'radial-gradient(circle, #6552E0 0%, transparent 70%)' }}
      />
      <div
        className="absolute -bottom-1/3 -left-1/4 w-[55vw] h-[55vw] max-w-[640px] max-h-[640px] rounded-full blur-3xl opacity-[0.14] dark:opacity-[0.25]"
        style={{ background: 'radial-gradient(circle, #3A64D9 0%, transparent 70%)' }}
      />

      {/* La mesh: grafo de nodos + documentos tejidos */}
      <svg
        className="absolute inset-0 w-full h-full opacity-[0.18] dark:opacity-[0.4]"
        viewBox="0 0 1000 600"
        preserveAspectRatio="xMidYMid slice"
        fill="none"
      >
        <defs>
          <linearGradient id="fmMeshStroke" x1="0" y1="0" x2="1000" y2="600" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#0B1638" />
            <stop offset="35%" stopColor="#3A64D9" />
            <stop offset="70%" stopColor="#6552E0" />
            <stop offset="100%" stopColor="#22D3EE" />
          </linearGradient>
        </defs>

        <g stroke="url(#fmMeshStroke)" strokeWidth="1.25">
          {EDGES.map(([a, b], i) => {
            const from = NODES[a]
            const to = NODES[b]
            return <line key={i} x1={from.x} y1={from.y} x2={to.x} y2={to.y} />
          })}
        </g>

        <g fill="url(#fmMeshStroke)">
          {NODES.map((node, i) => {
            if (DOCUMENT_NODES.includes(i)) return null
            const pulse = PULSING_NODES.find((p) => p.index === i)
            return (
              <circle
                key={i}
                cx={node.x}
                cy={node.y}
                r={4}
                className={pulse ? 'mesh-node-pulse' : undefined}
                style={pulse ? { animationDelay: pulse.delay } : undefined}
              />
            )
          })}
        </g>

        {/* Documentos tejidos en la red -- el concepto de marca: mesh + archivos */}
        <g fill="url(#fmMeshStroke)">
          {DOCUMENT_NODES.map((i, idx) => {
            const node = NODES[i]
            const rotation = [8, -6, 10][idx % 3]
            return (
              <rect
                key={i}
                x={node.x - 8}
                y={node.y - 8}
                width={16}
                height={16}
                rx={3}
                opacity={0.85}
                transform={`rotate(${rotation} ${node.x} ${node.y})`}
              />
            )
          })}
        </g>
      </svg>
    </div>
  )
}
