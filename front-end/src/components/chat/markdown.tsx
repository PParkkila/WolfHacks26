import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"

const components: Components = {
  p: (props) => <p className="leading-relaxed" {...props} />,
  ul: (props) => (
    <ul className="flex list-disc flex-col gap-1 pl-5" {...props} />
  ),
  ol: (props) => (
    <ol className="flex list-decimal flex-col gap-1 pl-5" {...props} />
  ),
  strong: (props) => <strong className="font-semibold" {...props} />,
  a: (props) => (
    <a
      className="underline underline-offset-3"
      target="_blank"
      rel="noreferrer"
      {...props}
    />
  ),
  h1: (props) => <h3 className="font-semibold" {...props} />,
  h2: (props) => <h3 className="font-semibold" {...props} />,
  h3: (props) => <h3 className="font-semibold" {...props} />,
  code: (props) => (
    <code
      className="rounded bg-muted px-1 py-0.5 font-mono text-xs"
      {...props}
    />
  ),
  table: (props) => (
    <div className="overflow-x-auto">
      <table className="w-full text-xs" {...props} />
    </div>
  ),
  th: (props) => (
    <th className="border-b px-2 py-1 text-left font-medium" {...props} />
  ),
  td: (props) => <td className="border-b px-2 py-1 tabular-nums" {...props} />,
}

/** Assistant text: GitHub-flavoured markdown, styled with the app's tokens. */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="flex flex-col gap-2">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  )
}
