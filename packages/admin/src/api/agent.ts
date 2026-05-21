import { getApiClient } from './client'
import type {
  Agent,
  AgentCreate,
  AgentUpdate,
  AgentListResponse} from '@akb/shared'

export async function createAgent(body: AgentCreate): Promise<Agent> {
  const { data } = await getApiClient().post<Agent>('/agents', body)
  return data
}

export async function listAgents(
  page = 1,
  size = 20,
): Promise<AgentListResponse> {
  const { data } = await getApiClient().get<AgentListResponse>('/agents', {
    params: { page, size }})
  return data
}

export async function getAgent(id: string): Promise<Agent> {
  const { data } = await getApiClient().get<Agent>(`/agents/${id}`)
  return data
}

export async function updateAgent(
  id: string,
  body: AgentUpdate,
): Promise<Agent> {
  const { data } = await getApiClient().put<Agent>(`/agents/${id}`, body)
  return data
}

export async function deleteAgent(id: string): Promise<void> {
  await getApiClient().delete(`/agents/${id}`)
}
