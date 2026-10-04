export function participantHref(personId: string) {
  return `/clinician/participants/${encodeURIComponent(personId)}`
}
