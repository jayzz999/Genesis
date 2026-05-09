import { useEffect, useRef } from 'react'
import {
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  Gauge,
  GitBranch,
  Network,
  Play,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
} from 'lucide-react'

function OrganismField() {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const pointer = { x: 0, y: 0, active: false }
    let width = 0
    let height = 0
    let frame = 0
    let rafId = 0
    let nodes = []

    const colors = ['#2dd4bf', '#38bdf8', '#f59e0b', '#a3e635', '#f472b6']

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      const ratio = Math.min(window.devicePixelRatio || 1, 2)
      width = rect.width
      height = rect.height
      canvas.width = Math.floor(width * ratio)
      canvas.height = Math.floor(height * ratio)
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0)

      const count = Math.max(42, Math.floor((width * height) / 19000))
      nodes = Array.from({ length: count }, (_, index) => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.34,
        vy: (Math.random() - 0.5) * 0.34,
        radius: 1.7 + Math.random() * 3.2,
        phase: Math.random() * Math.PI * 2,
        color: colors[index % colors.length],
      }))
    }

    const draw = () => {
      frame += 0.008
      ctx.clearRect(0, 0, width, height)

      const background = ctx.createLinearGradient(0, 0, width, height)
      background.addColorStop(0, '#05070a')
      background.addColorStop(0.42, '#071218')
      background.addColorStop(1, '#10110c')
      ctx.fillStyle = background
      ctx.fillRect(0, 0, width, height)

      ctx.save()
      ctx.globalAlpha = 0.33
      for (let i = 0; i < 5; i += 1) {
        const cx = width * (0.18 + i * 0.18) + Math.sin(frame + i) * 26
        const cy = height * (0.18 + (i % 3) * 0.23) + Math.cos(frame * 1.4 + i) * 34
        const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(width, height) * 0.32)
        glow.addColorStop(0, colors[i])
        glow.addColorStop(1, 'transparent')
        ctx.fillStyle = glow
        ctx.fillRect(0, 0, width, height)
      }
      ctx.restore()

      nodes.forEach((node) => {
        node.x += node.vx + Math.sin(frame + node.phase) * 0.08
        node.y += node.vy + Math.cos(frame + node.phase) * 0.08

        if (node.x < -20) node.x = width + 20
        if (node.x > width + 20) node.x = -20
        if (node.y < -20) node.y = height + 20
        if (node.y > height + 20) node.y = -20

        if (pointer.active) {
          const dx = node.x - pointer.x
          const dy = node.y - pointer.y
          const distance = Math.hypot(dx, dy)
          if (distance < 180) {
            const force = (180 - distance) / 1800
            node.vx += dx * force * 0.03
            node.vy += dy * force * 0.03
          }
        }

        node.vx *= 0.995
        node.vy *= 0.995
      })

      for (let i = 0; i < nodes.length; i += 1) {
        for (let j = i + 1; j < nodes.length; j += 1) {
          const a = nodes[i]
          const b = nodes[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const distance = Math.hypot(dx, dy)
          if (distance < 128) {
            ctx.strokeStyle = `rgba(125, 211, 252, ${0.22 * (1 - distance / 128)})`
            ctx.lineWidth = 1
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(b.x, b.y)
            ctx.stroke()
          }
        }
      }

      nodes.forEach((node) => {
        const pulse = 1 + Math.sin(frame * 6 + node.phase) * 0.22
        ctx.beginPath()
        ctx.fillStyle = node.color
        ctx.shadowColor = node.color
        ctx.shadowBlur = 18
        ctx.arc(node.x, node.y, node.radius * pulse, 0, Math.PI * 2)
        ctx.fill()
        ctx.shadowBlur = 0
      })

      const ringX = width * 0.72 + Math.sin(frame * 1.3) * 22
      const ringY = height * 0.46 + Math.cos(frame) * 16
      for (let ring = 0; ring < 4; ring += 1) {
        ctx.strokeStyle = `rgba(251, 191, 36, ${0.24 - ring * 0.04})`
        ctx.lineWidth = 1.4
        ctx.beginPath()
        ctx.ellipse(
          ringX,
          ringY,
          80 + ring * 34,
          24 + ring * 10,
          frame + ring * 0.45,
          0,
          Math.PI * 2,
        )
        ctx.stroke()
      }

      rafId = requestAnimationFrame(draw)
    }

    const movePointer = (event) => {
      const rect = canvas.getBoundingClientRect()
      pointer.x = event.clientX - rect.left
      pointer.y = event.clientY - rect.top
      pointer.active = true
    }

    resize()
    draw()
    window.addEventListener('resize', resize)
    window.addEventListener('pointermove', movePointer)
    window.addEventListener('pointerleave', () => {
      pointer.active = false
    })

    return () => {
      cancelAnimationFrame(rafId)
      window.removeEventListener('resize', resize)
      window.removeEventListener('pointermove', movePointer)
    }
  }, [])

  return <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" aria-hidden="true" />
}

