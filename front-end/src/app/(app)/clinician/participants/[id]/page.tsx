"use client"

import { useParams } from "next/navigation"

import { ParticipantDetail } from "@/components/clinician/participant-detail"
import { PageContainer } from "@/components/page-container"
import { RoleGate } from "@/components/role-gate"

export default function ParticipantPage() {
  const params = useParams<{ id: string }>()
  const id = decodeURIComponent(params.id)
  return (
    <RoleGate role="clinician">
      <PageContainer>
        {/* Keyed so one participant's data never stands in for another's while loading. */}
        <ParticipantDetail key={id} id={id} />
      </PageContainer>
    </RoleGate>
  )
}
