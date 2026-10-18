import { Fragment, type ReactNode } from 'react'

/** Minimal, safe rendering for model text: paragraphs, "- " bullets and **bold**. No HTML injection. */
function inline(text: string, keyBase: string): ReactNode[] {
  const out: ReactNode[] = []
  const re = /\*\*([^*]+)\*\*/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(<Fragment key={`${keyBase}-t${i++}`}>{text.slice(last, m.index)}</Fragment>)
    out.push(
      <strong key={`${keyBase}-b${i++}`} className="font-semibold text-ink">
        {m[1]}
      </strong>,
    )
    last = m.index + m[0].length
  }
  if (last < text.length) out.push(<Fragment key={`${keyBase}-t${i++}`}>{text.slice(last)}</Fragment>)
  return out
}

export function RichText({ text, className }: { text: string; className?: string }) {
  const blocks: ReactNode[] = []
  const lines = text.replace(/\r/g, '').split('\n')
  let list: string[] = []
  let para: string[] = []
  const flushPara = () => {
    if (para.length) {
      const k = `p${blocks.length}`
      blocks.push(<p key={k}>{inline(para.join(' '), k)}</p>)
      para = []
    }
  }
  const flushList = () => {
    if (list.length) {
      const k = `l${blocks.length}`
      blocks.push(
        <ul key={k} className="list-disc space-y-1 pl-5 marker:text-ink-3">
          {list.map((li, j) => (
            <li key={j}>{inline(li, `${k}-${j}`)}</li>
          ))}
        </ul>,
      )
      list = []
    }
  }
  for (const raw of lines) {
    const line = raw.trimEnd()
    const bullet = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/)
    if (bullet) {
      flushPara()
      list.push(bullet[1])
    } else if (!line.trim()) {
      flushPara()
      flushList()
    } else {
      flushList()
      para.push(line.replace(/^#+\s*/, ''))
    }
  }
  flushPara()
  flushList()
  return <div className={className ?? 'space-y-2'}>{blocks}</div>
}