const capabilities = [
  {
    icon: BrainCircuit,
    title: 'Reasoning organisms',
    body: 'Create agents with goals, skills, memory, mutation rules, and a clear chain of decisions.',
  },
  {
    icon: Network,
    title: 'Lineage and evolution',
    body: 'Track generations, inherited skills, failed mutations, repaired behaviors, and population runs.',
  },
  {
    icon: ShieldCheck,
    title: 'Audit-ready controls',
    body: 'Inspect every causal path, provider decision, lifecycle event, and benchmark result before promotion.',
  },
]

const workflow = [
  'Create an organism with a measurable business objective',
  'Connect approved tools and external systems',
  'Review proposed actions before execution',
  'Measure outcomes and promote reliable behavior',
]

const proof = [
  { label: 'Runtime', value: 'FastAPI + React', icon: TerminalSquare },
  { label: 'Provider', value: 'LLM-backed with dev mode', icon: BrainCircuit },
  { label: 'Traceability', value: 'Decision + causal graph', icon: GitBranch },
  { label: 'Readiness', value: 'Tests, health checks, Docker', icon: Gauge },
]

export default function GenesisLanding({ onEnter }) {
  return (
    <main className="min-h-screen bg-[#05070a] text-slate-50">
      <section className="relative min-h-[92vh] overflow-hidden">
        <OrganismField />
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(5,7,10,0.92),rgba(5,7,10,0.58)_44%,rgba(5,7,10,0.2))]" />
        <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-[#05070a] to-transparent" />

        <div className="relative z-10 mx-auto flex min-h-[92vh] w-full max-w-7xl flex-col px-5 sm:px-8 lg:px-10">
          <header className="flex items-center justify-between py-5">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-md border border-teal-300/30 bg-teal-300/10">
                <Sparkles className="h-5 w-5 text-teal-200" />
              </div>
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.24em] text-teal-100/80">Genesis</p>
                <p className="text-xs text-slate-300">Autonomous operations platform</p>
              </div>
            </div>
            <button
              type="button"
              onClick={onEnter}
              className="inline-flex h-10 items-center gap-2 rounded-md border border-white/15 bg-white/10 px-4 text-sm font-semibold text-white transition hover:border-teal-200/60 hover:bg-teal-200/15 focus:outline-none focus:ring-2 focus:ring-teal-200"
            >
              <Play className="h-4 w-4" />
              Open app
            </button>
          </header>

          <div className="grid flex-1 items-center gap-10 pb-10 pt-8 lg:grid-cols-[minmax(0,0.9fr)_minmax(300px,0.5fr)]">
            <div className="max-w-4xl">
              <div className="mb-6 inline-flex items-center gap-2 rounded-md border border-amber-200/20 bg-amber-200/10 px-3 py-2 text-sm text-amber-100">
                <CheckCircle2 className="h-4 w-4" />
                Production-oriented autonomy console
              </div>
              <h1 className="max-w-4xl text-6xl font-semibold leading-[0.92] tracking-normal text-white sm:text-7xl lg:text-8xl">
                Genesis
              </h1>
              <p className="mt-7 max-w-2xl text-lg leading-8 text-slate-200 sm:text-xl">
                A product platform for operating autonomous digital workers with memory, approvals,
                integrations, reliability metrics, and inspectable decisions.
              </p>
              <div className="mt-9 flex flex-col gap-3 sm:flex-row">
                <button
                  type="button"
                  onClick={onEnter}
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-md bg-teal-300 px-5 text-sm font-bold text-slate-950 transition hover:bg-teal-200 focus:outline-none focus:ring-2 focus:ring-teal-100"
                >
                  Open Genesis Console
                  <ArrowRight className="h-4 w-4" />
                </button>
                <a
                  href="#readiness"
                  className="inline-flex h-12 items-center justify-center rounded-md border border-white/15 px-5 text-sm font-semibold text-white transition hover:border-white/35 hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-white/40"
                >
                  View readiness
                </a>
              </div>
            </div>

            <aside className="hidden border-l border-white/10 pl-8 lg:block">
              <p className="text-sm font-semibold uppercase tracking-[0.22em] text-slate-400">Operating workflow</p>
              <div className="mt-5 space-y-4">
                {workflow.map((step, index) => (
                  <div key={step} className="flex gap-4">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-cyan-200/20 bg-cyan-200/10 text-sm font-bold text-cyan-100">
                      {index + 1}
                    </div>
                    <p className="pt-1 text-sm leading-6 text-slate-200">{step}</p>
                  </div>
                ))}
              </div>
            </aside>
          </div>

          <div className="relative grid gap-px overflow-hidden rounded-md border border-white/10 bg-white/10 md:grid-cols-4">
            {proof.map(({ label, value, icon: Icon }) => (
              <div key={label} className="bg-[#070b0d]/80 p-5">
                <Icon className="mb-4 h-5 w-5 text-amber-200" />
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{label}</p>
                <p className="mt-2 text-sm font-semibold text-slate-100">{value}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="readiness" className="border-t border-white/10 bg-[#05070a] px-5 py-16 sm:px-8 lg:px-10">
        <div className="mx-auto max-w-7xl">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold uppercase tracking-[0.24em] text-teal-200">Product platform</p>
            <h2 className="mt-4 text-3xl font-semibold tracking-normal text-white sm:text-4xl">
              A control room for autonomous work.
            </h2>
            <p className="mt-4 text-base leading-7 text-slate-300">
              Genesis turns agent behavior into something observable, permissioned, repeatable, and
              promotable instead of a black-box automation script.
            </p>
          </div>

          <div className="mt-10 grid gap-4 lg:grid-cols-3">
            {capabilities.map(({ icon: Icon, title, body }) => (
              <article key={title} className="rounded-md border border-white/10 bg-white/[0.04] p-6">
                <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-md bg-teal-300/10 text-teal-200">
                  <Icon className="h-5 w-5" />
                </div>
                <h3 className="text-lg font-semibold text-white">{title}</h3>
                <p className="mt-3 text-sm leading-6 text-slate-300">{body}</p>
              </article>
            ))}
          </div>

          <div className="mt-12 grid gap-6 border-y border-white/10 py-10 lg:grid-cols-[0.55fr_0.45fr]">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.24em] text-amber-200">Production posture</p>
              <h2 className="mt-4 text-3xl font-semibold tracking-normal text-white">Autonomy with controls.</h2>
            </div>
            <p className="text-base leading-7 text-slate-300">
              The value is in making autonomous systems governable: lifecycle control, skill inheritance,
              benchmark testing, causal inspection, approvals, connector safety, and production health in one product.
            </p>
          </div>
        </div>
      </section>
    </main>
  )
}
