import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BarChart3, MessageCircle, Smartphone, Sparkles } from 'lucide-react'
import { api } from '../lib/api'
import { useBootstrap } from '../lib/bootstrap'
import { DiwaliChip, Footer } from '../components/AppHeader'
import { Badge, cx } from '../components/ui'

export default function Landing() {
  const boot = useBootstrap()
  const [health, setHealth] = useState<'warming' | 'ready' | 'offline'>('warming')

  useEffect(() => {
    let alive = true
    void api.warmStream()
    api
      .health()
      .then(() => alive && setHealth('ready'))
      .catch(() => alive && setHealth('offline'))
    return () => {
      alive = false
    }
  }, [])

  return (
    <>
      <main id="main" className="mx-auto max-w-[1280px] px-4 sm:px-6">
        {/* Hero */}
        <section className="grid items-center gap-10 pt-10 pb-14 lg:grid-cols-[1.05fr_1fr] lg:gap-14 lg:pt-16 lg:pb-20">
          <div className="anim-rise">
            <DiwaliChip />
            <h1 className="display mt-5 text-[52px] text-ink sm:text-[76px] lg:text-[92px]">Every conversation is a demand signal</h1>
            <p className="mt-6 max-w-[54ch] text-lg leading-relaxed text-ink-2">
              When a festive bestseller sells out, the shoppers who ask for it leave no trace in sales data, so the next forecast orders
              less. RetailNova captures every ask and plans stock around what customers actually wanted.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                to="/live"
                className="inline-flex h-12 items-center gap-2 rounded-xl bg-maroon px-5 text-[15px] font-semibold text-on-maroon hover:bg-maroon-hover"
              >
                Open the live loop
              </Link>
              <Link
                to="/shop"
                className="inline-flex h-12 items-center gap-2 rounded-xl border border-line-strong bg-surface px-5 text-[15px] font-semibold text-ink hover:bg-surface-2"
              >
                Shop as Priya
              </Link>
              <span className="flex items-center gap-1.5 text-xs text-ink-3" role="status">
                <span
                  className={cx(
                    'size-2 rounded-full',
                    health === 'ready' ? 'bg-leaf' : health === 'offline' ? 'bg-danger' : 'typing-dot bg-marigold',
                  )}
                  aria-hidden
                />
                {health === 'ready' ? 'Service ready' : health === 'offline' ? 'Service unreachable, retrying on first use' : 'Waking the service'}
              </span>
            </div>
          </div>
          <SignalSpecimen />
        </section>

        {/* 2-minute guide */}
        <section aria-labelledby="guide-title" className="border-t border-line py-12">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <h2 id="guide-title" className="display text-[36px] text-ink sm:text-[44px]">
              Test it in 2 minutes
            </h2>
            <p className="max-w-[46ch] text-sm text-ink-3">The live loop puts the shopper and the store manager side by side, sharing one session.</p>
          </div>
          <ol className="mt-8 grid gap-6 md:grid-cols-3 md:gap-0">
            {[
              {
                t: 'Ask as Priya',
                d: 'Ask for a maroon Kanchipuram silk saree at T. Nagar. It is sold out there, so tap Notify me.',
              },
              {
                t: 'Watch the radar',
                d: "Your ask lands in Arjun's live feed as unmet demand, next to forecasts built with and without it.",
              },
              {
                t: 'Approve the plan',
                d: 'Generate the Diwali action plan, approve the transfer, and Priya gets "Reserved for you at T. Nagar".',
              },
            ].map((s, i) => (
              <li key={s.t} className={cx('relative flex gap-4 md:block md:px-6', i === 0 && 'md:pl-0', i > 0 && 'md:border-l md:border-line')}>
                <span className="display block w-8 shrink-0 text-[48px] text-marigold md:w-auto md:text-[56px]" aria-hidden>
                  {i + 1}
                </span>
                <div>
                <h3 className="mt-1 text-lg font-semibold text-ink">
                  <span className="sr-only">Step {i + 1}: </span>
                  {s.t}
                </h3>
                <p className="mt-1.5 max-w-[40ch] text-[15px] text-ink-2">{s.d}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        {/* Entry points */}
        <section aria-labelledby="entry-title" className="pb-12">
          <h2 id="entry-title" className="sr-only">
            Choose a view
          </h2>
          <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr_1fr]">
            <Link
              to="/live"
              className="group relative flex min-h-[200px] flex-col justify-between gap-6 overflow-hidden rounded-3xl bg-maroon p-6 text-on-maroon lg:min-h-[220px]"
            >
              <div className="flex items-center justify-between">
                <Sparkles className="size-6 text-marigold" aria-hidden />
                <span className="rounded-full bg-marigold px-2.5 py-1 text-xs font-bold text-[#3b2400]">Recommended</span>
              </div>
              <div>
                <h3 className="display text-[38px]">Live loop</h3>
                <p className="mt-2 max-w-[44ch] text-[15px] text-white/85">
                  Shopper and store manager on one screen. Watch a conversation become a signal, a plan and a notification.
                </p>
                <span className="mt-4 inline-block text-sm font-semibold text-white underline decoration-marigold decoration-2 underline-offset-4">Open the live loop</span>
              </div>
            </Link>
            <EntryCard
              to="/shop"
              icon={<Smartphone className="size-6 text-maroon-ink" aria-hidden />}
              title="Shopper"
              who="Priya, shopping in Chennai"
              body="Chat or send a photo. See real stock at every store, then reserve or get notified."
            />
            <EntryCard
              to="/manager"
              icon={<BarChart3 className="size-6 text-maroon-ink" aria-hidden />}
              title="Store manager"
              who="Arjun, T. Nagar"
              body="Demand radar, two TimesFM forecasts and an ops copilot that proposes transfers you approve."
            />
          </div>
        </section>

        {/* Sample prompts */}
        <section aria-labelledby="prompts-title" className="border-t border-line py-12">
          <h2 id="prompts-title" className="flex items-center gap-2 text-lg font-semibold text-ink">
            <MessageCircle className="size-5 text-maroon-ink" aria-hidden />
            Start with a real question
          </h2>
          <p className="mt-1 text-sm text-ink-3">Each one opens the shopper chat and asks it for you. English, Hinglish and Tamil all work.</p>
          <div className="mt-5 flex flex-wrap gap-2">
            {boot.sample_prompts.shopper.map((p) => (
              <Link
                key={p}
                to={`/shop?q=${encodeURIComponent(p)}`}
                className="rounded-full border border-line-strong bg-surface px-4 py-2 text-[15px] font-medium text-ink hover:border-maroon-ink hover:text-maroon-ink"
              >
                {p}
              </Link>
            ))}
          </div>
        </section>
      </main>
      <Footer />
    </>
  )
}

function EntryCard({ to, icon, title, who, body }: { to: string; icon: React.ReactNode; title: string; who: string; body: string }) {
  return (
    <Link to={to} className="group flex flex-col justify-between gap-6 rounded-3xl border border-line bg-surface p-6 hover:border-line-strong lg:min-h-[220px]">
      {icon}
      <div>
        <h3 className="display text-[32px] text-ink">{title}</h3>
        <p className="text-sm font-semibold text-ink-3">{who}</p>
        <p className="mt-2 text-[15px] text-ink-2">{body}</p>
      </div>
    </Link>
  )
}

/** Hero illustration: one shopper ask becoming a signal, then the gap between two forecasts. */
function SignalSpecimen() {
  const d = (ms: number) => ({ animationDelay: `${ms}ms` })
  return (
    <figure className="relative" aria-label="Example: a shopper's question becomes a demand signal that raises the forecast">
      <div className="rounded-[28px] border border-line bg-surface p-5 sm:p-7">
        <div className="space-y-2.5">
          <div className="anim-rise flex justify-end" style={d(150)}>
            <p className="max-w-[80%] rounded-2xl rounded-br-md bg-maroon px-3.5 py-2 text-[15px] text-on-maroon">
              Do you have the maroon Kanchipuram silk saree? I need it before Diwali.
            </p>
          </div>
          <div className="anim-rise flex" style={d(500)}>
            <p className="max-w-[80%] rounded-2xl rounded-bl-md bg-surface-2 px-3.5 py-2 text-[15px] text-ink">
              It's sold out at T. Nagar. RS Puram has 14. Want me to notify you?
            </p>
          </div>
        </div>

        <div className="anim-rise mt-5 rounded-2xl border border-maroon/25 bg-maroon-soft p-4" style={d(950)}>
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-semibold text-maroon-ink">Demand signal captured</p>
            <Badge tone="maroon">Unmet: out of stock</Badge>
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
            {[
              ['Category', 'Sarees'],
              ['Colour', 'Maroon'],
              ['Store', 'T. Nagar'],
              ['Value', '₹4,799'],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-ink-3">{k}</dt>
                <dd className="font-semibold text-ink">{v}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="anim-rise mt-5" style={d(1350)}>
          <MiniForecast />
        </div>
      </div>
    </figure>
  )
}

function MiniForecast() {
  // Hand-tuned paths: sales-only (dashed) vs demand-sensed (maroon), the hatched gap between them, Diwali marker.
  const sales = 'M0,118 C60,114 110,108 160,96 C200,86 230,70 262,62 C290,70 320,92 360,104'
  const sensed = 'M0,112 C60,104 110,92 160,74 C200,58 230,34 262,24 C290,34 320,70 360,88'
  const gap = `${sensed} L360,104 C320,92 290,70 262,62 C230,70 200,86 160,96 C110,108 60,114 0,118 Z`
  return (
    <div>
      <svg viewBox="0 0 360 140" className="h-auto w-full" role="img" aria-label="Demand-sensed forecast runs well above the sales-only forecast into Diwali">
        <defs>
          <pattern id="hero-hatch" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="var(--marigold)" fillOpacity="0.2" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="var(--marigold)" strokeWidth="2.4" strokeOpacity="0.8" />
          </pattern>
        </defs>
        <line x1="0" y1="130" x2="360" y2="130" stroke="var(--line)" />
        <path d={gap} fill="url(#hero-hatch)" className="anim-fade" style={{ animationDelay: '1700ms' }} />
        <path d={sales} fill="none" stroke="var(--chart-sales)" strokeWidth="2" strokeDasharray="6 4" />
        <path
          d={sensed}
          fill="none"
          stroke="var(--chart-sensed)"
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray="420"
          style={{ ['--len' as string]: '420', animation: 'rn-draw 1100ms cubic-bezier(.3,.7,.2,1) 1500ms both' }}
        />
        <line x1="262" y1="6" x2="262" y2="130" stroke="var(--marigold)" strokeWidth="2" />
        <text x="268" y="14" fontSize="12" fontWeight="700" fill="var(--marigold-ink)">
          Diwali
        </text>
      </svg>
      <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-2">
        <span className="inline-flex items-center gap-1.5">
          <span className="w-5 border-t-2 border-dashed border-ink-3" aria-hidden />
          What sales say
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-[3px] w-5 rounded bg-[var(--chart-sensed)]" aria-hidden />
          What customers asked for
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="hatch h-3 w-5 rounded-sm" aria-hidden />
          Stock you would have missed
        </span>
      </div>
    </div>
  )
}
