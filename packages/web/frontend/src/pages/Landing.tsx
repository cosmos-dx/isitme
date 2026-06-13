import { Link } from "react-router-dom";
import { GoogleButton } from "../components/GoogleButton";
import { Logo } from "../components/Logo";
import { useAuth } from "../hooks/useAuth";

function Nav() {
  const { user } = useAuth();
  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-ink-950/70 backdrop-blur-xl">
      <div className="container-content flex h-16 items-center justify-between">
        <Logo />
        <nav className="hidden items-center gap-8 text-sm text-neutral-400 md:flex">
          <a href="#how" className="transition-colors hover:text-neutral-100">
            How it works
          </a>
          <a href="#privacy" className="transition-colors hover:text-neutral-100">
            Privacy
          </a>
        </nav>
        {user ? (
          <Link to="/dashboard" className="btn-ghost">
            Open dashboard
          </Link>
        ) : (
          <GoogleButton label="Sign in" className="!px-4 !py-2" />
        )}
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div className="grid-bg pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_at_top,black,transparent_72%)]" />
      <div
        className="pointer-events-none absolute left-1/2 top-[-10%] h-[420px] w-[820px] -translate-x-1/2 rounded-full opacity-30 blur-3xl"
        style={{
          background:
            "radial-gradient(closest-side, rgba(124,92,255,0.55), rgba(34,211,238,0.18), transparent)",
        }}
      />
      <div className="container-content relative pb-24 pt-24 sm:pt-32">
        <div className="mx-auto max-w-3xl text-center">
          <span className="eyebrow animate-fade-in">Local-first · portable cognition</span>
          <h1 className="mt-6 animate-fade-up text-balance text-5xl font-semibold leading-[1.05] tracking-tightest text-neutral-50 sm:text-6xl">
            Your portable
            <br />
            online brain.
          </h1>
          <p
            className="mx-auto mt-6 max-w-xl animate-fade-up text-pretty text-lg leading-relaxed text-neutral-400"
            style={{ animationDelay: "0.06s" }}
          >
            isitme quietly turns your browsing, searches, and AI chats into a weighted
            knowledge graph that lives on your machine — then lets any LLM or browser
            recall the real you.
          </p>
          <div
            className="mt-9 flex animate-fade-up flex-col items-center justify-center gap-3 sm:flex-row"
            style={{ animationDelay: "0.12s" }}
          >
            <GoogleButton />
            <a href="#how" className="btn-ghost">
              See how it works
            </a>
          </div>
          <p
            className="mt-5 animate-fade-in text-xs text-neutral-600"
            style={{ animationDelay: "0.2s" }}
          >
            Runs entirely on localhost. Your data never leaves your machine.
          </p>
        </div>
      </div>
    </section>
  );
}

const STEPS = [
  {
    n: "01",
    title: "Capture",
    body: "A lightweight browser extension records what you actually do online — visits, searches, dwell, opinions, LLM chats — with redaction before anything is stored.",
  },
  {
    n: "02",
    title: "Graph",
    body: "The Central Brain weaves those signals into a typed knowledge graph: domains, topics, queries and opinions linked by time-decayed edges that fade as you move on.",
  },
  {
    n: "03",
    title: "Recall",
    body: "Point any LLM or tool at your brain over MCP. It recalls your interests, decisions, and context — so the model speaks as the real you, anywhere.",
  },
];

function HowItWorks() {
  return (
    <section id="how" className="border-t border-white/[0.06] py-24">
      <div className="container-content">
        <div className="max-w-2xl">
          <span className="eyebrow">How it works</span>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-neutral-100 sm:text-4xl">
            Capture → graph → recall, across any LLM or browser.
          </h2>
        </div>
        <div className="mt-14 grid gap-px overflow-hidden rounded-2xl border border-white/[0.07] bg-white/[0.05] md:grid-cols-3">
          {STEPS.map((s) => (
            <div key={s.n} className="bg-ink-950 p-8">
              <div className="font-mono text-sm text-accent-soft tnum">{s.n}</div>
              <h3 className="mt-5 text-lg font-medium text-neutral-100">{s.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-neutral-400">{s.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

const PRIVACY = [
  { k: "Local-first", v: "The brain runs on 127.0.0.1 and stores everything in SQLite under your own data directory." },
  { k: "Redacted at capture", v: "Passwords, banking, health, secrets, and PII are scrubbed before anything is ever written." },
  { k: "You hold the keys", v: "Issue scoped API keys for the extension and MCP clients — and revoke them in one click." },
  { k: "No cloud by default", v: "Optional encrypted sync is off unless you turn it on. Nothing leaves your machine otherwise." },
];

function Privacy() {
  return (
    <section id="privacy" className="border-t border-white/[0.06] py-24">
      <div className="container-content grid gap-14 md:grid-cols-[0.9fr_1.1fr]">
        <div>
          <span className="eyebrow">Privacy · local-first</span>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-neutral-100 sm:text-4xl">
            A second brain you actually own.
          </h2>
          <p className="mt-5 max-w-md text-sm leading-relaxed text-neutral-400">
            Most “memory” products ship your life to someone else’s server. isitme
            inverts that: the graph is yours, on your disk, behind your keys.
          </p>
        </div>
        <dl className="grid gap-px overflow-hidden rounded-2xl border border-white/[0.07] bg-white/[0.05] sm:grid-cols-2">
          {PRIVACY.map((p) => (
            <div key={p.k} className="bg-ink-950 p-6">
              <dt className="text-sm font-medium text-neutral-100">{p.k}</dt>
              <dd className="mt-2 text-sm leading-relaxed text-neutral-500">{p.v}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

function CTA() {
  return (
    <section className="border-t border-white/[0.06] py-24">
      <div className="container-content text-center">
        <h2 className="mx-auto max-w-xl text-3xl font-semibold tracking-tight text-neutral-100 sm:text-4xl">
          See how your brain looks.
        </h2>
        <p className="mx-auto mt-4 max-w-md text-sm text-neutral-400">
          Sign in to explore your knowledge graph in 3D, manage keys, and wire up
          your MCP clients.
        </p>
        <div className="mt-8 flex justify-center">
          <GoogleButton />
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-white/[0.06] py-10">
      <div className="container-content flex flex-col items-center justify-between gap-4 text-sm text-neutral-500 sm:flex-row">
        <Logo />
        <p className="text-neutral-600">Local-first personal cognition · runs on your machine</p>
        <a href="#how" className="transition-colors hover:text-neutral-300">
          Back to top
        </a>
      </div>
    </footer>
  );
}

export default function Landing() {
  return (
    <div className="min-h-screen">
      <Nav />
      <main>
        <Hero />
        <HowItWorks />
        <Privacy />
        <CTA />
      </main>
      <Footer />
    </div>
  );
}
