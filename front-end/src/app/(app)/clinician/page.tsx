"use client"

import { CohortOverview } from "@/components/clinician/cohort-overview"
import { ParticipantTable } from "@/components/clinician/participant-table"
import { PageContainer } from "@/components/page-container"
import { RoleGate } from "@/components/role-gate"

export default function ClinicianPage() {
  return (
    <RoleGate role="clinician">
      <PageContainer>
        <header className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold tracking-tight">Cohort</h1>
          <p className="text-muted-foreground">
            Everyone&apos;s newest Gluco Score and sensor readings, up to the
            replay clock.
          </p>
        </header>
        <CohortOverview />
        <ParticipantTable />
      </PageContainer>
    </RoleGate>
  )
}
