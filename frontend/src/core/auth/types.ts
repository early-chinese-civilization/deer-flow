/**
 * 认证类型定义
 */

export interface User {
  id: number;
  externalAuthId: string;
  username: string;
  displayName: string;
  email?: string;
  givenName?: string;
  familyName?: string;
  emailVerified: boolean;
}

export interface AuthContextType {
  user: User | null;
  loading: boolean;
  refetch: () => Promise<void>;
  login: (returnTo?: string) => void;
  logout: () => Promise<void>;
}
