/**
 * 认证 API ── 注册
 */

import type { RegisterRequest, UserInfo } from '@akb/shared'
import { getApiClient } from './client'

/** 用户自助注册 */
export async function register(params: RegisterRequest): Promise<UserInfo> {
  const { data } = await getApiClient().post<UserInfo>('/auth/register', params)
  return data
}
