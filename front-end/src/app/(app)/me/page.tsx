"use client"

import { PageContainer } from "@/components/page-container"
import { PatientDashboard } from "@/components/patient/patient-dashboard"
import { RoleGate } from "@/components/role-gate"
import { useSession } from "@/lib/auth"

export default function PatientPage() {
  const session = useSession()
  return (
    <RoleGate role="patient">
      <PageContainer>
        {session ? <PatientDashboard principal={session.principal} /> : null}
      </PageContainer>
    </RoleGate>
  )
}
