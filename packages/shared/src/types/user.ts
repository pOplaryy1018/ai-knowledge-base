/** 用户角色枚举 */
export type UserRole = 'super_admin' | 'user'

/** 后端返回的用户公开信息 */
export interface UserInfo {
  id: string
  username: string
  role: UserRole
  created_at: string
}

/** 登录请求体 */
export interface LoginRequest {
  username: string
  password: string
}

/** 用户注册请求体 */
export interface RegisterRequest {
  username: string
  password: string
}

/** 登录成功响应 */
export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: UserInfo
}

/** 刷新 Token 响应 */
export interface TokenRefreshResponse {
  access_token: string
  token_type: string
}

/** 管理员更新用户（仅允许修改角色） */
export interface UserUpdate {
  role: UserRole
}

/** 角色定义信息（含实际用户数） */
export interface RoleInfo {
  role: UserRole
  label: string
  description: string
  permissions: string
  user_count: number
}
