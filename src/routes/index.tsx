import { createFileRoute } from '@tanstack/react-router'
import { ArrowUpRight, Check, ChevronRight, CircleHelp, Download, Laptop, Menu, Smartphone, Tablet, X } from 'lucide-react'
import { useState } from 'react'

const assistants = [
  { id: 'chatgpt', name: 'ChatGPT', maker: 'OpenAI', mark: 'C', tone: 'bg-emerald-700', description: 'A versatile everyday assistant for writing, learning, planning, and creative work.', links: { windows: 'https://chatgpt.com/download', mac: 'https://chatgpt.com/download', ios: 'https://apps.apple.com/app/chatgpt/id6448311069', android: 'https://play.google.com/store/apps/details?id=com.openai.chatgpt' } },
  { id: 'claude', name: 'Claude', maker: 'Anthropic', mark: '✦', tone: 'bg-orange-700', description: 'A thoughtful partner for analysis, long documents, coding, and careful research.', links: { windows: 'https://claude.ai/download', mac: 'https://claude.ai/download', ios: 'https://apps.apple.com/app/claude-by-anthropic/id6473753684', android: 'https://play.google.com/store/apps/details?id=com.anthropic.claude' } },
  { id: 'gemini', name: 'Gemini', maker: 'Google', mark: '✧', tone: 'bg-indigo-700', description: 'Google’s assistant for brainstorming, multimodal questions, and connected work.', links: { windows: 'https://gemini.google.com/app', mac: 'https://gemini.google.com/app', ios: 'https://apps.apple.com/app/google-gemini/id6477489729', android: 'https://play.google.com/store/apps/details?id=com.google.android.apps.bard' } },
]

const devices = [
  { id: 'windows', label: 'Windows', icon: Laptop, note: 'Windows 10 or later' },
  { id: 'mac', label: 'Mac', icon: Laptop, note: 'macOS 13 or later' },
  { id: 'ios', label: 'iPhone / iPad', icon: Smartphone, note: 'iOS 16 or later' },
  { id: 'android', label: 'Android', icon: Tablet, note: 'Android 8 or later' },
] as const

type DeviceId = typeof devices[number]['id']

export const Route = createFileRoute('/')({
  head: () => ({ meta: [
    { title: 'How to Download AI Assistants · The Download Guide' },
    { name: 'description', content: 'Clear, official download instructions for ChatGPT, Claude, Gemini, and more.' },
  ] }),
  component: Home,
})

