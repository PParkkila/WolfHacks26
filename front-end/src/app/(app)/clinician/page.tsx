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
          <h1 className="text-2xl font-bold tracking-tight">Patient panel</h1>
          <p className="text-muted-foreground">
            Latest Gluco Score and sensor readings for each patient, up to the
            time shown.
          </p>
        </header>
        <CohortOverview />
        <ParticipantTable />
      </PageContainer>
    </RoleGate>
  )
}
