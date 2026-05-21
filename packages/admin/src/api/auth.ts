/**
 * 认证 API ── 登录、刷新令牌、获取用户信息
 */

import type { LoginRequest, LoginResponse, RoleInfo, TokenRefreshResponse, UserInfo, UserUpdate } from '@akb/shared'
import { getApiClient } from './client'

/** 用户登录 */
export async function login(req: LoginRequest): Promise<LoginResponse> {
  const { data } = await getApiClient().post<LoginResponse>('/auth/login', req)
  return data
}

/** 刷新 access_token */
export async function refreshToken(refreshTokenValue: string): Promise<TokenRefreshResponse> {
  const { data } = await getApiClient().post<TokenRefreshResponse>('/auth/refresh', {
    refresh_token: refreshTokenValue})
  return data
}

/** 获取当前登录用户信息 */
export async function getMe(): Promise<UserInfo> {
  const { data } = await getApiClient().get<UserInfo>('/auth/me')
  return data
}

/** 获取角色定义列表（含各角色实际用户数） */
export async function getRoles(): Promise<RoleInfo[]> {
  const { data } = await getApiClient().get<RoleInfo[]>('/auth/roles')
  return data
}

/** 管理员更新用户角色 */
export async function updateUser(userId: string, body: UserUpdate): Promise<UserInfo> {
  const { data } = await getApiClient().put<UserInfo>(`/auth/users/${userId}`, body)
  return data
}

/** 管理员删除用户 */
export async function deleteUser(userId: string): Promise<void> {
  await getApiClient().delete(`/auth/users/${userId}`)
}