function Home() {
  const [selectedAssistant, setSelectedAssistant] = useState(assistants[0])
  const [device, setDevice] = useState<DeviceId>('windows')
  const [menuOpen, setMenuOpen] = useState(false)
  const downloadUrl = selectedAssistant.links[device]
  const isBrowserOnly = selectedAssistant.id === 'gemini' && (device === 'windows' || device === 'mac')

  return (
    <main className="min-h-dvh overflow-hidden bg-background">
      <header className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5 lg:px-10">
        <a href="#top" className="flex items-center gap-3 text-sm font-bold tracking-tight text-foreground">
          <span className="grid size-9 place-items-center rounded-full bg-primary font-serif text-lg text-primary-foreground">↓</span>
          The Download Guide
        </a>
        <nav className={`${menuOpen ? 'absolute inset-x-4 top-18 z-20 flex' : 'hidden'} items-center gap-7 rounded-2xl border border-border bg-card p-4 shadow-lg lg:static lg:flex lg:border-0 lg:bg-transparent lg:p-0 lg:shadow-none`}>
          <a href="#guides" onClick={() => setMenuOpen(false)} className="text-sm text-muted-foreground transition-colors hover:text-foreground">Guides</a>
          <a href="#steps" onClick={() => setMenuOpen(false)} className="text-sm text-muted-foreground transition-colors hover:text-foreground">How it works</a>
          <a href="#safety" onClick={() => setMenuOpen(false)} className="text-sm text-muted-foreground transition-colors hover:text-foreground">Safety first</a>
        </nav>
        <button onClick={() => setMenuOpen(!menuOpen)} className="grid size-10 place-items-center rounded-full border border-border text-foreground lg:hidden" aria-label="Toggle menu">
          {menuOpen ? <X size={18} /> : <Menu size={18} />}
        </button>
      </header>

      <section id="top" className="relative mx-auto max-w-7xl px-6 pb-16 pt-14 lg:px-10 lg:pb-24 lg:pt-24">
        <div className="pointer-events-none absolute -right-20 top-0 size-72 rounded-full bg-accent/25 blur-3xl" />
        <div className="relative grid items-end gap-12 lg:grid-cols-[1.05fr_.95fr] lg:gap-20">
          <div>
            <p className="mb-6 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.2em] text-primary"><span className="size-2 rounded-full bg-accent" />A calmer way to get started</p>
            <h1 className="max-w-3xl font-serif text-5xl leading-[0.98] tracking-[-0.04em] text-foreground sm:text-6xl lg:text-8xl">Download AI without the guesswork.</h1>
            <p className="mt-7 max-w-xl text-lg leading-8 text-muted-foreground">Choose an assistant, tell us what you’re using, and follow the official path. No confusing search results. No fake installers. Just the next right click.</p>
            <a href="#guides" className="mt-9 inline-flex items-center gap-3 rounded-full bg-primary px-6 py-3.5 text-sm font-bold text-primary-foreground shadow-md transition-transform hover:-translate-y-0.5 active:translate-y-0">Find your download <ChevronRight size={17} /></a>
          </div>
          <div className="relative min-h-80 rounded-[2rem] border border-border bg-card p-5 shadow-lg sm:p-7">
            <div className="flex items-center justify-between border-b border-border pb-5"><span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">START HERE / 01</span><CircleHelp size={18} className="text-primary" /></div>
            <div className="mt-8 flex items-start gap-5"><span className={`grid size-16 shrink-0 place-items-center rounded-2xl ${selectedAssistant.tone} font-serif text-3xl text-primary-foreground`}>{selectedAssistant.mark}</span><div><p className="font-serif text-3xl text-foreground">{selectedAssistant.name}</p><p className="mt-1 text-sm text-muted-foreground">{selectedAssistant.maker} · official app</p></div></div>
            <div className="mt-10 flex items-center gap-3 text-sm text-muted-foreground"><span className="grid size-7 place-items-center rounded-full bg-secondary text-xs font-bold text-secondary-foreground">1</span> Pick a device below <ChevronRight size={15} /><span className="grid size-7 place-items-center rounded-full bg-accent text-xs font-bold text-accent-foreground">2</span> Get the link</div>
          </div>
        </div>
      </section>

      <section id="guides" className="border-y border-border bg-secondary/45 px-6 py-16 lg:px-10 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <div className="mb-10 flex flex-col justify-between gap-4 md:flex-row md:items-end"><div><p className="font-mono text-[10px] uppercase tracking-[0.2em] text-primary">01 / Choose an assistant</p><h2 className="mt-3 font-serif text-4xl tracking-tight text-foreground lg:text-5xl">What are you trying?</h2></div><p className="max-w-sm text-sm leading-6 text-muted-foreground">Every link below points to the assistant’s official website or app store listing.</p></div>
          <div className="grid gap-4 lg:grid-cols-3">
            {assistants.map((assistant) => <button key={assistant.id} onClick={() => setSelectedAssistant(assistant)} className={`group rounded-2xl border p-6 text-left transition-all hover:-translate-y-1 hover:shadow-md ${selectedAssistant.id === assistant.id ? 'border-primary bg-card shadow-md' : 'border-border bg-background/50'}`}><div className="flex items-start justify-between"><span className={`grid size-12 place-items-center rounded-xl ${assistant.tone} font-serif text-2xl text-primary-foreground`}>{assistant.mark}</span>{selectedAssistant.id === assistant.id && <span className="grid size-7 place-items-center rounded-full bg-accent text-accent-foreground"><Check size={15} /></span>}</div><p className="mt-8 font-serif text-2xl text-foreground">{assistant.name}</p><p className="mt-2 text-sm leading-6 text-muted-foreground">{assistant.description}</p><span className="mt-6 inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-primary">Select guide <ArrowUpRight size={14} className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" /></span></button>)}
          </div>
        </div>
      </section>

      <section id="steps" className="mx-auto max-w-7xl px-6 py-16 lg:px-10 lg:py-24">
        <div className="grid gap-12 lg:grid-cols-[.75fr_1.25fr] lg:gap-24">
          <div><p className="font-mono text-[10px] uppercase tracking-[0.2em] text-primary">02 / Tell us your device</p><h2 className="mt-3 font-serif text-4xl tracking-tight text-foreground lg:text-5xl">The right app for the right screen.</h2><p className="mt-5 max-w-md text-sm leading-7 text-muted-foreground">Select where you want to use {selectedAssistant.name}. We’ll send you straight to the official download.</p></div>
          <div><div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{devices.map(({ id, label, icon: Icon, note }) => <button key={id} onClick={() => setDevice(id)} className={`rounded-2xl border p-4 text-left transition-all hover:-translate-y-0.5 ${device === id ? 'border-primary bg-primary text-primary-foreground shadow-md' : 'border-border bg-card text-foreground'}`}><Icon size={21} /><p className="mt-8 text-sm font-bold">{label}</p><p className={`mt-1 text-[11px] ${device === id ? 'text-primary-foreground/70' : 'text-muted-foreground'}`}>{note}</p></button>)}</div>
            <div className="mt-5 flex flex-col justify-between gap-5 rounded-2xl bg-primary p-6 text-primary-foreground sm:flex-row sm:items-center sm:p-8"><div><p className="font-mono text-[10px] uppercase tracking-[0.2em] text-primary-foreground/65">Your official link</p><p className="mt-2 font-serif text-2xl">{isBrowserOnly ? `Open ${selectedAssistant.name} in your browser` : `Download ${selectedAssistant.name} for ${devices.find((item) => item.id === device)?.label}`}</p><p className="mt-2 max-w-md text-sm leading-6 text-primary-foreground/70">{isBrowserOnly ? 'There is no separate desktop app listed here. The browser version is the official way to begin.' : 'You’ll leave this guide and continue on the official source.'}</p></div><a href={downloadUrl} target="_blank" rel="noreferrer" className="inline-flex shrink-0 items-center justify-center gap-2 rounded-full bg-accent px-5 py-3 text-sm font-bold text-accent-foreground transition-transform hover:scale-[1.03] active:scale-[.98]">{isBrowserOnly ? 'Open website' : 'Get the app'} <Download size={16} /></a></div>
          </div>
        </div>
      </section>

      <section id="safety" className="bg-foreground px-6 py-16 text-background lg:px-10 lg:py-20"><div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[.8fr_1.2fr] lg:items-center"><div><p className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">03 / Safety first</p><h2 className="mt-3 max-w-lg font-serif text-4xl tracking-tight lg:text-5xl">If it asks for money before it installs, pause.</h2></div><div className="grid gap-6 border-l border-background/20 pl-6 sm:grid-cols-3 sm:pl-8"><div><p className="font-bold text-accent">01</p><p className="mt-3 text-sm leading-6 text-background/70">Use the official links in this guide, not sponsored search results.</p></div><div><p className="font-bold text-accent">02</p><p className="mt-3 text-sm leading-6 text-background/70">Check the publisher name before installing any mobile app.</p></div><div><p className="font-bold text-accent">03</p><p className="mt-3 text-sm leading-6 text-background/70">Never share a password or payment details with a download page.</p></div></div></div></section>
      <footer className="mx-auto flex max-w-7xl flex-col gap-3 px-6 py-8 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between lg:px-10"><span>© 2026 The Download Guide</span><span>Links open official sites in a new tab.</span></footer>
    </main>
  )
}
