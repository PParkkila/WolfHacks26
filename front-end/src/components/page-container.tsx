/** Width-limited page body. Container queries (`@…/main:`) size layouts to the
 * space left beside the docked assistant, not to the whole viewport. */
export function PageContainer({ children }: { children: React.ReactNode }) {
  return (
    <div className="@container/main">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 sm:p-6">
        {children}
      </div>
    </div>
  )
}
